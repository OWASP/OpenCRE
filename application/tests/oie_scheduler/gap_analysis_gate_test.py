"""Cache-only / queue gates for scheduled gap_analysis."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from application.utils.oie_scheduler.jobs import (
    JobContext,
    SchedulerConfig,
    _cache_only_ga_block_reason,
    stage_gap_analysis,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _ctx(filer: Optional[Any] = None, cache_file: str = "db") -> JobContext:
    collection = SimpleNamespace(session=object())
    state = {"filer": filer} if filer is not None else {}
    return JobContext(
        collection=collection,
        cache_file=cache_file,
        run_id="run-1",
        now=NOW,
        dry_run=False,
        config=SchedulerConfig(),
        state=state,
    )


class TestCacheOnlyGaGate(unittest.TestCase):
    def tearDown(self) -> None:
        for key in (
            "CRE_HEROKU_CACHE_ONLY",
            "DYNO",
            "DATABASE_URL",
            "DEV_DATABASE_URL",
            "CRE_CACHE_FILE",
            "CRE_OIE_GA_VIA_QUEUE",
            "I_UNDERSTAND_LIVE_GA_INLINE",
        ):
            os.environ.pop(key, None)

    def test_heroku_cache_only_env_blocks(self) -> None:
        os.environ["CRE_HEROKU_CACHE_ONLY"] = "1"
        self.assertIn("CRE_HEROKU_CACHE_ONLY", _cache_only_ga_block_reason() or "")

    def test_dyno_blocks(self) -> None:
        os.environ["DYNO"] = "web.1"
        self.assertIn("DYNO", _cache_only_ga_block_reason() or "")

    def test_opencreorg_dsn_blocks(self) -> None:
        self.assertIn(
            "opencreorg",
            _cache_only_ga_block_reason("postgres://u:p@host/opencreorg") or "",
        )

    def test_stage_skips_when_cache_only(self) -> None:
        os.environ["CRE_HEROKU_CACHE_ONLY"] = "1"
        filer = SimpleNamespace(
            graph_changed=True, standards={"OWASP/x"}, links_added=1
        )
        out = stage_gap_analysis(_ctx(filer))
        self.assertEqual(out.status, "skipped")
        self.assertIn("cache-only", out.detail)

    def test_stage_skips_without_queue_or_inline_ack(self) -> None:
        filer = SimpleNamespace(
            graph_changed=True, standards={"OWASP/x"}, links_added=1
        )
        out = stage_gap_analysis(_ctx(filer))
        self.assertEqual(out.status, "skipped")
        self.assertIn("CRE_OIE_GA_VIA_QUEUE", out.detail)

    @patch("application.utils.oie_scheduler.jobs._enqueue_ga")
    def test_stage_enqueues_when_via_queue(self, enqueue: MagicMock) -> None:
        enqueue.return_value = {"queued": True, "queue": "ga"}
        os.environ["CRE_OIE_GA_VIA_QUEUE"] = "1"
        filer = SimpleNamespace(
            graph_changed=True, standards={"OWASP/x"}, links_added=2
        )
        out = stage_gap_analysis(_ctx(filer))
        self.assertEqual(out.status, "ok")
        enqueue.assert_called_once_with("db")
        self.assertTrue(out.summary.get("queued"))


if __name__ == "__main__":
    unittest.main()
