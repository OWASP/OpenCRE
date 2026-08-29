from .models import Document


class DocumentValidator:
    """
    Validates structured Document objects before indexing.

    Ensures every required metadata field has been populated.
    """

    def validate(self, document: Document) -> bool:
        if not document.schema_version.strip():
            return False

        if not self._valid_artifact_id(document.artifact_id):
            return False

        if not document.pipeline_run_id.strip():
            return False

        if not document.text:
            return False

        if document.source.type != "github":
            return False

        if not document.source.repository.strip():
            return False

        if "/" not in document.source.repository:
            return False

        if not document.source.commit_sha.strip():
            return False

        if document.source.committed_at is None:
            return False

        if document.locator.kind != "repo_path":
            return False

        if not document.locator.id.strip():
            return False

        if not document.locator.path.strip():
            return False

        if document.locator.id != document.locator.path:
            return False

        return True

    @staticmethod
    def _valid_artifact_id(artifact_id: str) -> bool:
        # Expected: art:<owner>/<repo>:<path> with nonempty path.
        if not artifact_id.startswith("art:"):
            return False
        rest = artifact_id[len("art:") :]
        if ":" not in rest:
            return False
        repo, path = rest.split(":", 1)
        if not repo.strip() or "/" not in repo:
            return False
        if not path.strip():
            return False
        return True
