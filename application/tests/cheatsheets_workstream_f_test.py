"""Tests for Cheat Sheet -> CRE mapping, Workstream F, checkpoints F1+F2+F3.

F1: the suggestions.json data contract -- SUGGESTIONS_SCHEMA plus the
CandidateCRE / MappingSuggestion dataclasses.
F2: the read/write adapters -- write_suggestions_json and
load_approved_suggestions (schema-validate -> parse -> filter approved).
F3: the import adapter -- suggestions_to_parse_result (approved suggestions ->
ParseResult of defs.Standard with AutomaticallyLinkedTo links). F3's tests use a
lightweight Node_collection stub (get_CREs only) so no Postgres/Neo4j is needed.

F4/F5 (CLI) are deliberately out of scope here.
"""

import json
import os
import tempfile
import unittest

import jsonschema

from application.defs import cre_defs as defs
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.parsers import (
    cheatsheets_workstream_f as wf,
)

FIXTURES = os.path.join(
    os.path.dirname(__file__), "fixtures", "cheatsheets_workstream_f"
)
VALID_FIXTURE = os.path.join(FIXTURES, "suggestions_valid.json")
INVALID_FIXTURE = os.path.join(FIXTURES, "suggestions_invalid.json")


class TestSuggestionsSchema(unittest.TestCase):
    def test_valid_fixture_validates_against_schema(self) -> None:
        with open(VALID_FIXTURE, encoding="utf-8") as fh:
            doc = json.load(fh)
        # Must not raise.
        jsonschema.validate(instance=doc, schema=wf.SUGGESTIONS_SCHEMA)

    def test_invalid_fixture_fails_schema(self) -> None:
        with open(INVALID_FIXTURE, encoding="utf-8") as fh:
            doc = json.load(fh)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=doc, schema=wf.SUGGESTIONS_SCHEMA)


class TestLoadApprovedSuggestions(unittest.TestCase):
    def test_returns_only_approved_entries(self) -> None:
        approved = wf.load_approved_suggestions(VALID_FIXTURE)
        # Fixture has two approved + one "suggested"; only the approved survive.
        self.assertEqual(len(approved), 2)
        self.assertTrue(all(s.status == "approved" for s in approved))
        titles = {s.title for s in approved}
        self.assertEqual(
            titles,
            {"Authentication Cheat Sheet", "Cryptographic Storage Cheat Sheet"},
        )

    def test_parses_nested_candidate_cres(self) -> None:
        approved = wf.load_approved_suggestions(VALID_FIXTURE)
        auth = next(s for s in approved if s.title == "Authentication Cheat Sheet")
        self.assertEqual(len(auth.candidate_cres), 2)
        self.assertIsInstance(auth.candidate_cres[0], wf.CandidateCRE)
        self.assertEqual(auth.candidate_cres[0].cre_id, "764-507")

    def test_malformed_raises_field_named_error(self) -> None:
        with self.assertRaises(wf.SuggestionSchemaError) as ctx:
            wf.load_approved_suggestions(INVALID_FIXTURE)
        # The error must name the offending field so a reviewer can fix it.
        self.assertIn("title", str(ctx.exception))


class TestWriteRoundTrip(unittest.TestCase):
    def _sample(self) -> list:
        return [
            wf.MappingSuggestion(
                source="owasp_cheatsheets",
                cheatsheet_id="Authentication_Cheat_Sheet",
                title="Authentication Cheat Sheet",
                hyperlink=(
                    "https://cheatsheetseries.owasp.org/cheatsheets/"
                    "Authentication_Cheat_Sheet.html"
                ),
                category="authentication",
                status="approved",
                candidate_cres=[
                    wf.CandidateCRE(
                        cre_id="764-507",
                        score=0.91,
                        confidence="high",
                        reason="Direct overlap.",
                    ),
                ],
            ),
        ]

    def test_write_then_load_roundtrips(self) -> None:
        suggestions = self._sample()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "suggestions.json")
            wf.write_suggestions_json(path, suggestions)
            loaded = wf.load_approved_suggestions(path)
        self.assertEqual(loaded, suggestions)

    def test_write_is_deterministic(self) -> None:
        suggestions = self._sample()
        with tempfile.TemporaryDirectory() as d:
            p1 = os.path.join(d, "a.json")
            p2 = os.path.join(d, "b.json")
            wf.write_suggestions_json(p1, suggestions)
            wf.write_suggestions_json(p2, suggestions)
            with open(p1, encoding="utf-8") as fh:
                first = fh.read()
            with open(p2, encoding="utf-8") as fh:
                second = fh.read()
        self.assertEqual(first, second)

    def test_written_file_validates_against_schema(self) -> None:
        suggestions = self._sample()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "suggestions.json")
            wf.write_suggestions_json(path, suggestions)
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        jsonschema.validate(instance=doc, schema=wf.SUGGESTIONS_SCHEMA)


class _StubCache:
    """Minimal ``db.Node_collection`` stand-in exposing only ``get_CREs``.

    Known ids resolve to a ``defs.CRE`` (shaped like a real ``external_id`` --
    e.g. ``"764-507"`` -- exactly what the live cheatsheets parser passes);
    unknown ids return ``[]`` just like ``db.Node_collection.get_CREs``. No
    Postgres/Neo4j is touched.
    """

    def __init__(self, known):
        # known: dict of cre_id -> defs.CRE
        self._known = known

    def get_CREs(self, external_id=None, **kwargs):
        cre = self._known.get(external_id)
        # Return a fresh copy per call, mirroring the DB (which hydrates anew).
        return [cre.shallow_copy()] if cre is not None else []


def _cre(external_id):
    return defs.CRE(id=external_id, name=f"CRE {external_id}")


def _cand(cre_id):
    return wf.CandidateCRE(cre_id=cre_id, score=0.9, confidence="high", reason="r")


def _sugg(title, candidate_ids, category="authentication", status="approved"):
    slug = title.replace(" ", "_")
    return wf.MappingSuggestion(
        source="owasp_cheatsheets",
        cheatsheet_id=slug,
        title=title,
        hyperlink=f"https://cheatsheetseries.owasp.org/cheatsheets/{slug}.html",
        category=category,
        status=status,
        candidate_cres=[_cand(c) for c in candidate_ids],
    )


class TestSuggestionsToParseResult(unittest.TestCase):
    def test_builds_standards_with_links(self) -> None:
        cache = _StubCache({"764-507": _cre("764-507")})
        approved = [_sugg("Authentication Cheat Sheet", ["764-507"])]

        result = wf.suggestions_to_parse_result(approved, cache)

        self.assertIsInstance(result, base_parser_defs.ParseResult)
        standards = result.results["OWASP Cheat Sheets"]
        self.assertEqual(len(standards), 1)
        std = standards[0]
        self.assertIsInstance(std, defs.Standard)
        self.assertEqual(std.name, "OWASP Cheat Sheets")
        self.assertEqual(std.section, "Authentication Cheat Sheet")
        self.assertEqual(
            std.hyperlink,
            "https://cheatsheetseries.owasp.org/cheatsheets/"
            "Authentication_Cheat_Sheet.html",
        )
        self.assertEqual(len(std.links), 1)
        link = std.links[0]
        self.assertEqual(link.ltype, defs.LinkTypes.AutomaticallyLinkedTo)
        self.assertEqual(link.document.id, "764-507")

    def test_classification_tags_present_and_valid(self) -> None:
        cache = _StubCache({"764-507": _cre("764-507")})
        approved = [_sugg("Authentication Cheat Sheet", ["764-507"])]

        result = wf.suggestions_to_parse_result(approved, cache)

        # The import pipeline requires the full classification tag set.
        base_parser_defs.validate_classification_tags(result.results)
        std = result.results["OWASP Cheat Sheets"][0]
        self.assertIn(base_parser_defs.Family.GUIDANCE.value, std.tags)
        self.assertIn(base_parser_defs.Subtype.CHEATSHEET.value, std.tags)
        self.assertIn(base_parser_defs.Audience.DEVELOPER.value, std.tags)
        self.assertIn(base_parser_defs.Maturity.STABLE.value, std.tags)
        self.assertIn("source:owasp_cheatsheets", std.tags)
        # category is carried as an extra tag.
        self.assertIn("authentication", std.tags)

    def test_unknown_cre_id_skipped_sibling_still_linked(self) -> None:
        cache = _StubCache({"764-507": _cre("764-507")})
        # One known sibling, one unknown id on the same suggestion.
        approved = [_sugg("Authentication Cheat Sheet", ["764-507", "999-999"])]

        with self.assertLogs(wf.logger, level="WARNING") as cm:
            result = wf.suggestions_to_parse_result(approved, cache)

        standards = result.results["OWASP Cheat Sheets"]
        self.assertEqual(len(standards), 1)
        self.assertEqual([link.document.id for link in standards[0].links], ["764-507"])
        # The skipped id is reported for the reviewer.
        self.assertIn("999-999", "\n".join(cm.output))

    def test_all_unknown_candidates_drops_standard(self) -> None:
        cache = _StubCache({"764-507": _cre("764-507")})
        approved = [_sugg("Ghost Cheat Sheet", ["111-111", "222-222"])]

        result = wf.suggestions_to_parse_result(approved, cache)

        # A Standard with zero resolved links is omitted entirely.
        self.assertEqual(result.results["OWASP Cheat Sheets"], [])

    def test_deterministic_output(self) -> None:
        cache = _StubCache({"764-507": _cre("764-507"), "581-525": _cre("581-525")})
        approved = [
            _sugg("Authentication Cheat Sheet", ["764-507"]),
            _sugg("Cryptographic Storage Cheat Sheet", ["581-525", "764-507"]),
        ]

        first = wf.suggestions_to_parse_result(approved, cache)
        second = wf.suggestions_to_parse_result(approved, cache)

        self.assertEqual(first.results, second.results)

    def test_duplicate_candidate_ids_yield_single_link(self) -> None:
        # Two candidates on one suggestion resolving to the SAME cre_id must not
        # raise DuplicateLinkException -- the has_link guard collapses them.
        cache = _StubCache({"764-507": _cre("764-507")})
        approved = [_sugg("Authentication Cheat Sheet", ["764-507", "764-507"])]

        result = wf.suggestions_to_parse_result(approved, cache)

        std = result.results["OWASP Cheat Sheets"][0]
        self.assertEqual(len(std.links), 1)
        self.assertEqual(std.links[0].document.id, "764-507")

    def test_blank_category_produces_no_extra_tag(self) -> None:
        # Empty AND whitespace-only categories (both schema-valid) must not leak
        # a blank/whitespace extra tag.
        for blank in ("", "   "):
            with self.subTest(category=repr(blank)):
                cache = _StubCache({"764-507": _cre("764-507")})
                approved = [
                    _sugg("Authentication Cheat Sheet", ["764-507"], category=blank)
                ]

                result = wf.suggestions_to_parse_result(approved, cache)

                # Still a valid, classifiable Standard...
                base_parser_defs.validate_classification_tags(result.results)
                std = result.results["OWASP Cheat Sheets"][0]
                # ...with no blank/whitespace tag leaked in from the category.
                self.assertNotIn("", std.tags)
                self.assertNotIn(blank, std.tags)
                # Only the five required classification tags remain (no extra).
                self.assertEqual(len(std.tags), 5)

    def test_category_tag_is_stripped(self) -> None:
        cache = _StubCache({"764-507": _cre("764-507")})
        approved = [
            _sugg("Authentication Cheat Sheet", ["764-507"], category="  auth  ")
        ]

        result = wf.suggestions_to_parse_result(approved, cache)

        std = result.results["OWASP Cheat Sheets"][0]
        self.assertIn("auth", std.tags)
        self.assertNotIn("  auth  ", std.tags)


if __name__ == "__main__":
    unittest.main()
