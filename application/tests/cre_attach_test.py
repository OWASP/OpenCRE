import unittest
from unittest import mock

from application.utils.owasp_agent import service


def _resp(kind="evidence", accurate=True, table=None):
    return {
        "response": "Answer: x",
        "accurate": accurate,
        "table": table if table is not None else [],
        "owasp_agent": {"kind": kind, "citations": ["https://a/1"]},
    }


class TestAttachClosestCre(unittest.TestCase):
    def test_evidence_answer_gets_the_closest_cre_first(self):
        row = {"doctype": "CRE", "id": "123-456", "name": "Input validation"}
        with mock.patch.object(service, "closest_cre_rows", return_value=[row]):
            out = service.attach_closest_cre(
                "q", _resp(table=[{"doctype": "Standard"}])
            )
        self.assertEqual(out["table"][0], row)
        self.assertEqual(len(out["table"]), 2)
        self.assertEqual(
            out["owasp_agent"]["citations"][-1], "https://opencre.org/cre/123-456"
        )
        self.assertEqual(
            out["owasp_agent"]["citations"][0], "https://a/1"
        )  # [n] markers stay valid

    def test_other_kinds_abstentions_and_no_match_are_untouched(self):
        row = {"doctype": "CRE", "id": "1-2"}
        with mock.patch.object(service, "closest_cre_rows", return_value=[row]):
            self.assertEqual(
                service.attach_closest_cre("q", _resp(kind="chapter_lookup"))["table"],
                [],
            )
            self.assertEqual(
                service.attach_closest_cre("q", _resp(accurate=False))["table"], []
            )
        with mock.patch.object(service, "closest_cre_rows", return_value=[]):
            self.assertEqual(service.attach_closest_cre("q", _resp())["table"], [])

    def test_lookup_failure_never_breaks_the_answer(self):
        with mock.patch(
            "application.utils.comprehension.shared.shared_handler",
            side_effect=RuntimeError("boom"),
        ):
            self.assertEqual(service.closest_cre_rows("q"), [])


class TestEncodeCitationUrls(unittest.TestCase):
    def test_spaces_in_urls_are_encoded_and_positions_kept(self):
        resp = {"owasp_agent": {"citations": ["https://x/a b.md", "https://y/ok"]}}
        out = service.encode_citation_urls(resp)
        self.assertEqual(
            out["owasp_agent"]["citations"], ["https://x/a%20b.md", "https://y/ok"]
        )

    def test_clean_responses_are_returned_unchanged(self):
        resp = {"owasp_agent": {"citations": ["https://y/ok"]}}
        self.assertIs(service.encode_citation_urls(resp), resp)
        self.assertEqual(service.encode_citation_urls("x"), "x")


if __name__ == "__main__":
    unittest.main()
