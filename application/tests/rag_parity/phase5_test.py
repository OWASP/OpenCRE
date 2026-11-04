"""Phase 5: knowledge_claim extract + quote verify."""

import unittest

from application.utils.rag_parity.phase5_claims import (
    claims_for_persist,
    extract_claims,
    quote_verified,
)


class QuoteVerifyTest(unittest.TestCase):
    def test_requires_verbatim_substring(self) -> None:
        source = "Verify that passwords are at least 12 characters in length."
        self.assertTrue(quote_verified("passwords are at least 12 characters", source))
        self.assertFalse(quote_verified("passwords must be 99 characters", source))


class ExtractClaimsTest(unittest.TestCase):
    def test_drops_bad_quotes_keeps_verified(self) -> None:
        source = (
            "Verify that passwords are at least 12 characters in length "
            "and that the application rejects common passwords."
        )

        def llm(system: str, user: str) -> str:
            return (
                '{"claims":['
                '{"claim":"Min password length 12",'
                '"quote":"passwords are at least 12 characters","confidence":0.9},'
                '{"claim":"Invented","quote":"not in source at all","confidence":0.9}'
                "]}"
            )

        drafts = extract_claims(source, llm_fn=llm, source_ref="ASVS:V2.1.1")
        statuses = {d.claim: d.status for d in drafts}
        self.assertEqual(statuses["Min password length 12"], "verified")
        self.assertEqual(statuses["Invented"], "dropped")
        persistable = claims_for_persist(drafts)
        self.assertEqual(len(persistable), 1)
        self.assertEqual(persistable[0].source_ref, "ASVS:V2.1.1")


if __name__ == "__main__":
    unittest.main()
