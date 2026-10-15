"""Turn an OWASP event page (a Jekyll ``index.md``) into plain markdown prose.

Event repos (``www-event-*``) keep their facts in YAML front matter and a
schema.org JSON-LD ``<script>`` block, and wrap the rest in Liquid templating.
Fed to a chunker as-is, that markup would dominate the embedding text, so this
extracts the event's name, dates, location and description into a short header
and keeps only the real markdown body.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import yaml

# Page content is untrusted repo text, so every scan below is linear: delimiters
# are located with ``str.find`` or bounded regexes, never unbounded ``.*?`` that
# can rescan to the end of the page from each unmatched opener.
MAX_PAGE_CHARS = 300_000
_FRONT_MATTER = re.compile(r"\A\s*---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_SCRIPT_OR_STYLE_OPEN = re.compile(r"<(script|style)\b([^>]{0,500})>", re.IGNORECASE)
_LD_JSON_ATTR = re.compile(r"type\s*=\s*[\"']application/ld\+json[\"']", re.IGNORECASE)
_LIQUID_TAG = re.compile(r"\{%-?((?:(?!%\}).){0,300})%\}", re.DOTALL)
_LIQUID_OUTPUT = re.compile(r"\{\{(?:(?!\}\}).){0,300}\}\}", re.DOTALL)
_LIQUID_BLOCK_OPEN = re.compile(r"\s*-?\s*(for|if|unless|case|capture)\b")
_LIQUID_BLOCK_CLOSE = re.compile(r"\s*-?\s*end(for|if|unless|case|capture)\s*-?\s*\Z")
_BLANK_RUNS = re.compile(r"\n{3,}")


def _front_matter_title(text: str) -> tuple[Optional[str], str]:
    match = _FRONT_MATTER.match(text)
    if not match:
        return None, text
    title: Optional[str] = None
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("title"), str):
        title = data["title"].strip() or None
    return title, text[match.end() :]


def _event_objects(node: Any) -> List[Dict[str, Any]]:
    if isinstance(node, list):
        return [e for item in node for e in _event_objects(item)]
    if not isinstance(node, dict):
        return []
    found: List[Dict[str, Any]] = []
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    if any(isinstance(k, str) and k.endswith("Event") for k in kinds):
        found.append(node)
    found.extend(_event_objects(node.get("@graph")))
    return found


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _location(value: Any) -> str:
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, list):
        return ", ".join(p for p in (_location(v) for v in value) if p)
    if not isinstance(value, dict):
        return ""
    parts = [_text(value.get("name"))]
    address = value.get("address")
    if isinstance(address, dict):
        parts.append(
            ", ".join(
                _text(address.get(k))
                for k in (
                    "streetAddress",
                    "addressLocality",
                    "addressRegion",
                    "addressCountry",
                )
                if _text(address.get(k))
            )
        )
    else:
        parts.append(_text(address))
    if not any(parts):
        parts.append(_text(value.get("url")))
    return ", ".join(p for p in parts if p)


def _header(event: Dict[str, Any], fallback_title: Optional[str]) -> str:
    name = _text(event.get("name")) or fallback_title or ""
    lines: List[str] = [f"# {name}"] if name else []
    facts: List[str] = []
    start, end = _text(event.get("startDate")), _text(event.get("endDate"))
    if start and end and end != start:
        facts.append(f"Dates: {start} to {end}")
    elif start or end:
        facts.append(f"Dates: {start or end}")
    where = _location(event.get("location"))
    if where:
        facts.append(f"Location: {where}")
    if facts:
        lines.append("\n".join(facts))
    description = _text(event.get("description"))
    if description:
        lines.append(description)
    return "\n\n".join(lines)


def _strip_delimited(text: str, open_: str, close: str) -> str:
    """Remove ``open_ ... close`` spans; an unterminated opener is left alone."""
    out: List[str] = []
    pos = 0
    while True:
        i = text.find(open_, pos)
        if i < 0:
            break
        j = text.find(close, i + len(open_))
        if j < 0:
            break
        out.append(text[pos:i])
        pos = j + len(close)
    out.append(text[pos:])
    return "".join(out)


def _strip_liquid_blocks(text: str) -> str:
    """Drop whole ``{% if/for/... %}...{% end... %}`` blocks (outermost), in one pass."""
    spans: List[tuple[int, int]] = []
    stack: List[tuple[str, int]] = []
    for match in _LIQUID_TAG.finditer(text):
        body = match.group(1)
        opened = _LIQUID_BLOCK_OPEN.match(body)
        closed = _LIQUID_BLOCK_CLOSE.match(body)
        if opened:
            stack.append((opened.group(1), match.start()))
        elif closed:
            names = [name for name, _ in stack]
            if closed.group(1) in names:
                depth = len(names) - 1 - names[::-1].index(closed.group(1))
                start = stack[depth][1]
                del stack[depth:]
                if not stack:
                    spans.append((start, match.end()))
    out: List[str] = []
    pos = 0
    for start, end in spans:
        out.append(text[pos:start])
        pos = end
    out.append(text[pos:])
    return "".join(out)


def _strip_templating(text: str) -> str:
    text = _strip_delimited(text, "<!--", "-->")
    text = _strip_liquid_blocks(text)
    text = _LIQUID_TAG.sub("", text)
    return _LIQUID_OUTPUT.sub("", text)


def _extract_scripts(text: str, events: List[Dict[str, Any]]) -> str:
    """Remove ``<script>``/``<style>`` blocks, collecting schema.org Event JSON-LD."""
    out: List[str] = []
    lowered = text.lower()
    pos = 0
    scan = 0
    while True:
        match = _SCRIPT_OR_STYLE_OPEN.search(text, scan)
        if not match:
            break
        name = match.group(1).lower()
        close = lowered.find(f"</{name}", match.end())
        if close < 0:
            scan = match.end()
            continue
        end = lowered.find(">", close)
        if end < 0:
            break
        if name == "script" and _LD_JSON_ATTR.search(match.group(2)):
            try:
                # Hand-written JSON-LD often has raw newlines inside strings.
                events.extend(
                    _event_objects(json.loads(text[match.end() : close], strict=False))
                )
            except ValueError:
                pass
        out.append(text[pos : match.start()])
        pos = scan = end + 1
    out.append(text[pos:])
    return "".join(out)


def prepare_event_page(text: str) -> str:
    """Return clean markdown for an event page, or ``""`` if it has no content."""
    title, body = _front_matter_title(text[:MAX_PAGE_CHARS])

    events: List[Dict[str, Any]] = []
    body = _extract_scripts(body, events)
    body = _BLANK_RUNS.sub("\n\n", _strip_templating(body)).strip()

    header = ""
    if events:
        header = _header(events[0], title)
    elif title and body:
        header = f"# {title}"

    parts = [p for p in (header, body) if p]
    return "\n\n".join(parts) + "\n" if parts else ""


def _event_repo_markdown(url: str) -> bool:
    """True for a GitHub raw/blob URL of a markdown file in an OWASP ``www-event-*`` repo."""
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if host not in ("raw.githubusercontent.com", "github.com", "www.github.com"):
        return False
    parts = [p for p in parsed.path.split("/") if p]
    return (
        len(parts) >= 3
        and parts[0].lower() == "owasp"
        and parts[1].lower().startswith("www-event-")
        and parts[-1].lower().endswith(".md")
    )


def clean_embedding_text(url: str, text: str) -> str:
    """Clean fetched page text before embedding it, for event-repo pages only.

    The same markup that is dropped at harvest time would otherwise dominate the
    embedding of a filed event node. Falls back to ``text`` if nothing is left.
    """
    if not _event_repo_markdown(url):
        return text
    return prepare_event_page(text) or text
