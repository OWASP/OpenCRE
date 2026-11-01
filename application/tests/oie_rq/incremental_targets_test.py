"""Tests for exhaustive incremental skip / retry / failure reporting."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from application.utils.harvester.schemas import RepositoryConfig
from application.utils.oie_rq.incremental_targets import (
    MAX_TARGET_ATTEMPTS,
    FailureReport,
    TargetOutcome,
    harvestable_targets,
    record_attempt,
    should_skip_target,
    source_repo_for,
)


def _repo(
    repo_id: str = "owasp-asvs",
    *,
    kind: str = "standard",
    enabled: bool = True,
) -> RepositoryConfig:
    return RepositoryConfig.model_validate(
        {
            "id": repo_id,
            "kind": kind,
            "type": "github",
            "enabled": enabled,
            "owner": "OWASP",
            "repo": "ASVS",
            "branch": "master",
            "paths": {"include": ["**/*.md"]},
            "chunking": {
                "strategy": "markdown_heading",
                "max_tokens": 1000,
                "overlap_tokens": 100,
            },
            "polling": {"mode": "incremental", "interval_minutes": 60},
        }
    )


class HarvestableTargetsTests(unittest.TestCase):
    def test_filters_chapter_event_and_disabled(self) -> None:
        repos = [
            _repo("a", kind="standard"),
            _repo("b", kind="project"),
            _repo("c", kind="other"),
            _repo("d", kind="chapter"),
            _repo("e", kind="event"),
            _repo("f", kind="standard", enabled=False),
        ]
        # model_validate may reject unknown ids' repo names — rebuild with unique repos
        fixed = []
        for r, name in zip(
            repos,
            ["ASVS", "www-project-x", "Foo", "www-chapter-y", "www-event-z", "Bar"],
        ):
            data = r.model_dump()
            data["repo"] = name
            data["id"] = r.id
            fixed.append(RepositoryConfig.model_validate(data))
        got = harvestable_targets(fixed)
        self.assertEqual([g.id for g in got], ["a", "b", "c"])

    def test_source_repo_for(self) -> None:
        self.assertEqual(source_repo_for(_repo()), "OWASP/ASVS")


class SkipLogicTests(unittest.TestCase):
    @patch("application.utils.oie_rq.incremental_targets._unconsumed_kq_for_source")
    @patch("application.utils.oie_rq.incremental_targets._pending_hi_count")
    @patch("application.utils.oie_rq.incremental_targets.load_checkpoint_sha")
    def test_skip_when_sha_unchanged_and_drained(
        self, load_sha: MagicMock, pending: MagicMock, open_kq: MagicMock
    ) -> None:
        load_sha.return_value = "abc123"
        pending.return_value = 0
        open_kq.return_value = 0
        skip, reason = should_skip_target(
            MagicMock(),
            repo_id="owasp-asvs",
            source_repo="OWASP/ASVS",
            head_sha="abc123",
        )
        self.assertTrue(skip)
        self.assertEqual(reason, "sha_unchanged_and_prior_success")

    @patch("application.utils.oie_rq.incremental_targets._unconsumed_kq_for_source")
    @patch("application.utils.oie_rq.incremental_targets._pending_hi_count")
    @patch("application.utils.oie_rq.incremental_targets.load_checkpoint_sha")
    def test_no_skip_when_pending_hi(
        self, load_sha: MagicMock, pending: MagicMock, open_kq: MagicMock
    ) -> None:
        load_sha.return_value = "abc123"
        pending.return_value = 3
        open_kq.return_value = 0
        skip, reason = should_skip_target(
            MagicMock(),
            repo_id="owasp-asvs",
            source_repo="OWASP/ASVS",
            head_sha="abc123",
        )
        self.assertFalse(skip)
        self.assertEqual(reason, "")

    @patch("application.utils.oie_rq.incremental_targets._unconsumed_kq_for_source")
    @patch("application.utils.oie_rq.incremental_targets._pending_hi_count")
    @patch("application.utils.oie_rq.incremental_targets.load_checkpoint_sha")
    def test_skip_drained_no_head(
        self, load_sha: MagicMock, pending: MagicMock, open_kq: MagicMock
    ) -> None:
        load_sha.return_value = "abc123"
        pending.return_value = 0
        open_kq.return_value = 0
        skip, reason = should_skip_target(
            MagicMock(),
            repo_id="owasp-asvs",
            source_repo="OWASP/ASVS",
            head_sha="",
        )
        self.assertTrue(skip)
        self.assertEqual(reason, "all_hi_processed_kq_consumed")

    @patch("application.utils.oie_rq.incremental_targets._unconsumed_kq_for_source")
    @patch("application.utils.oie_rq.incremental_targets._pending_hi_count")
    @patch("application.utils.oie_rq.incremental_targets.load_checkpoint_sha")
    def test_no_skip_when_sha_changed(
        self, load_sha: MagicMock, pending: MagicMock, open_kq: MagicMock
    ) -> None:
        load_sha.return_value = "old"
        pending.return_value = 0
        open_kq.return_value = 0
        skip, _ = should_skip_target(
            MagicMock(),
            repo_id="owasp-asvs",
            source_repo="OWASP/ASVS",
            head_sha="new",
        )
        self.assertFalse(skip)


class RetryFailureTests(unittest.TestCase):
    def test_retries_then_exhausted(self) -> None:
        o = TargetOutcome(repo_id="x", source_repo="OWASP/X", status="pending")
        for i in range(MAX_TARGET_ATTEMPTS - 1):
            o = record_attempt(o, ok=False, error=f"boom{i}")
            self.assertEqual(o.status, "failed")
            self.assertEqual(o.attempts, i + 1)
        o = record_attempt(o, ok=False, error="final")
        self.assertEqual(o.status, "exhausted")
        self.assertEqual(o.attempts, MAX_TARGET_ATTEMPTS)

    def test_success_clears_error(self) -> None:
        o = TargetOutcome(
            repo_id="x", source_repo="OWASP/X", status="failed", attempts=2, error="e"
        )
        o = record_attempt(o, ok=True)
        self.assertEqual(o.status, "ok")
        self.assertEqual(o.error, "")
        self.assertEqual(o.attempts, 3)

    def test_failure_report_ok_when_empty(self) -> None:
        report = FailureReport(run_id="r1")
        self.assertTrue(report.to_dict()["ok"])
        report.failures.append(
            TargetOutcome(repo_id="x", source_repo="OWASP/X", status="exhausted")
        )
        self.assertFalse(report.to_dict()["ok"])
        self.assertEqual(report.to_dict()["failure_count"], 1)


if __name__ == "__main__":
    unittest.main()
