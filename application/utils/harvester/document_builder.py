from .artifact_id import generate_artifact_id
from .heading_extractor import HeadingExtractor
from .models import (
    DiffBlock,
    Document,
    Locator,
    SourceInfo,
)


class DocumentBuilder:
    """
    Builds structured Document objects from parsed diffs.

    This bridges raw git diff ingestion and downstream
    semantic chunking.
    """

    SCHEMA_VERSION = "0.2.0"

    def build(self, block: DiffBlock, full_text: str, pipeline_run_id: str) -> Document:
        artifact_id = generate_artifact_id(
            block.repository,
            block.file_path,
        )

        headings = HeadingExtractor().extract(full_text)

        return Document(
            schema_version=self.SCHEMA_VERSION,
            artifact_id=artifact_id,
            pipeline_run_id=pipeline_run_id,
            text=full_text,
            heading_structure=headings,
            source=SourceInfo(
                type="github",
                repository=block.repository,
                commit_sha=block.commit_sha,
                committed_at=block.committed_at,
            ),
            locator=Locator(
                kind="repo_path",
                id=block.file_path,
                path=block.file_path,
            ),
        )
