import re

from .models import DiffBlock


class DiffParser:
    def parse(self, diff: str) -> list[DiffBlock]:
        blocks: list[DiffBlock] = []

        current_file: str | None = None
        added_lines: list[str] = []

        for line in diff.splitlines():
            if line.startswith("diff --git"):
                if current_file is not None:
                    blocks.append(
                        DiffBlock(file_path=current_file, added_lines=added_lines)
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
            blocks.append(DiffBlock(file_path=current_file, added_lines=added_lines))

        return blocks
