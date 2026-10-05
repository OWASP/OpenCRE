import json
import logging
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.tests.oie_scheduler.graph_filer_test import _envelope
from cre_logging import JSONFormatter
from application.utils.harvester import pipeline as harvest_pipeline
from application.utils.oie_scheduler import health, jobs, lease, run_log
from application.utils.oie_scheduler.jobs import SchedulerConfig, StageResult
from application.utils.oie_scheduler.runner import run_due_jobs, run_job

NOW = datetime(2026, 10, 5, 10, 7, tzinfo=timezone.utc)


def _ok(name):
    return lambda ctx: StageResult(name, "ok", "", {"n": 1})


def _boom(name):
    def fn(ctx):
        raise RuntimeError("kaput")

    return fn


ALL_OK = {
    "agent_sync": _ok("agent_sync"),
    "harvest": _ok("harvest"),
    "noise_filter": _ok("noise_filter"),
    "librarian": _ok("librarian"),
    "file_graph": _ok("file_graph"),
    "gap_analysis": _ok("gap_analysis"),
}


class SchedulerTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def run_job(self, name="owasp", **kw):
        kw.setdefault("overrides", dict(ALL_OK))
        kw.setdefault("now", NOW)
        kw.setdefault("config", SchedulerConfig())
        return run_job(self.collection, name, cache_file="unused", **kw)


class RunJobTest(SchedulerTestBase):
    def test_runs_all_stages_and_records_the_run(self) -> None:
        out = self.run_job()
        self.assertEqual(out.status, "ok")
        self.assertEqual(out.run_id, "owasp-20261005T1000Z")
        self.assertEqual([s.name for s in out.stages], ["agent_sync", "harvest"])
        row = run_log.get_run(sqla.session, out.run_id)
        self.assertEqual(row.status, "ok")
        self.assertEqual(row.trigger, "scheduled")
        self.assertEqual(
            [s["name"] for s in row.summary["stages"]], ["agent_sync", "harvest"]
        )

    def test_same_slot_is_idempotent(self) -> None:
        self.run_job()
        again = self.run_job(now=NOW + timedelta(minutes=2))
        self.assertEqual(again.status, "skipped_already_ran")
        self.assertFalse(again.ran)
        self.assertEqual(sqla.session.query(db.OieRun).count(), 1)

    def test_next_slot_runs_again(self) -> None:
        self.run_job()
        nxt = self.run_job(now=NOW + timedelta(minutes=10))
        self.assertEqual(nxt.status, "ok")
        self.assertEqual(sqla.session.query(db.OieRun).count(), 2)

    def test_force_reruns_and_marks_manual(self) -> None:
        self.run_job()
        out = self.run_job(force=True, trigger="manual")
        self.assertEqual(out.status, "ok")
        row = run_log.get_run(sqla.session, out.run_id)
        self.assertEqual((row.attempts, row.trigger), (2, "manual"))

    def test_held_lease_skips_without_touching_the_run_table(self) -> None:
        with lease.job_lease(sqla.session, "owasp"):
            out = self.run_job()
        self.assertEqual(out.status, "skipped_locked")
        self.assertEqual(sqla.session.query(db.OieRun).count(), 0)

    def test_failing_stage_does_not_stop_later_stages(self) -> None:
        overrides = dict(ALL_OK, agent_sync=_boom("agent_sync"))
        out = self.run_job(overrides=overrides)
        self.assertEqual(out.status, "degraded")
        self.assertEqual([s.status for s in out.stages], ["error", "ok"])
        self.assertIn("kaput", out.stages[0].detail)
        self.assertEqual(run_log.get_run(sqla.session, out.run_id).status, "degraded")

    def test_all_stages_failing_is_an_error_and_retried_next_tick(self) -> None:
        overrides = {
            "agent_sync": _boom("agent_sync"),
            "harvest": _boom("harvest"),
        }
        out = self.run_job(overrides=overrides)
        self.assertEqual(out.status, "error")
        self.assertTrue(out.failed)
        self.assertIn("kaput", out.error)
        retry = self.run_job(now=NOW + timedelta(minutes=2))
        self.assertEqual(retry.status, "ok")
        self.assertEqual(run_log.get_run(sqla.session, retry.run_id).attempts, 2)

    def test_unknown_job_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.run_job("nope")

    def test_dry_run_is_recorded(self) -> None:
        out = self.run_job(dry_run=True)
        self.assertTrue(run_log.get_run(sqla.session, out.run_id).dry_run)

    def test_run_id_and_job_are_in_the_logs(self) -> None:
        seen = []

        def probe(ctx):
            record = logging.LogRecord("x", logging.INFO, "f", 1, "m", None, None)
            seen.append(json.loads(JSONFormatter().format(record)))
            return StageResult("agent_sync", "ok")

        self.run_job(overrides=dict(ALL_OK, agent_sync=probe))
        self.assertEqual(seen[0]["run_id"], "owasp-20261005T1000Z")
        self.assertEqual(seen[0]["job"], "owasp")
        self.assertEqual(seen[0]["stage"], "agent_sync")


class RunDueJobsTest(SchedulerTestBase):
    def test_tick_runs_both_jobs_once_per_slot(self) -> None:
        first = run_due_jobs(
            self.collection,
            cache_file="unused",
            now=NOW,
            config=SchedulerConfig(),
            overrides=dict(ALL_OK),
        )
        self.assertEqual([o.job for o in first], ["owasp", "cre_expansion"])
        self.assertEqual([o.status for o in first], ["ok", "ok"])
        second = run_due_jobs(
            self.collection,
            cache_file="unused",
            now=NOW + timedelta(minutes=10),
            config=SchedulerConfig(),
            overrides=dict(ALL_OK),
        )
        self.assertEqual([o.status for o in second], ["ok", "skipped_already_ran"])

    def test_subset_of_jobs(self) -> None:
        out = run_due_jobs(
            self.collection,
            cache_file="unused",
            jobs=["cre_expansion"],
            now=NOW,
            config=SchedulerConfig(),
            overrides=dict(ALL_OK),
        )
        self.assertEqual([o.job for o in out], ["cre_expansion"])


class ExpansionStagesTest(SchedulerTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.collection.add_cre(
            defs.CRE(id="111-111", name="Authentication", description="d")
        )
        sqla.session.add(
            db.DecisionQueueItem(
                chunk_id="c1",
                artifact_id="a",
                pipeline_run_id="r",
                schema_version="0.2.0",
                status="linked",
                confidence=0.95,
                envelope=_envelope("c1"),
            )
        )
        sqla.session.commit()
        self.ga_calls = []

    def _expansion(self, **cfg):
        overrides = {
            "noise_filter": _ok("noise_filter"),
            "librarian": _ok("librarian"),
        }
        return run_job(
            self.collection,
            "cre_expansion",
            cache_file="db-url",
            now=NOW,
            config=SchedulerConfig(**cfg),
            overrides=overrides,
            ga_fn=self.ga_calls.append,
        )

    def test_filing_edges_triggers_gap_analysis_once(self) -> None:
        out = self._expansion()
        by_name = {s.name: s for s in out.stages}
        self.assertEqual(by_name["file_graph"].summary["links_added"], 1)
        self.assertEqual(by_name["gap_analysis"].status, "ok")
        self.assertEqual(self.ga_calls, ["db-url"])
        self.assertEqual(
            by_name["gap_analysis"].summary["standards"], ["OWASP/www-project-foo"]
        )

    def test_no_new_edges_means_no_gap_analysis(self) -> None:
        self._expansion()
        self.ga_calls.clear()
        out = run_job(
            self.collection,
            "cre_expansion",
            cache_file="db-url",
            now=NOW + timedelta(days=1),
            config=SchedulerConfig(),
            overrides={
                "noise_filter": _ok("noise_filter"),
                "librarian": _ok("librarian"),
            },
            ga_fn=self.ga_calls.append,
        )
        by_name = {s.name: s for s in out.stages}
        self.assertEqual(by_name["gap_analysis"].status, "skipped")
        self.assertEqual(self.ga_calls, [])

    def test_kill_switch_skips_filing_and_gap_analysis(self) -> None:
        out = self._expansion(filing_enabled=False)
        by_name = {s.name: s for s in out.stages}
        self.assertEqual(by_name["file_graph"].status, "skipped")
        self.assertEqual(by_name["gap_analysis"].status, "skipped")
        self.assertEqual(self.ga_calls, [])
        self.assertIsNone(sqla.session.query(db.DecisionQueueItem).one().consumed_at)

    def test_high_floor_drops_the_link_and_skips_gap_analysis(self) -> None:
        out = self._expansion(file_floor=0.99)
        by_name = {s.name: s for s in out.stages}
        self.assertEqual(by_name["file_graph"].summary["below_floor"], 1)
        self.assertEqual(by_name["gap_analysis"].status, "skipped")

    def test_dry_run_files_nothing(self) -> None:
        out = run_job(
            self.collection,
            "cre_expansion",
            cache_file="db-url",
            now=NOW,
            dry_run=True,
            config=SchedulerConfig(),
            overrides={
                "noise_filter": _ok("noise_filter"),
                "librarian": _ok("librarian"),
            },
            ga_fn=self.ga_calls.append,
        )
        self.assertEqual(sqla.session.query(db.Node).count(), 0)
        self.assertEqual(self.ga_calls, [])
        self.assertEqual(out.status, "ok")

    def test_standard_kind_repos_are_not_filed(self) -> None:
        envelope = _envelope("c2", repo="OWASP/ASVS")
        sqla.session.add(
            db.DecisionQueueItem(
                chunk_id="c2",
                artifact_id="a",
                pipeline_run_id="r",
                schema_version="0.2.0",
                status="linked",
                confidence=0.95,
                envelope=envelope,
            )
        )
        sqla.session.commit()
        out = self._expansion()
        filer = {s.name: s for s in out.stages}["file_graph"].summary
        self.assertEqual(filer["skipped_standard_repo"], 1)
        self.assertEqual(filer["filed"], 1)

    def test_real_noise_and_librarian_stages_skip_on_empty_queues(self) -> None:
        out = run_job(
            self.collection,
            "cre_expansion",
            cache_file="db-url",
            now=NOW,
            config=SchedulerConfig(filing_enabled=False),
            ga_fn=self.ga_calls.append,
        )
        by_name = {s.name: s for s in out.stages}
        self.assertEqual(by_name["noise_filter"].status, "skipped")
        self.assertEqual(by_name["librarian"].status, "skipped")
        self.assertEqual(out.status, "ok")


class OwaspStagesTest(SchedulerTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.repos = Path(self.tmp.name) / "repos.yaml"
        self.repos.write_text(
            """
defaults:
  project:
    type: github
    owner: OWASP
    branch: main
    paths: {include: ["**/*.md"]}
    chunking: {strategy: docling, max_tokens: 1000}
    polling: {mode: incremental, interval_minutes: 1440}
repositories:
  - {id: owasp-p1, kind: project, repo: p1}
  - {id: owasp-p2, kind: project, repo: p2}
  - {id: owasp-p3, kind: project, repo: p3}
"""
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()
        super().tearDown()

    def test_harvest_stage_is_capped_and_reports_repos(self) -> None:
        visited = []

        def fake(*, repo_cfg, **_):
            visited.append(repo_cfg.id)
            return 2

        with patch.object(harvest_pipeline, "_harvest_repository", fake):
            out = self.run_job(
                overrides={"agent_sync": _ok("agent_sync")},
                config=SchedulerConfig(harvest_max_repos=2, repos_yaml=str(self.repos)),
            )
        self.assertEqual(visited, ["owasp-p1", "owasp-p2"])
        harvest = {s.name: s for s in out.stages}["harvest"]
        self.assertEqual(harvest.status, "ok")
        self.assertEqual(harvest.summary["chunks_written"], 4)
        self.assertEqual(harvest.summary["deferred"], 1)
        self.assertEqual(harvest.summary["repository_ids"], ["owasp-p1", "owasp-p2"])

    def _agent_sync(self, agent_db):
        from application.utils.owasp_agent import index_store
        from application.utils.owasp_agent import sync as agent_sync

        targets = []

        class RecordingStore:
            def __init__(self, target):
                targets.append(target)

        ctx = jobs.JobContext(
            collection=self.collection,
            cache_file="unused",
            run_id="owasp-test",
            now=NOW,
            config=SchedulerConfig(repos_yaml=str(self.repos), agent_db=agent_db),
        )
        report = agent_sync.SyncReport(nest_ok=True, github_ok=True)
        with patch.object(index_store, "IndexStore", RecordingStore), patch.object(
            agent_sync, "sync_all", lambda **_: report
        ):
            return jobs.stage_agent_sync(ctx), targets

    def test_agent_sync_reports_and_redacts_its_index_target(self) -> None:
        url = "postgresql://cre:hunter2@db.example/cre"
        result, targets = self._agent_sync(url)
        self.assertEqual(targets, [url])
        self.assertEqual(
            result.summary["index_target"], "postgresql://cre:***@db.example/cre"
        )
        self.assertNotIn("hunter2", json.dumps(result.summary))

    def test_agent_sync_falls_back_to_the_app_database(self) -> None:
        result, targets = self._agent_sync(None)
        self.assertEqual(targets, [str(sqla.session.get_bind().url)])
        self.assertEqual(result.status, "ok")

    def test_harvest_errors_mark_the_stage_degraded(self) -> None:
        def fake(*, repo_cfg, **_):
            raise RuntimeError("clone failed")

        with patch.object(harvest_pipeline, "_harvest_repository", fake):
            out = self.run_job(
                overrides={"agent_sync": _ok("agent_sync")},
                config=SchedulerConfig(repos_yaml=str(self.repos)),
            )
        harvest = {s.name: s for s in out.stages}["harvest"]
        self.assertEqual(harvest.status, "degraded")
        self.assertEqual(out.status, "degraded")


class HealthTest(SchedulerTestBase):
    def test_never_ran_is_unhealthy(self) -> None:
        report = health.evaluate_health(sqla.session, NOW)
        self.assertFalse(report["healthy"])
        self.assertEqual(report["jobs"]["owasp"]["state"], "never_ran")
        self.assertEqual(report["queues"]["harvest_input_pending"], 0)

    def test_recent_success_is_healthy(self) -> None:
        for name in ("owasp", "cre_expansion"):
            self.run_job(name)
        report = health.evaluate_health(sqla.session, NOW + timedelta(minutes=1))
        self.assertTrue(report["healthy"])
        self.assertEqual(report["jobs"]["owasp"]["state"], "ok")
        self.assertIsNotNone(report["jobs"]["owasp"]["last_success_at"])

    def test_old_success_is_stale(self) -> None:
        for name in ("owasp", "cre_expansion"):
            self.run_job(name)
        later = run_log.utcnow() + timedelta(hours=2)
        report = health.evaluate_health(sqla.session, later)
        self.assertEqual(report["jobs"]["owasp"]["state"], "stale")
        self.assertEqual(report["jobs"]["cre_expansion"]["state"], "ok")
        self.assertFalse(report["healthy"])

    def test_latest_failure_after_a_success_is_failing(self) -> None:
        self.run_job("owasp")
        self.run_job(
            "owasp",
            now=NOW + timedelta(minutes=10),
            overrides={"agent_sync": _boom("a"), "harvest": _boom("h")},
        )
        report = health.evaluate_health(sqla.session, NOW + timedelta(minutes=12))
        self.assertEqual(report["jobs"]["owasp"]["state"], "failing")

    def test_queue_depths_count_backlog(self) -> None:
        sqla.session.add(
            db.HarvestInput(pipeline_run_id="r", status="pending", payload={"a": 1})
        )
        sqla.session.commit()
        self.assertEqual(health.queue_depths(sqla.session)["harvest_input_pending"], 1)


class RunScheduledCliTest(SchedulerTestBase):
    def test_non_postgres_database_is_refused(self) -> None:
        import argparse

        from application.cmd import cre_main

        args = argparse.Namespace(
            run_scheduled="all",
            scheduled_force=False,
            scheduled_dry_run=False,
            cache_file="sqlite://",
        )
        self.assertEqual(cre_main.run_scheduled_cli(args, self.collection), 2)
        self.assertEqual(sqla.session.query(db.OieRun).count(), 0)


if __name__ == "__main__":
    unittest.main()
