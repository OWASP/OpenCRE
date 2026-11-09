from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
import tempfile
import unittest

from application.defs.cheatsheet_defs import CheatsheetRecord
from application.utils.external_project_parsers.parsers.cheatsheet_knowledge_queue_item import (
    knowledge_queue_item_from_cheatsheet_record,
    write_knowledge_queue_jsonl,
)
from application.utils.noise_filter.hashing import compute_content_hash
from application.utils.librarian.knowledge_source import FixtureKnowledgeSource
from application.utils.librarian.schemas import (
    SCHEMA_VERSION,
    LocatorKind,
    SourceType,
)
from application.utils.librarian.section_validator import section_from_queue_row

RUN_ID = "run-cheatsheet-test"
HYPERLINK = (
    "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html"
)


def _record(headings=None):
    if headings is None:
        headings = ["Introduction", "Architectural Patterns"]

    return CheatsheetRecord(
        source_id="Secrets_Management_Cheat_Sheet",
        title="Secrets Management Cheat Sheet",
        hyperlink=HYPERLINK,
        summary="Storage guidance.",
        headings=headings,
        raw_markdown_path="cheatsheets/Secrets_Management_Cheat_Sheet.md",
        metadata={
            "parser_version": "v1",
            "fallback_used": "false",
            "committed_at": "2026-06-14T10:22:03+00:00",
        },
    )


class TestKnowledgeQueueItemFromCheatsheetRecord(unittest.TestCase):
    # Happy Path
    def test_valid_record_maps_every_field(self):
        item = knowledge_queue_item_from_cheatsheet_record(
            _record(), pipeline_run_id=RUN_ID
        )

        self.assertTrue(item.id)  ## confirms id is created.
        self.assertEqual(
            item.artifact_id, "art:owasp_cheatsheets:Secrets_Management_Cheat_Sheet"
        )
        self.assertEqual(
            item.chunk_id,
            "chk:art:owasp_cheatsheets:Secrets_Management_Cheat_Sheet:0",
        )
        self.assertEqual(
            item.text, "Storage guidance.\nIntroduction\nArchitectural Patterns"
        )
        self.assertEqual(item.content_hash, compute_content_hash(item.text))
        self.assertEqual(item.pipeline_run_id, RUN_ID)
        self.assertEqual(item.schema_version, SCHEMA_VERSION)
        self.assertEqual(
            item.source_type, SourceType.url
        )  # preserves upstream provenance
        self.assertIsNone(item.source_repo)
        self.assertIsNone(item.source_commit_sha)
        self.assertEqual(
            item.source_committed_at.isoformat(), "2026-06-14T10:22:03+00:00"
        )
        self.assertEqual(item.feed_url, HYPERLINK)
        self.assertIsNone(item.post_guid)
        self.assertEqual(item.locator_kind, LocatorKind.url)
        self.assertEqual(item.locator_path, HYPERLINK)
        self.assertEqual(item.span_index, 0)
        self.assertEqual(item.span_total, 1)
        self.assertEqual(
            json.loads(item.span_heading_path),
            ["Introduction", "Architectural Patterns"],
        )
        self.assertEqual(item.llm_label, "KNOWLEDGE")
        self.assertEqual(item.confidence, 1.0)
        self.assertIsNone(item.consumed_at)
        self.assertEqual(item.llm_reasoning, None)
        self.assertIsNotNone(item.created_at)

    ## test to ensure no '[]' can pass accidentally.
    def test_no_headings_leaves_heading_path_null(self):
        item = knowledge_queue_item_from_cheatsheet_record(
            _record(headings=[]), pipeline_run_id=RUN_ID
        )
        self.assertIsNone(item.span_heading_path)

    def test_row_passes_c0_validation(self):
        item = knowledge_queue_item_from_cheatsheet_record(
            _record(),
            pipeline_run_id=RUN_ID,
        )
        # If C.0 rejects our JSONL item, the test fails.
        section_from_queue_row(item)

    def test_jsonl_can_be_read_by_fixture_knowledge_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cheatsheets.jsonl")

            write_knowledge_queue_jsonl(
                [_record()],
                path,
                pipeline_run_id=RUN_ID,
            )

            # If FixtureKnowledgeSource rejects our generated JSONL, the test fails.
            list(FixtureKnowledgeSource(path).items())


if __name__ == "__main__":
    unittest.main()
