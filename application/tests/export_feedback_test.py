import unittest
from datetime import datetime, timedelta

from scripts.export_feedback import build_candidates


def row(i, q, rated, comment="wrong"):
    return {
        "id": i,
        "source": "chat",
        "question": q,
        "answer": "an answer",
        "citations": ["u"],
        "comment": comment,
        "rated_at": rated,
        "flags": "LONGCTX",
    }


class ExportFeedbackTest(unittest.TestCase):
    def test_candidates_are_deduped_recent_and_free_of_emails(self):
        now = datetime(2026, 10, 24, 12, 0)
        rows = [
            row(
                "1",
                "Who leads SAMM? mail me at jane@owasp.org",
                now.isoformat(),
                "bad, ask bob@x.org",
            ),
            row(
                "2",
                "who leads  SAMM? MAIL me at jane@owasp.org",
                (now - timedelta(hours=1)).isoformat(),
            ),  # same question
            row("3", "Old question", (now - timedelta(days=30)).isoformat()),
            row("4", "How many levels in ASVS?", (now - timedelta(days=1)).isoformat()),
        ]
        out = build_candidates(rows, since=now - timedelta(days=7))
        self.assertEqual([c["answer_id"] for c in out], ["1", "4"])
        blob = str(out)
        self.assertNotIn("jane@owasp.org", blob)
        self.assertNotIn("bob@x.org", blob)
        self.assertEqual(out[0]["reference"], "")
        self.assertFalse(out[0]["flawed"])

    def test_without_a_cutoff_everything_distinct_is_kept(self):
        rows = [row("1", "Q one", None), row("2", "Q two", None)]
        self.assertEqual(len(build_candidates(rows)), 2)
