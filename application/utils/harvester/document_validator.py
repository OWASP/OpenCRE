from .models import Document


class DocumentValidator:
    """
    Validates structured Document objects before indexing.

    Ensures every required metadata field has been populated.
    """

    def validate(self, document: Document) -> bool:
        if not document.schema_version:
            return False

        if not document.artifact_id.startswith("art:"):
            return False

        if not document.pipeline_run_id:
            return False

        if not document.text:
            return False

        if document.source.type != "github":
            return False

        if not document.source.repository:
            return False

        if not document.source.commit_sha:
            return False

        if document.source.committed_at is None:
            return False

        if document.locator.kind != "repo_path":
            return False

        if not document.locator.path:
            return False

        return True
