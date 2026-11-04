"""Hermetic tests for LC structured extract helpers."""

from __future__ import annotations

import unittest


class LcExtractSlugsTest(unittest.TestCase):
    def test_parses_menu_slugs(self) -> None:
        from application.utils.comprehension.lc_extract import extract_project_slugs

        def llm(system: str, user: str) -> str:
            return '{"slugs":["owasp-asvs","nope"]}'

        out = extract_project_slugs(
            "Tell me about ASVS",
            [("owasp-asvs", "asvs"), ("owasp-top-ten", "top ten")],
            llm=llm,
        )
        self.assertEqual(out, ["owasp-asvs"])

    def test_none_on_bad_json(self) -> None:
        from application.utils.comprehension.lc_extract import extract_project_slugs

        def llm(system: str, user: str) -> str:
            return "not-json"

        self.assertIsNone(extract_project_slugs("q", [("a", "a")], llm=llm))


class LcExtractPlanTest(unittest.TestCase):
    def test_parses_plan_flags(self) -> None:
        from application.utils.comprehension.lc_extract import extract_answer_plan

        def llm(system: str, user: str) -> str:
            return (
                '{"multipart":true,"people_route":false,'
                '"count_route":true,"cre_style":false}'
            )

        plan = extract_answer_plan("How many leaders and also where?", llm=llm)
        self.assertEqual(
            plan,
            {
                "multipart": True,
                "people_route": False,
                "count_route": True,
                "cre_style": False,
            },
        )


class MatchedSlugsLcTest(unittest.TestCase):
    def test_uses_extract_when_available(self) -> None:
        from unittest import mock

        from application.utils.comprehension import retrieve

        with mock.patch(
            "application.utils.comprehension.lc_extract.extract_project_slugs",
            return_value=["owasp-asvs"],
        ):
            with mock.patch.object(retrieve, "_external_aliases", return_value={}):
                out = retrieve.matched_slugs(
                    "ASVS please", ["owasp-asvs", "owasp-top-ten"], limit=2
                )
        self.assertEqual(out, ["owasp-asvs"])

    def test_phrase_fallback_when_extract_none(self) -> None:
        from unittest import mock

        from application.utils.comprehension import retrieve

        with mock.patch(
            "application.utils.comprehension.lc_extract.extract_project_slugs",
            return_value=None,
        ):
            with mock.patch.object(retrieve, "_external_aliases", return_value={}):
                out = retrieve.matched_slugs(
                    "what does the asvs say", ["owasp-asvs"], limit=1
                )
        self.assertEqual(out, ["owasp-asvs"])


if __name__ == "__main__":
    unittest.main()
