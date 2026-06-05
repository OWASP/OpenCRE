import os
import re

from application.defs.cheatsheet_defs import CheatsheetRecord

PARSER_VERSION = "v1"
FALLBACK_USED = "false"

CANONICAL_BASE_URL = "https://cheatsheetseries.owasp.org/cheatsheets/"

_TITLE_RE = re.compile(r"^#\s+(?P<title>.+)$", re.MULTILINE)
_HEADING_RE = re.compile(r"^##\s+(?P<heading>.+)$", re.MULTILINE)
_ANY_HEADING_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)


def _derive_source_id(source_path: str) -> str:
    """Derive the cheatsheet source ID from the markdown file path."""

    basename = os.path.basename(source_path)
    source_id, _ = os.path.splitext(basename)

    return source_id


def _derive_hyperlink(source_path: str) -> str:
    """Generate the canonical OWASP cheatsheet hyperlink."""

    source_id = _derive_source_id(source_path)

    return f"{CANONICAL_BASE_URL}{source_id}.html"


def _extract_body_after_heading(markdown: str, heading_match: re.Match) -> str:
    """Extract body content until the next markdown heading."""

    start = heading_match.end()
    next_heading = _ANY_HEADING_RE.search(markdown, start)
    end = next_heading.start() if next_heading else len(markdown)

    return markdown[start:end].strip()


def _extract_summary(markdown: str) -> str:
    """Extract a summary section from cheatsheet markdown."""

    all_heading_matches = list(_ANY_HEADING_RE.finditer(markdown))

    for match in all_heading_matches:
        heading_text = match.group().lstrip("#").strip()

        if heading_text.lower() == "introduction":
            body = _extract_body_after_heading(markdown, match)

            if body:
                return body

            break

    for match in all_heading_matches:
        body = _extract_body_after_heading(markdown, match)

        if body:
            return body

    raise ValueError("_extract_summary: no summary could be extracted from markdown.")


def extract_cheatsheet_record(
    markdown: str,
    source_path: str,
) -> CheatsheetRecord:
    """Extract a structured CheatsheetRecord from markdown content."""

    title_match = _TITLE_RE.search(markdown)
    title = title_match.group("title").strip()

    headings = [m.group("heading").strip() for m in _HEADING_RE.finditer(markdown)]

    summary = _extract_summary(markdown)

    source_id = _derive_source_id(source_path)
    hyperlink = _derive_hyperlink(source_path)

    return CheatsheetRecord(
        source_id=source_id,
        title=title,
        hyperlink=hyperlink,
        summary=summary,
        headings=headings,
        raw_markdown_path=source_path,
        category_hints=[],
        metadata={
            "parser_version": PARSER_VERSION,
            "fallback_used": FALLBACK_USED,
        },
    )
