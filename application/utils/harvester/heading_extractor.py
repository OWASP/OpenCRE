from cre_logging import get_logger

logger = get_logger(__name__)

from dataclasses import dataclass
import re

from .models import HeadingNode


@dataclass(slots=True)
class _FenceState:
    in_fence: bool = False
    marker: str = ""
    length: int = 0


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
        # Four spaces (or a leading tab) belong to indented code, not a fence.
        match = re.fullmatch(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if match is None:
            return False

        marker, remainder = match.groups()
        if fence.in_fence:
            # A closer must match the opener's type and be at least as long.
            # Language/info strings are allowed only on opening fences.
            if (
                marker[0] != fence.marker
                or len(marker) < fence.length
                or remainder.strip(" \t")
            ):
                return False
            fence.in_fence = False
            fence.marker = ""
            fence.length = 0
        else:
            if marker[0] == "`" and "`" in remainder:
                return False
            fence.in_fence = True
            fence.marker = marker[0]
            fence.length = len(marker)
        return True

    @staticmethod
    def _is_indented_code(line: str) -> bool:
        if not line.strip():
            return False
        return line.startswith("    ") or line.startswith("\t")
