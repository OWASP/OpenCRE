"""Tests for the corrections log: the durable half of a verdict.

The property under test is not formatting, it is the retirement gate: what this
log records is what permits ``mark_reviewed`` to run, so a record must land
whole, survive reopening, and refuse verdicts outside the two the RFC defines.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from application.utils.reviewer.corrections_log import (
    CORRECTIONS_SCHEMA_VERSION,
    JsonlCorrectionsLog,
    ReviewVerdict,
)

AT = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)


def _verdict(**overrides) -> ReviewVerdict:
    values = dict(
        decision_row_id="row-1",
        review_id="review:chk:1",
        chunk_id="chk:1",
        pipeline_run_id="run-1",
        reason_code="BELOW_THRESHOLD",
        source_label="KNOWLEDGE",
        verdict="approved",
        approved_cre_id="616-305",
        reviewer="prateek",
        reviewed_at=AT,
    )
    values.update(overrides)
    return ReviewVerdict(**values)


class JsonlCorrectionsLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "nested", "corrections.jsonl")

    def tearDown(self) -> None:
        self.dir.cleanup()

    def _lines(self):
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]

    def test_appends_one_json_line_per_verdict(self) -> None:
        log = JsonlCorrectionsLog(self.path)
        log.record(_verdict())
        log.record(
            _verdict(decision_row_id="row-2", verdict="rejected", approved_cre_id=None)
        )

        first, second = self._lines()
        self.assertEqual(first["decision_row_id"], "row-1")
        self.assertEqual(first["verdict"], "approved")
        self.assertEqual(first["approved_cre_id"], "616-305")
        self.assertEqual(first["schema_version"], CORRECTIONS_SCHEMA_VERSION)
        self.assertEqual(second["verdict"], "rejected")
        self.assertIsNone(second["approved_cre_id"])

    def test_survives_reopening_the_log(self) -> None:
        """Two service restarts, one file: earlier verdicts must remain."""
        JsonlCorrectionsLog(self.path).record(_verdict())
        JsonlCorrectionsLog(self.path).record(_verdict(decision_row_id="row-2"))

        self.assertEqual(
            [line["decision_row_id"] for line in self._lines()], ["row-1", "row-2"]
        )

    def test_reviewed_at_is_recorded_in_utc(self) -> None:
        from datetime import timedelta, timezone as tz

        ist = tz(timedelta(hours=5, minutes=30))
        JsonlCorrectionsLog(self.path).record(_verdict(reviewed_at=AT.astimezone(ist)))

        (line,) = self._lines()
        # Canonical form: naive UTC ISO, byte-identical to what decision_queue
        # stores, no offset suffix to strip before joining.
        self.assertEqual(line["reviewed_at"], "2026-09-17T12:00:00")

    def test_only_the_two_rfc_verdicts_are_representable(self) -> None:
        with self.assertRaises(ValidationError):
            _verdict(verdict="maybe")


if __name__ == "__main__":
    unittest.main()
