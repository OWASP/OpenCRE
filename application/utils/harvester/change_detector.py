import logging
import subprocess

from .git_repository_client import GitRepositoryClient

logger = logging.getLogger(__name__)


class ChangeDetector:
    def __init__(self, repository_client: GitRepositoryClient):
        self.repository_client = repository_client

    def _resolve_commit(self, commit_sha: str) -> str:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repository_client.get_local_path()),
                    "rev-parse",
                    "--verify",
                    "--end-of-options",
                    f"{commit_sha}^{{commit}}",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
        except subprocess.CalledProcessError as exc:
            logger.error("Git command failed: %s", exc.stderr)
            raise

        return result.stdout.strip()

    def get_modified_files_since(
        self, base_commit: str, target_commit: str
    ) -> list[str]:
        logger.info(
            "Detecting changes between %s and %s",
            base_commit,
            target_commit,
        )

        base = self._resolve_commit(base_commit)
        target = self._resolve_commit(target_commit)

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repository_client.get_local_path()),
                    "diff",
                    "--name-only",
                    base,
                    target,
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

    def get_commits_since(self, base_commit: str, target_commit: str) -> list[str]:
        base = self._resolve_commit(base_commit)
        target = self._resolve_commit(target_commit)

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repository_client.get_local_path()),
                    "log",
                    "--reverse",
                    "--format=%H",
                    f"{base}..{target}",
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
            "Detected %s commits between %s and %s",
            len(commits),
            base_commit,
            target_commit,
        )

        return commits
