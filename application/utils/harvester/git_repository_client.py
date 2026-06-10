import subprocess
from pathlib import Path

from .repository_cache import build_repository_cache_path
from .repository_client import RepositoryClient
import logging

logger = logging.getLogger(__name__)


class GitRepositoryClient(RepositoryClient):
    def __init__(self, owner: str, repository: str, branch: str = "main") -> None:
        self.owner = owner
        self.repository = repository
        self.branch = branch

        self.local_path = build_repository_cache_path(
            owner,
            repository,
            branch,
        )

    @property
    def repository_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repository}.git"

    def clone(self) -> None:
        if self.exists_locally():
            logger.warning(
                "Repository %s/%s already exists locally",
                self.owner,
                self.repository,
            )
            return

        logger.info(
            "Cloning repository %s/%s",
            self.owner,
            self.repository,
        )

        self.local_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        subprocess.run(
            [
                "git",
                "clone",
                "--branch",
                self.branch,
                self.repository_url,
                str(self.local_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

    def fetch(self) -> None:
        logger.info(
            "Fetching repository %s/%s",
            self.owner,
            self.repository,
        )

        subprocess.run(
            [
                "git",
                "-C",
                str(self.local_path),
                "fetch",
                "--all",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

    def checkout(self, reference: str) -> None:
        logger.info(
            "Checking out %s in %s/%s",
            reference,
            self.owner,
            self.repository,
        )

        subprocess.run(
            [
                "git",
                "-C",
                str(self.local_path),
                "checkout",
                reference,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

    def get_local_path(self) -> Path:
        return self.local_path

    def exists_locally(self) -> bool:
        return self.local_path.exists()

    def sync(self) -> None:
        logger.info(
            "Synchronizing repository %s/%s",
            self.owner,
            self.repository,
        )

        if self.verify_repository_integrity():
            self.fetch()
        else:
            self.clone()

    def get_current_commit_sha(self) -> str:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.local_path),
                "rev-parse",
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

        return result.stdout.strip()

    def verify_repository_integrity(self) -> bool:
        git_directory = self.local_path / ".git"

        return (
            self.local_path.exists()
            and self.local_path.is_dir()
            and git_directory.exists()
        )
