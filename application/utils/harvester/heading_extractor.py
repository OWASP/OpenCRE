from dataclasses import dataclass

from .models import HeadingNode


@dataclass(slots=True)
class _FenceState:
    in_fence: bool = False


class HeadingExtractor:
    """
    Extracts Markdown ATX headings and their line ranges.

    Heading ranges extend until the next heading of the same
    or higher level, or the end of the document. Lines inside
    fenced code blocks and indented code blocks are ignored.
    """

    def extract(self, text: str) -> list[HeadingNode]:
        lines = text.splitlines()
        headings: list[HeadingNode] = []
        fence = _FenceState()

        for line_number, line in enumerate(lines, start=1):
            if self._toggle_fence(line, fence):
                continue
            if fence.in_fence:
                continue
            if self._is_indented_code(line):
                continue

            stripped = line.lstrip()
            if not stripped.startswith("#"):
                continue

            hashes = len(stripped) - len(stripped.lstrip("#"))
            if hashes == 0 or hashes > 6:
                continue
            if len(stripped) <= hashes or stripped[hashes] != " ":
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

    @staticmethod
    def _toggle_fence(line: str, fence: _FenceState) -> bool:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence.in_fence = not fence.in_fence
            return True
        return False

    @staticmethod
    def _is_indented_code(line: str) -> bool:
        if not line.strip():
            return False
        return line.startswith("    ") or line.startswith("\t")
