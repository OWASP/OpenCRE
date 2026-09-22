"""Tests for C.0.4 problem-class classification (DB-backed taxonomy index)."""

import unittest

from application.tests.librarian.oie_taxonomy_fixtures import fixture_taxonomy_index
from application.utils.librarian.oie_taxonomy import set_default_taxonomy_index
from application.utils.librarian.problem_class import classify_problem


class ClassifyProblemTest(unittest.TestCase):
    def setUp(self) -> None:
        set_default_taxonomy_index(fixture_taxonomy_index())

    def tearDown(self) -> None:
        set_default_taxonomy_index(None)

    def test_section_id_auth(self) -> None:
        text = (
            "Standard: owasp_top10_2025\n"
            "Source: A07.txt\n"
            "Section-ID: A07\n"
            "Section: Authentication Failures\n\n"
            "Body about login."
        )
        pc = classify_problem(text)
        self.assertEqual(pc.class_id, "authentication")
        self.assertEqual(pc.family, "auth")
        self.assertEqual(pc.section_id, "A07")

    def test_section_id_access(self) -> None:
        pc = classify_problem("Section-ID: A01\nSection: Broken Access Control\n")
        self.assertEqual(pc.class_id, "access_control")
        self.assertEqual(pc.family, "access")

    def test_section_id_a02_is_configuration_not_appsec_blob(self) -> None:
        pc = classify_problem("Section-ID: A02\nSection: Security Misconfiguration\n")
        self.assertEqual(pc.class_id, "configuration")
        self.assertEqual(pc.family, "configuration")

    def test_api7_ssrf(self) -> None:
        pc = classify_problem(
            "Section-ID: API7\nSection: Server Side Request Forgery\n"
        )
        self.assertEqual(pc.class_id, "ssrf")
        self.assertEqual(pc.family, "ssrf")

    def test_llm_fine_class(self) -> None:
        pc = classify_problem("Section-ID: LLM01\nSection: Prompt Injection\n")
        self.assertEqual(pc.class_id, "prompt_injection")
        self.assertEqual(pc.family, "ai")

    def test_llm10_not_generic_ai_risk(self) -> None:
        pc = classify_problem("Section-ID: LLM10\nSection: Unbounded Consumption\n")
        self.assertEqual(pc.class_id, "unbounded_consumption")
        self.assertEqual(pc.family, "ai")

    def test_k08_secrets(self) -> None:
        pc = classify_problem("Section-ID: K08\nSection: Secrets Management Failures\n")
        self.assertEqual(pc.class_id, "secrets_management")
        self.assertEqual(pc.family, "cloud")

    def test_body_llm_token_alone_does_not_force_ai(self) -> None:
        # Bare "LLM" without prompt-injection phrase → standard family only.
        pc = classify_problem(
            "Standard: owasp_asvs\nSection: Something\n\nMentions LLM in passing."
        )
        self.assertEqual(pc.class_id, "general")
        self.assertEqual(pc.family, "appsec")

    def test_keyword_title_crypto(self) -> None:
        pc = classify_problem("Section: Encrypt data at rest with AES\n")
        self.assertEqual(pc.class_id, "cryptography")
        self.assertEqual(pc.family, "crypto")

    def test_standard_family_default(self) -> None:
        pc = classify_problem("Standard: owasp_ccm_v4\nSource: x.md\n\nHello.")
        self.assertEqual(pc.family, "cloud")
        self.assertEqual(pc.class_id, "general")

    def test_source_filename_section_id(self) -> None:
        pc = classify_problem(
            "Standard: OWASP Top 10\nVersion: 2025\nSource: A05.txt\nSection-ID: A05\n"
        )
        self.assertEqual(pc.class_id, "injection")
        self.assertEqual(pc.section_id, "A05")
        self.assertEqual(pc.family, "injection")

    def test_source_beats_polluted_section_id_line(self) -> None:
        # Nav pollution lists A01 first; Source stem must win.
        text = (
            "Source: A05.txt\n"
            "Section-ID: A01, A02, A03, A04, A05, A06\n"
            "Section: Injection\n"
        )
        pc = classify_problem(text)
        self.assertEqual(pc.class_id, "injection")
        self.assertEqual(pc.section_id, "A05")


if __name__ == "__main__":
    unittest.main()
