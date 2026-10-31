"""Tests for optional requirement matcher / extractor."""

from __future__ import annotations

import unittest

from application.utils.harvester.requirement_extractor import (
    extract_requirement_chunks,
    extract_requirement_segments,
    normalize_asvs_id,
    requirements_needed,
    should_extract_requirements,
)

_ASVS_SNIPPET = """\
# V1 Encoding and Sanitization

## V1.1 Encoding and Sanitization Architecture

| # | Description | Level |
| :---: | :--- | :---: |
| **1.1.1** | Verify that input is decoded into a canonical form only once. | 2 |
| **1.1.2** | Verify that the application performs output encoding and escaping. | 2 |
| **1.1.3** | Verify that output encoding preserves the integrity of data. | 2 |
| **1.2.1** | Verify that the application protects against SQL injection. | 1 |
| **1.2.2** | Verify that the application protects against OS command injection. | 1 |
"""

_NARRATIVE = """\
# Authorization Cheat Sheet

This sheet describes how to design authorization for web apps.
It mentions version 1.2.3 only as an example release number once.
There are no Verify that requirement tables here.
"""


class RequirementExtractorTests(unittest.TestCase):
    def test_normalize_asvs_id(self) -> None:
        self.assertEqual(normalize_asvs_id("1.1.2"), "V1.1.2")
        self.assertEqual(normalize_asvs_id("v1.1.2"), "V1.1.2")
        self.assertEqual(normalize_asvs_id("V1.1.2"), "V1.1.2")
        self.assertEqual(normalize_asvs_id("AC-2"), "AC-2")

    def test_requirements_needed_true_for_asvs_table(self) -> None:
        self.assertTrue(requirements_needed(_ASVS_SNIPPET))

    def test_requirements_needed_false_for_narrative(self) -> None:
        self.assertFalse(requirements_needed(_NARRATIVE))

    def test_should_extract_modes(self) -> None:
        self.assertFalse(should_extract_requirements(_ASVS_SNIPPET, mode="off"))
        self.assertTrue(should_extract_requirements(_ASVS_SNIPPET, mode="on"))
        self.assertTrue(should_extract_requirements(_ASVS_SNIPPET, mode="auto"))
        self.assertFalse(should_extract_requirements(_NARRATIVE, mode="auto"))

    def test_extract_table_segments(self) -> None:
        segs = extract_requirement_segments(_ASVS_SNIPPET)
        ids = [s.requirement_id for s in segs]
        self.assertIn("V1.1.1", ids)
        self.assertIn("V1.1.2", ids)
        self.assertIn("V1.2.2", ids)
        self.assertGreaterEqual(len(segs), 5)

    def test_extract_chunks_prefix_section_id(self) -> None:
        chunks = extract_requirement_chunks(_ASVS_SNIPPET)
        self.assertGreaterEqual(len(chunks), 5)
        joined = "\n".join(c.text for c in chunks)
        self.assertIn("Section-ID: V1.1.2", joined)
        for c in chunks:
            self.assertLess(c.start_char_idx, c.end_char_idx)

    def test_table_segment_is_prose_only_no_next_heading_bleed(self) -> None:
        body = """\
## V1.1 Encoding Architecture

| # | Description | Level |
| :---: | :--- | :---: |
| **1.1.2** | Verify that the application performs output encoding. | 2 |
| **1.1.3** | Verify that output encoding preserves integrity. | 2 |

## V1.2 Injection Prevention

| # | Description | Level |
| :---: | :--- | :---: |
| **1.2.1** | Verify that the application protects against SQL injection. | 1 |
"""
        segs = {s.requirement_id: s for s in extract_requirement_segments(body)}
        self.assertIn("V1.1.3", segs)
        # Must not pull the next subsection heading into the prior requirement.
        self.assertNotIn("V1.2 Injection", segs["V1.1.3"].text)
        self.assertNotIn("SQL injection", segs["V1.1.3"].text)
        # Body is clean requirement prose (no raw table pipes).
        self.assertIn("preserves integrity", segs["V1.1.3"].text)
        self.assertNotIn("|", segs["V1.1.3"].text)

    def test_extract_chunk_single_section_id_line(self) -> None:
        chunks = extract_requirement_chunks(_ASVS_SNIPPET)
        v112 = next(c for c in chunks if "Section-ID: V1.1.2\n" in c.text)
        # Exactly one Section-ID line, matching Source id (B2-shaped).
        sid_lines = [
            ln for ln in v112.text.splitlines() if ln.startswith("Section-ID:")
        ]
        self.assertEqual(sid_lines, ["Section-ID: V1.1.2"])
        self.assertTrue(v112.text.startswith("Source: V1.1.2\n"))
        self.assertNotIn("|", v112.text)


if __name__ == "__main__":
    unittest.main()
