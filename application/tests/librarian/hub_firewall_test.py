import unittest

from application.utils.librarian.hub_firewall import HubRep, firewall, leaks


class TestHubFirewall(unittest.TestCase):
    def setUp(self):
        self.row = (
            "Verify that user-set passwords are at least 12 characters in length."
        )
        self.hub = [
            HubRep("764-507", "Some CRE text. " + self.row + " More context."),
            HubRep("311-369", "Session tokens must have the Secure attribute set."),
        ]

    def test_test_row_text_leaks_before_firewall(self):
        self.assertTrue(leaks(self.row, self.hub))

    def test_firewall_removes_leaking_rep_only(self):
        cleaned = firewall(self.row, self.hub)
        self.assertEqual([r.cre_id for r in cleaned], ["311-369"])
        # The whole point: the row's text is absent from the hub afterwards.
        self.assertFalse(leaks(self.row, cleaned))

    def test_firewall_is_whitespace_and_case_insensitive(self):
        hub = [
            HubRep(
                "1-2",
                "VERIFY THAT user-set   passwords are at least 12 characters in length.",
            )
        ]
        self.assertTrue(leaks(self.row, hub))
        self.assertEqual(firewall(self.row, hub), [])

    def test_empty_row_is_a_noop(self):
        self.assertFalse(leaks("", self.hub))
        self.assertEqual(firewall("", self.hub), self.hub)


if __name__ == "__main__":
    unittest.main()
