"""#1078: runner that records /completion answers and scores them offline."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from application.utils.ask_eval.gold import load_gold
from application.utils.ask_eval.runner import (
    compare_reports,
    fetch_live,
    load_records,
    score_records,
    write_records,
)
from scripts import chat_eval_gold

GOLD = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "ask_regressions"
    / "chat_eval_gold.jsonl"
)

SAMM = {"name": "SAMM", "section": "Threat Assessment", "id": "068-102"}
CS = {"name": "Cheat_sheets", "section": "Threat Modeling", "id": "068-102"}


def _ok(answer, table, accurate=True):
    return {
        "status": 200,
        "body": {"response": answer, "table": table, "accurate": accurate},
    }


class UrllibPostTest(unittest.TestCase):
    def test_sends_named_user_agent(self) -> None:
        # Cloudflare answers urllib's default agent with 403 / error 1010.
        from unittest import mock

        from application.utils.ask_eval import runner

        resp = mock.MagicMock()
        resp.__enter__.return_value = resp
        resp.status = 200
        resp.read.return_value = b"{}"
        with mock.patch.object(
            runner.urllib.request, "urlopen", return_value=resp
        ) as op:
            runner._urllib_post("http://h/x", {"prompt": "q"}, {}, 5)
        req = op.call_args[0][0]
        self.assertEqual(req.get_header("User-agent"), runner.USER_AGENT)


class RunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        rows = load_gold(GOLD)
        self.rows = [r for r in rows if r.id in ("tm_people_samm", "refuse_off_topic")]

    def test_fetch_live_posts_prompt_with_bearer_and_records_errors(self) -> None:
        seen = []

        def post(url, body, headers, timeout):
            seen.append((url, body, dict(headers)))
            if len(seen) == 2:
                raise OSError("connection reset")
            return 200, {"response": "x", "table": [], "accurate": True}

        recs = fetch_live(self.rows, "http://h:5000/", token="t", post=post)
        self.assertEqual(seen[0][0], "http://h:5000/rest/v1/completion")
        self.assertEqual(seen[0][1], {"prompt": self.rows[0].question})
        self.assertEqual(seen[0][2], {"Authorization": "Bearer t"})
        self.assertEqual([r["id"] for r in recs], [r.id for r in self.rows])
        self.assertEqual(recs[1]["status"], 0)

    def test_errors_and_missing_stay_out_of_metrics(self) -> None:
        records = [{"id": "tm_people_samm", "status": 503, "body": {"error": "x"}}]
        rep = score_records(self.rows, records)
        self.assertEqual(rep["n"], 0)
        self.assertEqual(rep["errors"], {"tm_people_samm": 503})
        self.assertEqual(rep["missing"], ["refuse_off_topic"])

    def test_records_round_trip_and_score(self) -> None:
        records = [
            dict(id="tm_people_samm", **_ok("Per SAMM [1].", [SAMM])),
            dict(
                id="refuse_off_topic",
                **_ok("I couldn't find that in the indexed OWASP sources", [], False),
            ),
        ]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "run.jsonl"
            write_records(path, records)
            rep = score_records(self.rows, load_records(path))
        self.assertEqual(rep["passed"], 2)
        self.assertEqual(rep["failed"], [])
        self.assertTrue(all(c["passed"] for c in rep["cases"]))

    def test_compare_reports_lists_flips(self) -> None:
        before = score_records(
            self.rows, [dict(id="tm_people_samm", **_ok("Pick people [1].", [CS]))]
        )
        after = score_records(
            self.rows, [dict(id="tm_people_samm", **_ok("Per SAMM [1].", [SAMM]))]
        )
        cmp = compare_reports(before, after)
        self.assertEqual(cmp["fixed"], ["tm_people_samm"])
        self.assertEqual(cmp["broken"], [])
        self.assertEqual(cmp["metrics"]["cite_group_recall"], [0.0, 1.0])

    def test_script_scores_recordings_and_compares(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            base, cand, out = (Path(d) / n for n in ("a.jsonl", "b.jsonl", "o.json"))
            write_records(
                base, [dict(id="tm_people_samm", **_ok("Pick people [1].", [CS]))]
            )
            write_records(
                cand, [dict(id="tm_people_samm", **_ok("Per SAMM [1].", [SAMM]))]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = chat_eval_gold.main(
                    [
                        "--responses",
                        str(cand),
                        "--baseline",
                        str(base),
                        "--output-json",
                        str(out),
                    ]
                )
            report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertIn("== fixed: tm_people_samm", buf.getvalue())
        self.assertEqual(report["compare"]["fixed"], ["tm_people_samm"])

    def test_script_needs_exactly_one_mode(self) -> None:
        quiet = redirect_stderr(io.StringIO())
        with quiet, self.assertRaises(SystemExit):
            chat_eval_gold.main([])


if __name__ == "__main__":
    unittest.main()
