"""Orchestration helpers for one-shot CRE description generation."""

import unittest
from typing import List, Tuple

from application.utils.cre_descriptions.generate import (
    CreDescriptionInput,
    propose_descriptions,
    should_skip,
)
from application.utils.cre_descriptions.table import ApprovalRow


class ShouldSkipTest(unittest.TestCase):
    def test_skips_non_empty_unless_force(self) -> None:
        self.assertTrue(should_skip("already filled", force=False))
        self.assertFalse(should_skip("already filled", force=True))
        self.assertFalse(should_skip("", force=False))
        self.assertFalse(should_skip("   ", force=False))


class ProposeDescriptionsTest(unittest.TestCase):
    def test_dry_run_emits_rows_without_calling_llm(self) -> None:
        calls: List[Tuple[str, str]] = []

        def llm(system: str, user: str) -> str:
            calls.append((system, user))
            return '{"description": "should not be used"}'

        rows = propose_descriptions(
            [
                CreDescriptionInput(
                    cre_id="111-111",
                    name="Stored secrets",
                    existing_description="",
                    linked_prose=[
                        "Requirement 3.4: Render PAN unreadable anywhere it is stored "
                        "by using strong cryptography, truncation, or index tokens so that "
                        "a compromise of one store does not expose the full primary account number."
                    ],
                    neighbour_names=["Key management"],
                )
            ],
            llm_fn=llm,
            model="test-model",
            dry_run=True,
        )
        self.assertEqual(calls, [])
        self.assertEqual(len(rows), 1)
        self.assertIsInstance(rows[0], ApprovalRow)
        self.assertEqual(rows[0].cre_id, "111-111")
        self.assertEqual(rows[0].proposed_description, "")
        self.assertEqual(rows[0].model, "test-model")
        self.assertTrue(rows[0].prompt_hash)
        self.assertIn("Render PAN", rows[0].grounding_snippet)

    def test_mocked_llm_fills_description(self) -> None:
        def llm(system: str, user: str) -> str:
            self.assertIn("Stored secrets", user)
            return '{"description": "Encrypt secrets at rest using strong crypto."}'

        rows = propose_descriptions(
            [
                CreDescriptionInput(
                    cre_id="111-111",
                    name="Stored secrets",
                    existing_description="",
                    linked_prose=[
                        "Requirement 3.4: Render PAN unreadable anywhere it is stored "
                        "by using strong cryptography, truncation, or index tokens so that "
                        "a compromise of one store does not expose the full primary account number."
                    ],
                    neighbour_names=[],
                )
            ],
            llm_fn=llm,
            model="mock-model",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0].proposed_description,
            "Encrypt secrets at rest using strong crypto.",
        )
        self.assertEqual(rows[0].model, "mock-model")

    def test_skips_existing_description_unless_force(self) -> None:
        calls: List[str] = []

        def llm(system: str, user: str) -> str:
            calls.append(user)
            return '{"description": "new"}'

        records = [
            CreDescriptionInput(
                cre_id="1",
                name="A",
                existing_description="old",
                linked_prose=[],
                neighbour_names=[],
            ),
            CreDescriptionInput(
                cre_id="2",
                name="B",
                existing_description="",
                linked_prose=[],
                neighbour_names=[],
            ),
        ]
        rows = propose_descriptions(records, llm_fn=llm, model="m")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].cre_id, "2")
        self.assertEqual(len(calls), 1)

        rows_force = propose_descriptions(records, llm_fn=llm, model="m", force=True)
        self.assertEqual(len(rows_force), 2)

    def test_limit_caps_rows(self) -> None:
        def llm(system: str, user: str) -> str:
            return '{"description": "x"}'

        records = [
            CreDescriptionInput(
                cre_id=str(i),
                name=f"N{i}",
                existing_description="",
                linked_prose=[],
                neighbour_names=[],
            )
            for i in range(5)
        ]
        rows = propose_descriptions(records, llm_fn=llm, model="m", limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r.cre_id for r in rows], ["0", "1"])

    def test_skips_when_only_junk_grounding_still_prompts_on_name(self) -> None:
        junk = (
            "An official website of the United States government "
            "skip to content navigation menu unauthorized frame window "
            "You have JavaScript disabled."
        )

        def llm(system: str, user: str) -> str:
            self.assertIn("Sessions", user)
            return '{"description": "Manage authenticated sessions securely."}'

        rows = propose_descriptions(
            [
                CreDescriptionInput(
                    cre_id="333-333",
                    name="Sessions",
                    existing_description="",
                    linked_prose=[junk],
                    neighbour_names=[],
                )
            ],
            llm_fn=llm,
            model="m",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0].proposed_description,
            "Manage authenticated sessions securely.",
        )
        # Junk filtered out of grounding snippet
        self.assertNotIn("united states government", rows[0].grounding_snippet.lower())


if __name__ == "__main__":
    unittest.main()
