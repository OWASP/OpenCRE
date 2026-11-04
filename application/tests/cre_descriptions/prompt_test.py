"""Prompt builder for one-shot CRE description generation."""

import hashlib
import json
import unittest

from application.utils.cre_descriptions.prompt import (
    build_description_prompt,
    compute_prompt_hash,
    parse_description_text,
)


class BuildDescriptionPromptTest(unittest.TestCase):
    def test_user_json_includes_cre_id_name_and_grounding(self) -> None:
        system, user = build_description_prompt(
            cre_id="111-111",
            name="Stored secrets",
            linked_prose=["Render PAN unreadable with strong crypto."],
            neighbour_names=["Key management"],
        )
        payload = json.loads(user)
        self.assertEqual(payload["cre_id"], "111-111")
        self.assertEqual(payload["name"], "Stored secrets")
        self.assertIn("Render PAN", payload["linked_prose"][0])
        self.assertEqual(payload["neighbour_names"], ["Key management"])
        lower = system.lower()
        self.assertIn("junk", lower)
        self.assertIn("nist", lower)
        self.assertIn("description", lower)

    def test_works_with_no_grounding(self) -> None:
        system, user = build_description_prompt(
            cre_id="222-222",
            name="Sessions",
            linked_prose=[],
            neighbour_names=[],
        )
        self.assertTrue(system)
        payload = json.loads(user)
        self.assertEqual(payload["linked_prose"], [])
        self.assertEqual(payload["neighbour_names"], [])


class ParseDescriptionTextTest(unittest.TestCase):
    def test_parses_json_description(self) -> None:
        raw = '{"description": "Protect stored credentials with encryption."}'
        self.assertEqual(
            parse_description_text(raw),
            "Protect stored credentials with encryption.",
        )

    def test_strips_fenced_json(self) -> None:
        raw = '```json\n{"description": "Bound session cookies."}\n```'
        self.assertEqual(parse_description_text(raw), "Bound session cookies.")

    def test_falls_back_to_raw_text(self) -> None:
        self.assertEqual(
            parse_description_text("Plain sentence about MFA."),
            "Plain sentence about MFA.",
        )


class PromptHashTest(unittest.TestCase):
    def test_stable_sha256(self) -> None:
        h1 = compute_prompt_hash("sys", "user")
        h2 = compute_prompt_hash("sys", "user")
        self.assertEqual(h1, h2)
        expected = hashlib.sha256(b"sys\n---\nuser").hexdigest()
        self.assertEqual(h1, expected)

    def test_changes_when_prompt_changes(self) -> None:
        self.assertNotEqual(
            compute_prompt_hash("a", "b"),
            compute_prompt_hash("a", "c"),
        )


if __name__ == "__main__":
    unittest.main()
