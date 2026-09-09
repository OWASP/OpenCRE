"""Unit tests for grounded shortlist judge (stub LLM — no network)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from application.utils.librarian.schemas import CreCandidate, RetrievalAudit
from application.utils.librarian.shortlist_judge import (
    ShortlistJudgeCache,
    candidates_from_audit,
    judge_shortlist,
    parse_judge_json,
)


class ParseJudgeJsonTest(unittest.TestCase):
    def test_valid_subset(self) -> None:
        allow = ["111-111", "222-222", "333-333"]
        self.assertEqual(
            parse_judge_json('["222-222", "111-111"]', allow),
            ["222-222", "111-111"],
        )

    def test_rejects_invented_ids(self) -> None:
        allow = ["111-111", "222-222"]
        self.assertEqual(
            parse_judge_json('["999-999", "111-111", "bogus"]', allow),
            ["111-111"],
        )

    def test_empty_on_bad_json(self) -> None:
        self.assertEqual(parse_judge_json("not json", ["111-111"]), [])
        self.assertEqual(parse_judge_json('{"no": "array"}', ["111-111"]), [])

    def test_wrapper_and_fences(self) -> None:
        raw = '```json\n{"cre_ids": ["111-111", "222-222", "111-111"]}\n```'
        self.assertEqual(
            parse_judge_json(raw, ["111-111", "222-222"]),
            ["111-111", "222-222"],
        )

    def test_caps_at_two(self) -> None:
        allow = ["a", "b", "c"]
        self.assertEqual(parse_judge_json('["a","b","c"]', allow), ["a", "b"])


class JudgeShortlistTest(unittest.TestCase):
    def test_stub_llm_returns_validated_ids(self) -> None:
        def llm(system: str, user: str) -> str:
            self.assertIn("Broken Access Control", user)
            return '["cre-a", "cre-invented"]'

        out = judge_shortlist(
            "Section: Broken Access Control",
            [
                {"cre_id": "cre-a", "name": "Access control"},
                {"cre_id": "cre-b", "name": "Other"},
            ],
            llm_fn=llm,
        )
        self.assertEqual(out, ["cre-a"])

    def test_llm_error_fail_open(self) -> None:
        def llm(system: str, user: str) -> str:
            raise RuntimeError("network down")

        out = judge_shortlist(
            "Section: X",
            [{"cre_id": "cre-a", "name": "A"}],
            llm_fn=llm,
        )
        self.assertEqual(out, [])

    def test_empty_query_or_candidates(self) -> None:
        def llm(system: str, user: str) -> str:
            raise AssertionError("should not call")

        self.assertEqual(judge_shortlist("", [{"cre_id": "a"}], llm_fn=llm), [])
        self.assertEqual(judge_shortlist("q", [], llm_fn=llm), [])

    def test_disk_cache_roundtrip(self) -> None:
        calls = {"n": 0}

        def llm(system: str, user: str) -> str:
            calls["n"] += 1
            return '["cre-a"]'

        with tempfile.TemporaryDirectory() as tmp:
            cache = ShortlistJudgeCache(disk_dir=Path(tmp))
            cands = [{"cre_id": "cre-a", "name": "A"}, {"cre_id": "cre-b", "name": "B"}]
            first = judge_shortlist("focus", cands, llm_fn=llm, cache=cache)
            second = judge_shortlist("focus", cands, llm_fn=llm, cache=cache)
            self.assertEqual(first, ["cre-a"])
            self.assertEqual(second, ["cre-a"])
            self.assertEqual(calls["n"], 1)


class CandidatesFromAuditTest(unittest.TestCase):
    def test_top_n_with_names(self) -> None:
        audit = RetrievalAudit(
            retriever="stub",
            candidates=[
                CreCandidate(cre_id="a", cre_name="Alpha", score_vector=0.9),
                CreCandidate(cre_id="b", cre_name="Beta", score_vector=0.8),
                CreCandidate(cre_id="c", score_vector=0.7),
            ],
            reranked=[],
            threshold=0.5,
        )
        rows = candidates_from_audit(audit, top_n=2)
        self.assertEqual(rows, [{"cre_id": "a", "name": "Alpha"}, {"cre_id": "b", "name": "Beta"}])


if __name__ == "__main__":
    unittest.main()
