from abc import ABC, abstractmethod
from pathlib import Path


class RepositoryClient(ABC):
    @abstractmethod
    def clone(self) -> None:
        """Clone repository locally."""

    @abstractmethod
    def fetch(self) -> None:
        """Fetch latest repository changes."""

    @abstractmethod
    def checkout(self, reference: str) -> None:
        """Checkout a branch, tag, or commit."""

    @abstractmethod
    def get_local_path(self) -> Path:
        """Return local repository path."""

    @abstractmethod
    def exists_locally(self) -> bool:
        """Return whether repository exists locally."""

    @abstractmethod
    def sync(self) -> None:
        """Clone if missing, otherwise fetch latest changes."""

    @abstractmethod
    def get_current_commit_sha(self) -> str:
        """Return HEAD commit SHA."""

    @abstractmethod
    def verify_repository_integrity(self) -> bool:
        """Verify local repository integrity."""

