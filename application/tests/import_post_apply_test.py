import unittest
from unittest.mock import Mock, patch

from application.utils import import_post_apply


class TestImportPostApply(unittest.TestCase):
    @patch("application.utils.import_post_apply.prompt_client.PromptHandler")
    @patch("application.utils.import_post_apply.cre_main.populate_neo4j_db")
    @patch("application.utils.import_post_apply.redis.wait_for_jobs")
    @patch("application.utils.import_post_apply.cre_main.schedule_gap_analysis_pairs_with_rq")
    @patch("application.utils.import_post_apply.cre_main.resolve_ga_peer_standard_names")
    @patch("application.utils.import_post_apply.db_backend.detect_backend")
    def test_post_apply_runs_pair_level_ga_only(
        self,
        detect_backend_mock,
        resolve_peers_mock,
        schedule_pairs_mock,
        wait_for_jobs_mock,
        populate_neo4j_mock,
        prompt_handler_cls_mock,
    ) -> None:
        detect_backend_mock.return_value = Mock(is_postgres=True, backend="postgres")
        collection = Mock()
        collection.with_graph.return_value = collection
        resolve_peers_mock.return_value = ["ASVS", "CWE"]
        schedule_pairs_mock.return_value = [Mock(description="ASVS->CWE")]

        import_post_apply.run_post_apply(
            collection=collection,
            db_connection_str="postgresql://cre:password@127.0.0.1:5432/cre",
            touched_standard_names=["ASVS"],
        )

        populate_neo4j_mock.assert_called_once()
        schedule_pairs_mock.assert_called_with(
            collection=collection,
            importing_name="ASVS",
            db_connection_str="postgresql://cre:password@127.0.0.1:5432/cre",
            peer_names=["ASVS", "CWE"],
            skip_neo_populate=True,
        )
        wait_for_jobs_mock.assert_called_once()

    @patch("application.utils.import_post_apply.prompt_client.PromptHandler")
    @patch("application.utils.import_post_apply.redis.wait_for_jobs")
    @patch("application.utils.import_post_apply.db_backend.detect_backend")
    def test_post_apply_skips_ga_on_sqlite_backend(
        self,
        detect_backend_mock,
        wait_for_jobs_mock,
        prompt_handler_cls_mock,
    ) -> None:
        detect_backend_mock.return_value = Mock(is_postgres=False, backend="sqlite")
        collection = Mock()
        collection.with_graph.return_value = collection

        import_post_apply.run_post_apply(
            collection=collection,
            db_connection_str="sqlite:///tmp.db",
            touched_standard_names=["ASVS"],
        )

        wait_for_jobs_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
