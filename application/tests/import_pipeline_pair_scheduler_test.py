import unittest
from unittest.mock import Mock, patch

from application.utils import import_pipeline
from application.utils.external_project_parsers import base_parser_defs


class TestImportPipelinePairScheduler(unittest.TestCase):
    @patch("application.cmd.cre_main.schedule_gap_analysis_pairs_with_rq")
    @patch("application.cmd.cre_main.resolve_ga_peer_standard_names")
    @patch("application.cmd.cre_main.db_connect")
    @patch("application.utils.import_pipeline._phase2_snapshots_and_staging")
    @patch("application.utils.telemetry.emit_import_event")
    @patch("rq.Queue.enqueue_call")
    @patch("alive_progress.alive_bar")
    @patch("application.utils.redis.wait_for_jobs")
    @patch("application.utils.redis.empty_queues")
    @patch("application.utils.redis.connect")
    @patch("application.utils.db_backend.detect_backend")
    @patch("application.prompt_client.prompt_client.PromptHandler")
    @patch("application.utils.external_project_parsers.base_parser_defs.validate_classification_tags")
    def test_postgres_schedules_pair_jobs_separately(
        self,
        validate_tags_mock,
        prompt_handler_cls_mock,
        detect_backend_mock,
        redis_connect_mock,
        empty_queues_mock,
        wait_for_jobs_mock,
        alive_bar_mock,
        enqueue_call_mock,
        emit_import_event_mock,
        phase2_mock,
        db_connect_mock,
        resolve_peers_mock,
        schedule_pairs_mock,
    ) -> None:
        detect_backend_mock.return_value = Mock(is_postgres=True, backend="postgres", supports_pair_ga_scheduler=True, reason="test")
        redis_connect_mock.return_value = Mock()
        prompt_handler_cls_mock.return_value = Mock()
        collection = Mock()
        collection.with_graph.return_value = collection

        pr = base_parser_defs.ParseResult(
            results={
                "CRE": [],
                "ASVS": [Mock(name="a1")],
                "CWE": [Mock(name="c1")],
            },
            calculate_gap_analysis=True,
            calculate_embeddings=False,
        )

        job_obj = Mock()
        enqueue_call_mock.return_value = job_obj
        db_connect_mock.return_value = collection
        resolve_peers_mock.side_effect = lambda _c, n: ["ASVS", "CWE"]
        schedule_pairs_mock.side_effect = [
            [Mock(), Mock()],
            [Mock(), Mock()],
        ]
        alive_bar_mock.return_value.__enter__.return_value = Mock()
        alive_bar_mock.return_value.__exit__.return_value = False

        import_pipeline.apply_parse_result_with_rq(
            parse_result=pr,
            cache_location="postgresql://cre:password@localhost:5432/cre",
            collection=collection,
            prompt_handler=None,
            import_run_id=None,
            import_source=None,
            validate_classification_tags=True,
        )

        # Standard jobs are enqueued with GA disabled; GA is moved to pair scheduler.
        standard_job_kwargs = [c.kwargs["kwargs"] for c in enqueue_call_mock.call_args_list]
        self.assertTrue(all(k["calculate_gap_analysis"] is False for k in standard_job_kwargs))
        self.assertEqual(2, schedule_pairs_mock.call_count)
        self.assertEqual(2, wait_for_jobs_mock.call_count)  # one for import jobs, one for GA pair jobs
        emit_import_event_mock.assert_not_called()

    @patch("application.cmd.cre_main.schedule_gap_analysis_pairs_with_rq")
    @patch("application.cmd.cre_main.db_connect")
    @patch("rq.Queue.enqueue_call")
    @patch("alive_progress.alive_bar")
    @patch("application.utils.redis.wait_for_jobs")
    @patch("application.utils.redis.empty_queues")
    @patch("application.utils.redis.connect")
    @patch("application.utils.db_backend.detect_backend")
    @patch("application.prompt_client.prompt_client.PromptHandler")
    @patch("application.utils.external_project_parsers.base_parser_defs.validate_classification_tags")
    def test_non_postgres_rejects_ga_scheduler_path(
        self,
        validate_tags_mock,
        prompt_handler_cls_mock,
        detect_backend_mock,
        redis_connect_mock,
        empty_queues_mock,
        wait_for_jobs_mock,
        alive_bar_mock,
        enqueue_call_mock,
        db_connect_mock,
        schedule_pairs_mock,
    ) -> None:
        detect_backend_mock.return_value = Mock(is_postgres=False, backend="sqlite", supports_pair_ga_scheduler=False, reason="test")
        redis_connect_mock.return_value = Mock()
        prompt_handler_cls_mock.return_value = Mock()
        collection = Mock()
        collection.with_graph.return_value = collection

        pr = base_parser_defs.ParseResult(
            results={"CRE": [], "ASVS": [Mock(name="a1")]},
            calculate_gap_analysis=True,
            calculate_embeddings=False,
        )

        enqueue_call_mock.return_value = Mock()
        db_connect_mock.return_value = collection
        alive_bar_mock.return_value.__enter__.return_value = Mock()
        alive_bar_mock.return_value.__exit__.return_value = False

        with self.assertRaises(RuntimeError):
            import_pipeline.apply_parse_result_with_rq(
                parse_result=pr,
                cache_location="sqlite:///tmp.db",
                collection=collection,
                prompt_handler=None,
                import_run_id=None,
                import_source=None,
                validate_classification_tags=True,
            )

        enqueue_call_mock.assert_not_called()
        schedule_pairs_mock.assert_not_called()
        self.assertEqual(0, wait_for_jobs_mock.call_count)

    @patch("application.cmd.cre_main.run_gap_pair_job")
    @patch("application.cmd.cre_main.schedule_gap_analysis_pairs_with_rq")
    @patch("application.cmd.cre_main.resolve_ga_peer_standard_names")
    @patch("application.cmd.cre_main.db_connect")
    @patch("application.utils.import_pipeline._phase2_snapshots_and_staging")
    @patch("application.utils.telemetry.emit_import_event")
    @patch("rq.Queue.enqueue_call")
    @patch("alive_progress.alive_bar")
    @patch("application.utils.redis.wait_for_jobs")
    @patch("application.utils.redis.empty_queues")
    @patch("application.utils.redis.connect")
    @patch("application.utils.db_backend.detect_backend")
    @patch("application.prompt_client.prompt_client.PromptHandler")
    @patch("application.utils.external_project_parsers.base_parser_defs.validate_classification_tags")
    def test_postgres_retries_failed_pair_jobs_only(
        self,
        validate_tags_mock,
        prompt_handler_cls_mock,
        detect_backend_mock,
        redis_connect_mock,
        empty_queues_mock,
        wait_for_jobs_mock,
        alive_bar_mock,
        enqueue_call_mock,
        emit_import_event_mock,
        phase2_mock,
        db_connect_mock,
        resolve_peers_mock,
        schedule_pairs_mock,
        run_pair_job_mock,
    ) -> None:
        detect_backend_mock.return_value = Mock(is_postgres=True, backend="postgres", supports_pair_ga_scheduler=True, reason="test")
        redis_connect_mock.return_value = Mock()
        prompt_handler_cls_mock.return_value = Mock()
        collection = Mock()
        collection.with_graph.return_value = collection

        pr = base_parser_defs.ParseResult(
            results={"CRE": [], "ASVS": [Mock(name="a1")]},
            calculate_gap_analysis=True,
            calculate_embeddings=False,
        )
        db_connect_mock.return_value = collection
        resolve_peers_mock.return_value = ["CWE"]
        first_failed = Mock(is_failed=True, kwargs={"importing_name": "ASVS", "peer_name": "CWE"}, description="ASVS->CWE")
        first_ok = Mock(is_failed=False, kwargs={"importing_name": "CWE", "peer_name": "ASVS"}, description="CWE->ASVS")
        schedule_pairs_mock.return_value = [first_failed, first_ok]
        enqueue_call_mock.return_value = Mock(is_failed=False)
        alive_bar_mock.return_value.__enter__.return_value = Mock()
        alive_bar_mock.return_value.__exit__.return_value = False

        import os
        os.environ["CRE_GA_PAIR_JOB_RETRY_ATTEMPTS"] = "1"
        try:
            import_pipeline.apply_parse_result_with_rq(
                parse_result=pr,
                cache_location="postgresql://cre:password@localhost:5432/cre",
                collection=collection,
                prompt_handler=None,
                import_run_id=None,
                import_source=None,
                validate_classification_tags=True,
            )
        finally:
            os.environ.pop("CRE_GA_PAIR_JOB_RETRY_ATTEMPTS", None)

        # wait_for_jobs called for standard jobs, initial GA jobs, and retried failed GA job.
        self.assertGreaterEqual(wait_for_jobs_mock.call_count, 3)
        # Retry enqueue is only for failed pair(s), not successful ones.
        self.assertTrue(enqueue_call_mock.called)
        emit_import_event_mock.assert_not_called()

    @patch("application.cmd.cre_main.run_gap_pair_job")
    @patch("application.cmd.cre_main.schedule_gap_analysis_pairs_with_rq")
    @patch("application.cmd.cre_main.resolve_ga_peer_standard_names")
    @patch("application.cmd.cre_main.db_connect")
    @patch("application.utils.import_pipeline._phase2_snapshots_and_staging")
    @patch("application.utils.telemetry.emit_import_event")
    @patch("rq.Queue.enqueue_call")
    @patch("alive_progress.alive_bar")
    @patch("application.utils.redis.wait_for_jobs")
    @patch("application.utils.redis.empty_queues")
    @patch("application.utils.redis.connect")
    @patch("application.utils.db_backend.detect_backend")
    @patch("application.prompt_client.prompt_client.PromptHandler")
    @patch("application.utils.external_project_parsers.base_parser_defs.validate_classification_tags")
    def test_postgres_interrupted_pair_recovery_requeues_only_remaining_pair(
        self,
        validate_tags_mock,
        prompt_handler_cls_mock,
        detect_backend_mock,
        redis_connect_mock,
        empty_queues_mock,
        wait_for_jobs_mock,
        alive_bar_mock,
        enqueue_call_mock,
        emit_import_event_mock,
        phase2_snapshots_mock,
        db_connect_mock,
        resolve_peers_mock,
        schedule_pairs_mock,
        run_pair_job_mock,
    ) -> None:
        detect_backend_mock.return_value = Mock(
            is_postgres=True,
            backend="postgres",
            supports_pair_ga_scheduler=True,
            reason="test",
        )
        redis_connect_mock.return_value = Mock()
        prompt_handler_cls_mock.return_value = Mock()
        collection = Mock()
        collection.with_graph.return_value = collection

        pr = base_parser_defs.ParseResult(
            results={"CRE": [], "ASVS": [Mock(name="a1")]},
            calculate_gap_analysis=True,
            calculate_embeddings=False,
        )
        db_connect_mock.return_value = collection
        resolve_peers_mock.return_value = ["CWE"]
        # Simulate a mid-run interruption/failure for one directed pair while the other succeeds.
        failed_pair = Mock(
            is_failed=True,
            kwargs={"importing_name": "ASVS", "peer_name": "CWE"},
            description="ASVS->CWE",
        )
        successful_pair = Mock(
            is_failed=False,
            kwargs={"importing_name": "CWE", "peer_name": "ASVS"},
            description="CWE->ASVS",
        )
        schedule_pairs_mock.return_value = [failed_pair, successful_pair]
        recovered_retry_job = Mock(is_failed=False, description="ASVS->CWE")
        enqueue_call_mock.return_value = recovered_retry_job
        alive_bar_mock.return_value.__enter__.return_value = Mock()
        alive_bar_mock.return_value.__exit__.return_value = False

        import os

        os.environ["CRE_GA_PAIR_JOB_RETRY_ATTEMPTS"] = "1"
        try:
            import_pipeline.apply_parse_result_with_rq(
                parse_result=pr,
                cache_location="postgresql://cre:password@localhost:5432/cre",
                collection=collection,
                prompt_handler=None,
                import_run_id=None,
                import_source=None,
                validate_classification_tags=True,
            )
        finally:
            os.environ.pop("CRE_GA_PAIR_JOB_RETRY_ATTEMPTS", None)

        # The retry path should enqueue exactly one GA replay and only for failed ASVS->CWE.
        self.assertEqual(enqueue_call_mock.call_count, 2)  # 1 standard import + 1 GA retry
        retry_call = enqueue_call_mock.call_args_list[-1]
        self.assertEqual(retry_call.kwargs["description"], "ASVS->CWE")
        self.assertEqual(
            retry_call.kwargs["kwargs"]["importing_name"],
            "ASVS",
        )
        self.assertEqual(
            retry_call.kwargs["kwargs"]["peer_name"],
            "CWE",
        )
        # Coordinator waits for import jobs + initial GA batch + retried failed pair batch.
        self.assertEqual(wait_for_jobs_mock.call_count, 3)
        emit_import_event_mock.assert_not_called()

    @patch("application.cmd.cre_main.schedule_gap_analysis_pairs_with_rq")
    @patch("application.cmd.cre_main.resolve_ga_peer_standard_names")
    @patch("application.cmd.cre_main.db_connect")
    @patch("application.utils.telemetry.emit_import_event")
    @patch("rq.Queue.enqueue_call")
    @patch("alive_progress.alive_bar")
    @patch("application.utils.redis.wait_for_jobs")
    @patch("application.utils.redis.empty_queues")
    @patch("application.utils.redis.connect")
    @patch("application.utils.db_backend.detect_backend")
    @patch("application.prompt_client.prompt_client.PromptHandler")
    @patch("application.utils.external_project_parsers.base_parser_defs.validate_classification_tags")
    def test_emits_ga_pair_op_counts_to_telemetry(
        self,
        validate_tags_mock,
        prompt_handler_cls_mock,
        detect_backend_mock,
        redis_connect_mock,
        empty_queues_mock,
        wait_for_jobs_mock,
        alive_bar_mock,
        enqueue_call_mock,
        emit_import_event_mock,
        db_connect_mock,
        resolve_peers_mock,
        schedule_pairs_mock,
    ) -> None:
        detect_backend_mock.return_value = Mock(is_postgres=True, backend="postgres", supports_pair_ga_scheduler=True, reason="test")
        redis_connect_mock.return_value = Mock()
        prompt_handler_cls_mock.return_value = Mock()
        collection = Mock()
        collection.with_graph.return_value = collection
        db_connect_mock.return_value = collection

        pr = base_parser_defs.ParseResult(
            results={"CRE": [], "ASVS": [Mock(name="a1")]},
            calculate_gap_analysis=True,
            calculate_embeddings=False,
        )
        resolve_peers_mock.return_value = ["CWE"]
        schedule_pairs_mock.return_value = [Mock(is_failed=False, kwargs={})]
        enqueue_call_mock.return_value = Mock(is_failed=False)
        alive_bar_mock.return_value.__enter__.return_value = Mock()
        alive_bar_mock.return_value.__exit__.return_value = False

        with patch("application.utils.import_pipeline._phase2_snapshots_and_staging"):
            import_pipeline.apply_parse_result_with_rq(
                parse_result=pr,
                cache_location="postgresql://cre:password@localhost:5432/cre",
                collection=collection,
                prompt_handler=None,
                import_run_id="run-123",
                import_source="test-source",
                validate_classification_tags=True,
            )

        emit_import_event_mock.assert_called_once()
        op_counts = emit_import_event_mock.call_args.kwargs["op_counts"]
        self.assertEqual(op_counts["ga_pairs_planned"], 2)
        self.assertEqual(op_counts["ga_pairs_enqueued"], 1)
        self.assertEqual(op_counts["ga_pairs_failed"], 0)


if __name__ == "__main__":
    unittest.main()
