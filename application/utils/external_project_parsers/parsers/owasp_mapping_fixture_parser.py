"""Opt-in parsers that hydrate Standards from OWASP mapping *fixtures*.

These are eval/test gold, not import-all catalog sources. Other projects should
link to OpenCRE; we parse at the source. The exception is GSoC/OIE validation.
"""

from __future__ import annotations

from pathlib import Path

from typing import Optional

from application.database import db
from application.prompt_client import prompt_client
from application.utils.external_project_parsers.base_parser_defs import (
    ParseResult,
    ParserInterface,
)
from application.utils.mapping_fixtures import (
    linked_standards_from_mapping,
    load_mapping_entries,
)


class OwaspMappingFixtureParser(ParserInterface):
    fixture_name: str
    fallback_fixture_name: str | None = None
    data_file: Path | None = None
    fallback_data_file: Path | None = None

    def parse(
        self,
        database: db.Node_collection,
        prompt_client: Optional[prompt_client.PromptHandler],
    ) -> ParseResult:
        del prompt_client
        entries = load_mapping_entries(self.fixture_name, self.data_file)
        fallback_entries = None
        if self.fallback_fixture_name or self.fallback_data_file:
            fallback_entries = load_mapping_entries(
                self.fallback_fixture_name or "",
                self.fallback_data_file,
            )
        documents = linked_standards_from_mapping(
            database,
            self.name,
            entries,
            fallback_entries=fallback_entries,
        )
        return ParseResult(
            results={self.name: documents},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )
