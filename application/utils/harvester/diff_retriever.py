import logging
import subprocess

from .git_repository_client import GitRepositoryClient

logger = logging.getLogger(__name__)


class DiffRetriever:
    MAX_DIFF_SIZE_BYTES = 50 * 1024 * 1024
    """

    Retrieves unified git diffs between two commits.

    This class is responsible only for retrieving raw diff text.

    Parsing and normalization are handled by downstream components.

    """

    def __init__(self, repository_client: GitRepositoryClient) -> None:
        self.repository_client = repository_client

    def get_diff(self, base_commit: str, target_commit: str = "HEAD") -> str:
        """
        Return the unified git diff between two commits.

        Args:
            base_commit:
                Base commit SHA.
            target_commit:
                Target commit SHA or branch.

        Raises:
            subprocess.CalledProcessError:
                If git diff fails.

            ValueError:
                If the diff exceeds the configured size limit.
        """
        logger.info(
            "Retrieving diff between %s and %s",
            base_commit,
            target_commit,
        )

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repository_client.get_local_path()),
                    "diff",
                    base_commit,
                    target_commit,
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to retrieve diff: %s",
                exc.stderr.decode("utf-8", errors="replace"),
            )
            raise

        diff_bytes = result.stdout

        diff_size = len(diff_bytes)

        if diff_size > self.MAX_DIFF_SIZE_BYTES:
            raise ValueError(
                f"Diff size ({diff_size} bytes) exceeds "
                f"maximum supported size ({self.MAX_DIFF_SIZE_BYTES} bytes)."
            )

        return diff_bytes.decode("utf-8", errors="replace")
