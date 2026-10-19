import os
import unittest

from application import create_app, sqla
from application.utils import answer_feedback as af


class AnswerFeedbackTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["NO_LOAD_GRAPH_DB"] = "1"
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        os.environ.pop("ANSWER_LOG_ENABLED", None)
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_log_then_rate_and_change_rating(self) -> None:
        aid = af.log_answer(
            source="mcp",
            question="How many levels in SAMM?",
            answer="Three [1]",
            citations=["https://x/a"],
            channel="owasp_meta",
        )
        self.assertTrue(aid)
        self.assertEqual(af.record_rating(aid, "UP", " nice ")["rating"], "up")
        self.assertEqual(af.record_rating(aid, "down")["rating"], "down")
        rows = af.list_feedback()
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (rows[0]["rating"], rows[0]["comment"], rows[0]["citations"]),
            ("down", None, ["https://x/a"]),
        )
        self.assertEqual(af.list_feedback(rating="up"), [])

    def test_rejects_bad_input(self) -> None:
        aid = af.log_answer(source="chat", question="q", answer="a")
        with self.assertRaises(ValueError):
            af.record_rating(aid, "meh")
        with self.assertRaises(ValueError):
            af.record_rating("", "up")
        with self.assertRaises(LookupError):
            af.record_rating("no-such-id", "up")

    def test_logging_can_be_switched_off_and_never_raises(self) -> None:
        os.environ["ANSWER_LOG_ENABLED"] = "0"
        self.assertIsNone(af.log_answer(source="mcp", question="q", answer="a"))
        os.environ["ANSWER_LOG_ENABLED"] = "1"
        sqla.drop_all()  # table missing: must be swallowed, not raised
        self.assertIsNone(af.log_answer(source="mcp", question="q", answer="a"))
        sqla.create_all()

    def test_attach_answer_id_adds_id_only_when_logged(self) -> None:
        out = af.attach_answer_id(
            {"message": "m", "citations": ["c"], "channel": "x"},
            question="q",
            source="mcp",
        )
        self.assertIn("answer_id", out)
        os.environ["ANSWER_LOG_ENABLED"] = "0"
        self.assertNotIn(
            "answer_id",
            af.attach_answer_id({"message": "m"}, question="q", source="mcp"),
        )


if __name__ == "__main__":
    unittest.main()


class McpRatingTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["NO_LOAD_GRAPH_DB"] = "1"
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_ask_result_carries_id_that_rate_answer_accepts(self) -> None:
        from unittest import mock

        from application.mcp import ask as ask_mod

        fake = {
            "ok": True,
            "channel": "owasp_meta",
            "message": "SAMM has 3 levels",
            "citations": ["https://x"],
        }
        with mock.patch.object(ask_mod, "_ask_impl", return_value=fake):
            out = ask_mod.ask("how many levels in samm?")
        self.assertIn("answer_id", out)
        self.assertEqual(
            ask_mod.rate_answer(out["answer_id"], "up", "correct")["rating"], "up"
        )
        with self.assertRaises(KeyError):
            ask_mod.rate_answer("nope", "up")

    def test_rate_tool_is_listed_and_dispatches(self) -> None:
        from application.mcp import server
        from application.utils import answer_feedback as af_mod

        aid = af_mod.log_answer(source="mcp", question="q", answer="a")
        out = server.dispatch_tool(
            "rate_answer", {"answer_id": aid, "rating": "down", "comment": "wrong"}
        )
        self.assertEqual(out["rating"], "down")
