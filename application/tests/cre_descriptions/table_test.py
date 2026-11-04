"""Approval table writers for CRE description generation."""

import csv
import tempfile
import unittest
from pathlib import Path

from application.utils.cre_descriptions.table import (
    APPROVAL_COLUMNS,
    ApprovalRow,
    write_approval_csv,
    write_approval_markdown,
)


def _row(**overrides: str) -> ApprovalRow:
    base = {
        "cre_id": "111-111",
        "name": "Stored secrets",
        "proposed_description": "Encrypt secrets at rest.",
        "grounding_snippet": "PCI 3.4 | neighbour: Key management",
        "model": "gemini/gemini-2.5-flash",
        "prompt_hash": "abc123",
    }
    base.update(overrides)
    return ApprovalRow(
        cre_id=base["cre_id"],
        name=base["name"],
        proposed_description=base["proposed_description"],
        grounding_snippet=base["grounding_snippet"],
        model=base["model"],
        prompt_hash=base["prompt_hash"],
    )


class ApprovalTableTest(unittest.TestCase):
    def test_csv_header_and_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            write_approval_csv(path, [_row()])
            with path.open(newline="") as fh:
                reader = csv.DictReader(fh)
                self.assertEqual(list(reader.fieldnames or []), list(APPROVAL_COLUMNS))
                rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["cre_id"], "111-111")
            self.assertEqual(
                rows[0]["proposed_description"], "Encrypt secrets at rest."
            )
            self.assertEqual(rows[0]["prompt_hash"], "abc123")

    def test_markdown_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.md"
            write_approval_markdown(path, [_row(name="Sessions")])
            text = path.read_text()
            self.assertIn("| cre_id |", text)
            self.assertIn("Sessions", text)
            self.assertIn("111-111", text)
            self.assertIn("Encrypt secrets at rest.", text)


if __name__ == "__main__":
    unittest.main()
