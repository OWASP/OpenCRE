from dataclasses import dataclass
from .models import HeadingNode


class HeadingExtractor:
    """
    Extracts Markdown headings and their line ranges.

    Heading ranges extend until the next heading of the same
    or higher level, or the end of the document.
    """

    def extract(self, text: str) -> list[HeadingNode]:
        lines = text.splitlines()

        headings: list[HeadingNode] = []

        for line_number, line in enumerate(lines, start=1):
            stripped = line.lstrip()

            if not stripped.startswith("#"):
                continue

            hashes = len(stripped) - len(stripped.lstrip("#"))

            if hashes == 0:
                continue

            if len(stripped) > hashes and stripped[hashes] != " ":
                continue

            headings.append(
                HeadingNode(
                    level=hashes,
                    text=stripped[hashes:].strip(),
                    start_line=line_number,
                    end_line=len(lines),
                )
            )

        for index, heading in enumerate(headings):
            for next_heading in headings[index + 1 :]:
                if next_heading.level <= heading.level:
                    heading.end_line = next_heading.start_line - 1
                    break

        return headings
