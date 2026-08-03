import subprocess
from pathlib import Path

from .repository_cache import build_repository_cache_path
from .repository_client import RepositoryClient
import logging
from .repository_lock import repository_lock
import os
import shutil
import tempfile

logger = logging.getLogger(__name__)


class GitRepositoryClient(RepositoryClient):
    def __init__(
        self,
        owner: str,
        repository: str,
        branch: str = "main",
        local_path: Path | None = None,
    ) -> None:
        if branch.startswith("-"):
            raise ValueError("Invalid git branch")
        self.owner = owner
        self.repository = repository
        self.branch = branch

        self.local_path = (
            local_path
            if local_path is not None
            else build_repository_cache_path(owner, repository, branch)
        )

    @property
    def repository_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repository}.git"

    def clone(self) -> None:

        logger.info(
            "Cloning repository %s/%s",
            self.owner,
            self.repository,
        )

        self.local_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._clone_atomically()

    def _clone_atomically(self) -> None:
        temp_path = Path(
            tempfile.mkdtemp(
                prefix=f"{self.repository}-",
                dir=self.local_path.parent,
            )
        )

        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--branch",
                    self.branch,
                    self.repository_url,
                    str(temp_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if not self.is_valid_repository(temp_path):
                raise RuntimeError("Temporary clone failed integrity verification")

            if self.local_path.exists():
                shutil.rmtree(temp_path)
                return

            os.replace(temp_path, self.local_path)

        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to clone repository %s/%s: %s",
                self.owner,
                self.repository,
                exc.stderr,
            )
            raise

        finally:
            if temp_path.exists():
                shutil.rmtree(temp_path, ignore_errors=True)

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

        with repository_lock(self.local_path):
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

    def is_valid_repository(self, repository_path: Path) -> bool:
        if not (repository_path.exists() and repository_path.is_dir()):
            return False

        try:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository_path),
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
                    str(repository_path),
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
                    str(repository_path),
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

    def verify_repository_integrity(self) -> bool:
        return self.is_valid_repository(self.local_path)
