from typing import Any

from sqlalchemy.exc import IntegrityError

from application import sqla
from application.database.db import HarvesterCheckpoint
from .models import RepositoryCheckpoint


class CheckpointStore:
    def __init__(self, session: Any = None) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session if self._session is not None else sqla.session

    def load(self, repository_id: str) -> RepositoryCheckpoint | None:
        session = self.session
        record = (
            session.query(HarvesterCheckpoint)
            .filter_by(repository_id=repository_id)
            .first()
        )
        if record is None:
            return None
        return RepositoryCheckpoint(
            repository_id=record.repository_id,
            last_processed_commit=record.last_processed_commit,
            updated_at=record.updated_at,
            provider=record.provider,
            owner=record.owner,
            repository=record.repository,
            branch=record.branch,
        )

    def save(self, checkpoint: RepositoryCheckpoint) -> None:
        session = self.session
        existing = (
            session.query(HarvesterCheckpoint)
            .filter_by(repository_id=checkpoint.repository_id)
            .first()
        )

        if existing is None:
            canonical_conflict = (
                session.query(HarvesterCheckpoint)
                .filter_by(
                    provider=checkpoint.provider,
                    owner=checkpoint.owner,
                    repository=checkpoint.repository,
                    branch=checkpoint.branch,
                )
                .first()
            )
            if canonical_conflict is not None:
                session.rollback()
                raise ValueError("duplicate canonical source identity")

            new_record = HarvesterCheckpoint(
                repository_id=checkpoint.repository_id,
                provider=checkpoint.provider,
                owner=checkpoint.owner,
                repository=checkpoint.repository,
                branch=checkpoint.branch,
                last_processed_commit=checkpoint.last_processed_commit,
                updated_at=checkpoint.updated_at,
            )
            session.add(new_record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise ValueError("duplicate canonical source identity")
            except Exception:
                session.rollback()
                raise
            return

        if (
            existing.provider != checkpoint.provider
            or existing.owner != checkpoint.owner
            or existing.repository != checkpoint.repository
            or existing.branch != checkpoint.branch
        ):
            session.rollback()
            raise ValueError("immutable repository identity")

        existing.last_processed_commit = checkpoint.last_processed_commit
        existing.updated_at = checkpoint.updated_at
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
