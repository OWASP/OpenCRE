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

_FRONT_MATTER = re.compile(r"\A\s*---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_JSON_LD = re.compile(
    r"<script\b[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script\s*>",
    re.DOTALL | re.IGNORECASE,
)
_OTHER_SCRIPT_OR_STYLE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.DOTALL | re.IGNORECASE
)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_LIQUID_BLOCK = re.compile(
    r"\{%-?\s*(for|if|unless|case|capture)\b.*?%\}.*?\{%-?\s*end\1\s*-?%\}",
    re.DOTALL,
)
_LIQUID_TAG = re.compile(r"\{%.*?%\}", re.DOTALL)
_LIQUID_OUTPUT = re.compile(r"\{\{.*?\}\}", re.DOTALL)
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


def _strip_templating(text: str) -> str:
    text = _OTHER_SCRIPT_OR_STYLE.sub("", text)
    text = _HTML_COMMENT.sub("", text)
    previous = None
    while previous != text:
        previous = text
        text = _LIQUID_BLOCK.sub("", text)
    text = _LIQUID_TAG.sub("", text)
    text = _LIQUID_OUTPUT.sub("", text)
    return text


def prepare_event_page(text: str) -> str:
    """Return clean markdown for an event page, or ``""`` if it has no content."""
    title, body = _front_matter_title(text)

    events: List[Dict[str, Any]] = []

    def collect(match: "re.Match[str]") -> str:
        try:
            # Hand-written JSON-LD often has raw newlines inside strings.
            events.extend(_event_objects(json.loads(match.group(1), strict=False)))
        except ValueError:
            pass
        return ""

    body = _JSON_LD.sub(collect, body)
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
