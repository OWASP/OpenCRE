import logging
import os
import re
import subprocess

from application.defs.cheatsheet_defs import CheatsheetRecord

PARSER_VERSION = "v1"

CANONICAL_BASE_URL = "https://cheatsheetseries.owasp.org/cheatsheets/"

_TITLE_RE = re.compile(
    r"^\s*#(?!#)\s*(?P<title>.+?)$",
    re.MULTILINE,
)

_HEADING_RE = re.compile(
    r"^\s*##(?!#)\s*(?P<heading>.+?)$",
    re.MULTILINE,
)

_ANY_HEADING_RE = re.compile(
    r"^\s*#{1,6}(?!#)\s*.+?$",
    re.MULTILINE,
)


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
    """Extract summary from Introduction section in cheatsheet markdown."""

    for match in _ANY_HEADING_RE.finditer(markdown):
        if match.group().strip().lstrip("#").strip().lower() == "introduction":
            body = _extract_body_after_heading(markdown, match)
            if body:
                return body

    raise ValueError(
        "_extract_summary: no suitable summary section could be extracted from markdown."
    )


def _extract_title(markdown: str) -> str:
    """Extract H1 title from cheatsheet markdown."""

    match = _TITLE_RE.search(markdown)
    if not match:
        raise ValueError("_extract_title: no title found in markdown.")

    return match.group("title").strip()


def _fallback_title() -> str:
    """Return fallback title for malformed markdown."""

    return "No title found."


def _fallback_summary(markdown: str) -> str:
    """Return first non-empty paragraph after any heading, or 'No summary found.'"""

    for match in _ANY_HEADING_RE.finditer(markdown):
        body = _extract_body_after_heading(markdown, match)
        if body:
            return body

    return "No summary found."


def _get_committed_at(source_path: str) -> str:
    """Return the ISO 8601 last-commit timestamp for source_path, or '' if unavailable."""

    repo_dir = os.path.dirname(os.path.abspath(source_path)) or "."

    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", os.path.basename(source_path)],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        logging.warning(
            "_get_committed_at: commit not found for %s: %s",
            source_path,
            e,
        )
        return ""

    return result.stdout.strip()


def extract_cheatsheet_record(
    markdown: str,
    source_path: str,
) -> CheatsheetRecord:
    """Extract a structured CheatsheetRecord from markdown content."""

    fallback_used = "false"

    try:
        title = _extract_title(markdown)
    except ValueError as e:
        logging.warning(str(e))
        title = _fallback_title()
        fallback_used = "true"

    # Headings can be empty.
    headings = [m.group("heading").strip() for m in _HEADING_RE.finditer(markdown)]

    try:
        summary = _extract_summary(markdown)
    except ValueError as e:
        logging.warning(str(e))
        summary = _fallback_summary(markdown)
        fallback_used = "true"

    source_id = _derive_source_id(source_path)
    hyperlink = _derive_hyperlink(source_path)
    committed_at = _get_committed_at(source_path)

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
            "fallback_used": fallback_used,
            "committed_at": committed_at,
        },
    )
