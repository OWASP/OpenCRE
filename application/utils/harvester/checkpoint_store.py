import json
import os
from datetime import datetime
from pathlib import Path

from .models import RepositoryCheckpoint


class CheckpointStore:
    def __init__(self, checkpoint_file: Path):
        self.checkpoint_file = checkpoint_file

    def load(self, repository_id: str) -> RepositoryCheckpoint | None:
        try:
            data = json.loads(
                self.checkpoint_file.read_text(
                    encoding="utf-8",
                )
            )
        except FileNotFoundError:
            return None

        if repository_id not in data:
            return None

        checkpoint = data[repository_id]

        return RepositoryCheckpoint(
            repository_id=repository_id,
            last_processed_commit=checkpoint["last_processed_commit"],
            updated_at=datetime.fromisoformat(
                checkpoint["updated_at"],
            ),
        )

    def save(self, checkpoint: RepositoryCheckpoint) -> None:
        try:
            data = json.loads(
                self.checkpoint_file.read_text(
                    encoding="utf-8",
                )
            )
        except FileNotFoundError:
            data = {}

        data[checkpoint.repository_id] = {
            "last_processed_commit": checkpoint.last_processed_commit,
            "updated_at": checkpoint.updated_at.isoformat(),
        }

        self.checkpoint_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_file = self.checkpoint_file.with_suffix(".tmp")
        temp_file.write_text(
            json.dumps(
                data,
                indent=2,
            ),
            encoding="utf-8",
        )

        os.replace(temp_file, self.checkpoint_file)
