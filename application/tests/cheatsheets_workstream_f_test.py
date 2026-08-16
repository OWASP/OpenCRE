"""Tests for Cheat Sheet -> CRE mapping, Workstream F, checkpoints F1+F2.

F1: the suggestions.json data contract -- SUGGESTIONS_SCHEMA plus the
CandidateCRE / MappingSuggestion dataclasses.
F2: the read/write adapters -- write_suggestions_json and
load_approved_suggestions (schema-validate -> parse -> filter approved).

F3 (suggestions_to_parse_result) and F4/F5 (CLI) are deliberately out of scope
here; these tests never touch defs.Standard / ParseResult / Node_collection.
"""

import json
import os
import tempfile
import unittest

import jsonschema

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


if __name__ == "__main__":
    unittest.main()
