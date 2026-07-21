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
        if self.verify_repository_integrity():
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

        try:
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
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to clone repository %s/%s: %s",
                self.owner,
                self.repository,
                exc.stderr,
            )
            raise

    def fetch(self) -> None:
        logger.info(
            "Fetching repository %s/%s",
            self.owner,
            self.repository,
        )

        try:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.local_path),
                    "fetch",
                    "origin",
                    self.branch,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.local_path),
                    "reset",
                    "--hard",
                    f"origin/{self.branch}",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )

        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to fetch repository %s/%s: %s",
                self.owner,
                self.repository,
                exc.stderr,
            )
            raise

    def checkout(self, reference: str) -> None:
        if reference.startswith("-"):
            raise ValueError("Invalid git reference")

        logger.info(
            "Checking out %s in %s/%s",
            reference,
            self.owner,
            self.repository,
        )

        try:
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
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to checkout %s in %s/%s: %s",
                reference,
                self.owner,
                self.repository,
                exc.stderr,
            )
            raise

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
        try:
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
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to retrieve commit SHA for %s/%s: %s",
                self.owner,
                self.repository,
                exc.stderr,
            )
            raise

        return result.stdout.strip()

    def verify_repository_integrity(self) -> bool:
        if not (self.local_path.exists() and self.local_path.is_dir()):
            return False

        try:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.local_path),
                    "rev-parse",
                    "--is-inside-work-tree",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )

            remote = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.local_path),
                    "config",
                    "--get",
                    "remote.origin.url",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            ).stdout.strip()

            if remote.rstrip("/") != self.repository_url.rstrip("/"):
                return False

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.local_path),
                    "show-ref",
                    "--verify",
                    f"refs/remotes/origin/{self.branch}",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )

            return True

        except subprocess.CalledProcessError:
            return False
