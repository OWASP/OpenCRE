from datetime import datetime
import re

from .models import DiffBlock


class DiffParser:
    """
    Parses unified git diffs into DiffBlock objects.

    Only added lines are extracted.
    Deleted lines and diff metadata are ignored.
    """

    def parse(
        self, diff: str, repository: str, commit_sha: str, committed_at: datetime
    ) -> list[DiffBlock]:
        """
        Convert a unified git diff into DiffBlock objects.
        """
        blocks: list[DiffBlock] = []

        current_file: str | None = None
        added_lines: list[str] = []

        for line in diff.splitlines():
            if line.startswith("diff --git"):
                if current_file is not None:
                    blocks.append(
                        DiffBlock(
                            file_path=current_file,
                            added_lines=added_lines,
                            repository=repository,
                            commit_sha=commit_sha,
                            committed_at=committed_at,
                        )
                    )

                match = re.match(r"diff --git a/(.+?) b/", line)

                if match:
                    current_file = match.group(1)
                    added_lines = []

                continue

            if line.startswith("+++"):
                continue

            if line.startswith("---"):
                continue

            if line.startswith("@@"):
                continue

            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])

        if current_file is not None:
            blocks.append(
                DiffBlock(
                    file_path=current_file,
                    added_lines=added_lines,
                    repository=repository,
                    commit_sha=commit_sha,
                    committed_at=committed_at,
                )
            )

        return blocks
