"""Tests for the corrections log: the durable half of a decision.

The property under test is not formatting, it is the retirement gate: what this
log records is what permits ``mark_reviewed`` to run, so a record must land
whole, survive reopening, match the pinned ``HumanDecision`` schema, and refuse
a decision that contradicts itself.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource

from application.utils.librarian.schemas import ProposedLink
from application.utils.reviewer import corrections_log
from application.utils.reviewer.corrections_log import (
    HumanDecision,
    JsonlCorrectionsLog,
    LossEvent,
    RejectionDetail,
    UiMeta,
)

AT = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
LINK = ProposedLink(cre_id="616-305", link_type="Related", confidence=1.0)
SCHEMA_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "docs",
    "owasp-graph",
    "apis",
    "schemas",
)


def _decision(**overrides) -> HumanDecision:
    values = dict(
        review_id="review:chk:1",
        chunk_id="chk:1",
        pipeline_run_id="run-1",
        decided_at=AT,
        decided_by="prateek",
        action="approve",
        final_links=[LINK],
    )
    values.update(overrides)
    return HumanDecision(**values)


def _rejected(**overrides) -> HumanDecision:
    return _decision(
        action="reject",
        final_links=None,
        rejection=RejectionDetail(reason_code="NOT_SECURITY"),
        **overrides,
    )


def _validator() -> Draft202012Validator:
    schemas = []
    for name in ("human-decision.json", "proposed-link.json"):
        with open(os.path.join(SCHEMA_DIR, name), encoding="utf-8") as fh:
            schemas.append(json.load(fh))
    registry = Registry().with_resources(
        [(s["$id"], Resource.from_contents(s)) for s in schemas]
    )
    return Draft202012Validator(schemas[0], registry=registry)


class HumanDecisionTest(unittest.TestCase):
    def test_all_three_contract_actions_are_representable(self) -> None:
        self.assertEqual("approve", _decision().action)
        self.assertEqual("correct", _decision(action="correct").action)
        self.assertEqual("reject", _rejected().action)

    def test_unknown_action_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            _decision(action="maybe")

    def test_contradictory_decisions_are_refused(self) -> None:
        for bad in (
            dict(final_links=None),
            dict(final_links=[]),
            dict(rejection=RejectionDetail(reason_code="X")),
            dict(action="reject"),
            dict(action="reject", rejection=RejectionDetail(reason_code="X")),
            dict(decided_by=""),
        ):
            with self.assertRaises(ValidationError, msg=bad):
                _decision(**bad)


class JsonlCorrectionsLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "nested", "corrections.jsonl")

    def tearDown(self) -> None:
        self.dir.cleanup()

    def _lines(self):
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]

    def test_every_line_matches_the_pinned_schema(self) -> None:
        """A dump with nulls or extra keys still looks like JSONL; only
        validating against the contract can catch it."""
        log = JsonlCorrectionsLog(self.path)
        log.record(_decision())
        log.record(_rejected())
        log.record(
            _decision(
                action="correct",
                ui=UiMeta(review_duration_ms=2100, keybind_used="c"),
                loss_event=LossEvent(
                    module="C",
                    input_snapshot={"text": "x"},
                    wrong_prediction={"cre_id": "111-111"},
                    correct_label={"cre_id": "616-305"},
                ),
            )
        )
        validator = _validator()
        for line in self._lines():
            self.assertEqual([], [e.message for e in validator.iter_errors(line)])

    def test_each_decision_gets_its_own_id(self) -> None:
        log = JsonlCorrectionsLog(self.path)
        log.record(_decision())
        log.record(_decision())
        first, second = self._lines()
        self.assertNotEqual(first["decision_id"], second["decision_id"])

    def test_survives_reopening_the_log(self) -> None:
        """Two service restarts, one file: earlier decisions must remain."""
        JsonlCorrectionsLog(self.path).record(_decision(review_id="r1"))
        JsonlCorrectionsLog(self.path).record(_decision(review_id="r2"))

        self.assertEqual([line["review_id"] for line in self._lines()], ["r1", "r2"])

    def test_decided_at_is_recorded_in_utc(self) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        JsonlCorrectionsLog(self.path).record(_decision(decided_at=AT.astimezone(ist)))

        (line,) = self._lines()
        self.assertEqual(line["decided_at"], "2026-09-17T12:00:00Z")

    def test_a_torn_last_line_does_not_swallow_the_next_record(self) -> None:
        log = JsonlCorrectionsLog(self.path)
        log.record(_decision(review_id="r1"))
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write('{"review_id": "torn')  # a crash mid-write
        log.record(_decision(review_id="r3"))

        with open(self.path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(3, len(lines))
        self.assertEqual("r3", json.loads(lines[2])["review_id"])

    def test_directory_entry_is_synced_up_the_chain(self) -> None:
        opened = []
        real_open = os.open

        def tracking_open(path, flags, *args, **kwargs):
            opened.append(path)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(corrections_log.os, "open", tracking_open):
            JsonlCorrectionsLog(self.path).record(_decision())
        parent = os.path.abspath(os.path.dirname(self.path))
        self.assertIn(parent, opened)
        self.assertIn(os.path.dirname(parent), opened)


if __name__ == "__main__":
    unittest.main()
