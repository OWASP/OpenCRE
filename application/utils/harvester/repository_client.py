from abc import ABC, abstractmethod
from pathlib import Path


class RepositoryClient(ABC):
    @abstractmethod
    def clone(self) -> None:
        """Clone repository locally."""

    @abstractmethod
    def fetch(self) -> None:
        """Fetch latest remote changes."""

    @abstractmethod
    def checkout(self, reference: str) -> None:
        """Checkout repository reference."""

    @abstractmethod
    def get_local_path(self) -> Path:
        """Return local repository path."""

    @abstractmethod
    def exists_locally(self) -> bool:
        """Check if repository already exists locally."""
