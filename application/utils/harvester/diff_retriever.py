import logging
import subprocess

from .git_repository_client import GitRepositoryClient

logger = logging.getLogger(__name__)


class DiffRetriever:
    def __init__(self, repository_client: GitRepositoryClient) -> None:
        self.repository_client = repository_client

    def get_diff(self, base_commit: str, target_commit: str = "HEAD") -> str:
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
                text=True,
                timeout=300,
            )
        except subprocess.CalledProcessError as exc:
            logger.error("Failed to retrieve diff: %s", exc.stderr)
            raise

        return result.stdout
