"""#1078: hermetic side of the faithfulness eval (no LLM, fake judge)."""

from __future__ import annotations

import asyncio
import unittest

from application.utils.ask_eval.faithfulness import (
    SNIPPET_CAP,
    Statement,
    clean_answer,
    evidence_passages,
    faithfulness_inputs,
    judge_inputs,
    summarize_faithfulness,
)
from application.utils.ask_eval.gold import ABSTAIN_PREFIX, GoldRow


def _row(rid, expect="answer"):
    return GoldRow(id=rid, family="practice", question=f"q {rid}", expect=expect)


def _body(answer, snippets, accurate=True):
    return {
        "response": answer,
        "accurate": accurate,
        "table": [],
        "owasp_agent": {
            "citations": [f"https://example.org/{i}" for i in range(len(snippets))],
            "data": {
                "evidence": [{"n": i + 1, "snippet": s} for i, s in enumerate(snippets)]
            },
        },
    }


def _rec(rid, body, status=200):
    return {"id": rid, "status": status, "body": body}


class CleanAnswerTest(unittest.TestCase):
    def test_strips_label_and_markers(self):
        self.assertEqual(
            clean_answer("Answer: Hash passwords [1][2]. Use a salt [3]."),
            "Hash passwords. Use a salt.",
        )


class EvidencePassagesTest(unittest.TestCase):
    def test_reads_snippets_and_skips_blank(self):
        body = _body("a", ["one", "  ", "two"])
        self.assertEqual(evidence_passages(body), ["one", "two"])

    def test_missing_agent_block_is_empty(self):
        self.assertEqual(evidence_passages({"response": "a"}), [])


class FaithfulnessInputsTest(unittest.TestCase):
    def test_selects_judgeable_rows_and_explains_skips(self):
        rows = [
            _row("ok"),
            _row("refusal", expect="abstain"),
            _row("missing"),
            _row("http"),
            _row("abstained"),
            _row("no_passages"),
        ]
        records = [
            _rec("ok", _body("Answer: Hash it [1].", ["x" * SNIPPET_CAP, "short"])),
            _rec("refusal", _body(ABSTAIN_PREFIX, [])),
            _rec("http", {"error": "boom"}, status=503),
            _rec("abstained", _body(ABSTAIN_PREFIX, ["p"], accurate=False)),
            _rec("no_passages", _body("Answer: something", [])),
        ]
        inputs, skipped = faithfulness_inputs(rows, records)

        self.assertEqual([i.id for i in inputs], ["ok"])
        self.assertEqual(inputs[0].answer, "Hash it.")
        self.assertEqual(inputs[0].question, "q ok")
        self.assertEqual(inputs[0].truncated_passages, 1)
        self.assertEqual(
            skipped,
            {
                "refusal": "refusal row",
                "missing": "no record",
                "http": "http 503",
                "abstained": "answer abstained",
                "no_passages": "no passage text in response",
            },
        )


class JudgeAndSummaryTest(unittest.TestCase):
    def test_scores_errors_and_summary(self):
        rows = [_row("good"), _row("half"), _row("boom")]
        records = [
            _rec("good", _body("Answer: a", ["p"])),
            _rec("half", _body("Answer: b", ["p", "x" * SNIPPET_CAP])),
            _rec("boom", _body("Answer: c", ["p"])),
        ]
        inputs, _ = faithfulness_inputs(rows, records)

        async def judge(question, answer, passages):
            if answer == "c":
                raise RuntimeError("judge down")
            if answer == "a":
                return [Statement("a1", True), Statement("a2", True)]
            return [Statement("b1", True), Statement("b2", False)]

        results = asyncio.run(judge_inputs(inputs, judge))
        by_id = {r.id: r for r in results}
        self.assertEqual(by_id["good"].score, 1.0)
        self.assertEqual(by_id["half"].score, 0.5)
        self.assertEqual(by_id["half"].unsupported, ["b2"])
        self.assertIsNone(by_id["boom"].score)
        self.assertIn("judge down", by_id["boom"].error)

        summary = summarize_faithfulness(results)
        self.assertEqual(summary["judged"], 2)
        self.assertEqual(summary["mean_faithfulness"], 0.75)
        self.assertEqual(summary["statements"], 4)
        self.assertEqual(summary["supported_statements"], 3)
        self.assertEqual(summary["fully_faithful"], ["good"])
        self.assertEqual(summary["below_one"], {"half": 0.5})
        self.assertEqual(summary["passages"], 4)
        self.assertEqual(summary["truncated_passages"], 1)
        self.assertEqual(list(summary["errors"]), ["boom"])

    def test_no_claims_is_unscored_not_perfect(self):
        inputs, _ = faithfulness_inputs([_row("x")], [_rec("x", _body("a", ["p"]))])

        async def judge(question, answer, passages):
            return []

        results = asyncio.run(judge_inputs(inputs, judge))
        self.assertIsNone(results[0].score)
        self.assertEqual(summarize_faithfulness(results)["judged"], 0)


if __name__ == "__main__":
    unittest.main()
