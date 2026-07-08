import logging
import subprocess

from .git_repository_client import GitRepositoryClient

logger = logging.getLogger(__name__)


class ChangeDetector:
    def __init__(self, repository_client: GitRepositoryClient):
        self.repository_client = repository_client

    def get_modified_files_since(self, commit_sha: str) -> list[str]:
        logger.info(
            "Detecting changes since commit %s",
            commit_sha,
        )

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repository_client.get_local_path()),
                    "diff",
                    "--name-only",
                    commit_sha,
                    "HEAD",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
        except subprocess.CalledProcessError as exc:
            logger.error("Git command failed: %s", exc.stderr)
            raise

        files = [
            file_path for file_path in result.stdout.splitlines() if file_path.strip()
        ]

        return sorted(set(files))

    def get_commits_since(self, commit_sha: str) -> list[str]:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repository_client.get_local_path()),
                    "log",
                    "--format=%H",
                    f"{commit_sha}..HEAD",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
        except subprocess.CalledProcessError as exc:
            logger.error("Git command failed: %s", exc.stderr)
            raise

        commits = [sha for sha in result.stdout.splitlines() if sha.strip()]

        logger.info(
            "Detected %s commits since %s",
            len(commits),
            commit_sha,
        )

        return commits
