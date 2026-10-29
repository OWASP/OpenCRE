"""Contract for external (non-GitHub) knowledge sources: crawled websites and YouTube channels.

They are stored as ordinary ``IngestionTarget`` rows (``kind`` below, ``spec_json`` = an
:class:`ExternalSpec`), so the existing admin targets API/UI, seeding and per-target status apply.
Everything that reads or writes them (registry/suggestions, crawler, YouTube, retrieval) goes through
this module so the shape is defined in one place.

Chunks produced by any external source have the same shape as repository chunks:
``(path, index, text)``. ``path`` is stable and unique inside the source (for a page: its URL path plus
query; for a talk: ``<video_id>``), and :func:`page_url` turns it back into the citation URL.
They are written with ``store.write_raw(database, slug_for(spec), chunks, embed, url_for=...)``, which
makes them retrievable exactly like a repository (``comprehension-<slug>-raw-*``).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

KIND_SITE = "external_site"
KIND_YOUTUBE = "youtube_channel"
KINDS = (KIND_SITE, KIND_YOUTUBE)

# suggested: found by us, nothing is crawled; approved: crawl allowed; rejected: never suggest again.
STATUS_SUGGESTED = "suggested"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUSES = (STATUS_SUGGESTED, STATUS_APPROVED, STATUS_REJECTED)

SLUG_PREFIX = "ext-"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


@dataclass
class ExternalSpec:
    id: str  # lowercase letters, digits, dashes; unique across targets
    name: str  # what people call it, e.g. "OWASP Benelux"
    kind: str = KIND_SITE
    owner: str = ""  # project/chapter repo slug or free text
    aliases: List[str] = field(
        default_factory=list
    )  # extra names that should match questions
    status: str = STATUS_SUGGESTED
    weight: float = 1.0  # authority weight (same meaning as the Authority tab)
    refresh_days: int = 30
    notes: str = ""  # licence / robots remarks
    # site
    start_urls: List[str] = field(default_factory=list)
    allow_prefixes: List[str] = field(
        default_factory=list
    )  # empty = same host as start_urls
    max_pages: int = 200
    max_depth: int = 2
    # youtube
    channel_id: str = ""
    playlist_id: str = ""
    # where we found it (suggestions): [{"repo": ..., "file": ..., "link_text": ..., "url": ...}]
    found_in: List[Dict[str, Any]] = field(default_factory=list)


def slug_for(spec_or_id: Any) -> str:
    """The comprehension "repo" slug for a source: ``ext-<id>``."""
    sid = spec_or_id if isinstance(spec_or_id, str) else spec_or_id.id
    return f"{SLUG_PREFIX}{sid}"


def is_external_slug(slug: str) -> bool:
    return (slug or "").startswith(SLUG_PREFIX)


def page_url(spec: ExternalSpec, path: str) -> str:
    """Citation URL for a chunk ``path`` of this source (identity for sites: the path is the URL)."""
    if spec.kind == KIND_YOUTUBE:
        return f"https://www.youtube.com/watch?v={path.split('#')[0]}" + (
            f"&t={path.split('#t=')[1]}s" if "#t=" in path else ""
        )
    return path


def _http_url(value: str) -> bool:
    u = urlparse(value or "")
    return u.scheme in ("http", "https") and bool(u.netloc)


def validate_spec(raw: Dict[str, Any]) -> ExternalSpec:
    """Build a clean :class:`ExternalSpec` from a dict (e.g. ``spec_json``); raises ``ValueError``."""
    if not isinstance(raw, dict):
        raise ValueError("spec must be an object")
    known = {f for f in ExternalSpec.__dataclass_fields__}
    spec = ExternalSpec(**{k: v for k, v in raw.items() if k in known})
    if not _ID_RE.match(spec.id or ""):
        raise ValueError("id must be 2-61 chars of a-z, 0-9 and dashes")
    if not (spec.name or "").strip():
        raise ValueError("name is required")
    if spec.kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if spec.status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if not 0.0 <= float(spec.weight) <= 3.0:
        raise ValueError("weight must be between 0 and 3")
    for field_name, lo, hi in (
        ("refresh_days", 1, 365),
        ("max_pages", 1, 5000),
        ("max_depth", 0, 6),
    ):
        v = getattr(spec, field_name)
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            raise ValueError(f"{field_name} must be an integer between {lo} and {hi}")
    if spec.kind == KIND_SITE:
        if not spec.start_urls or not all(_http_url(u) for u in spec.start_urls):
            raise ValueError("a site needs at least one http(s) start URL")
        if not all(_http_url(u) for u in spec.allow_prefixes):
            raise ValueError("allow_prefixes must be http(s) URLs")
    else:
        if not (spec.channel_id or spec.playlist_id):
            raise ValueError("a youtube source needs channel_id or playlist_id")
    spec.aliases = [a.strip() for a in spec.aliases if isinstance(a, str) and a.strip()]
    return spec


def spec_to_json(spec: ExternalSpec) -> str:
    return json.dumps(asdict(spec), sort_keys=True)


def spec_from_target(target: Any) -> Optional[ExternalSpec]:
    """The spec of an ``IngestionTarget`` row, or ``None`` if it is not an external source / invalid."""
    if getattr(target, "kind", None) not in KINDS:
        return None
    try:
        data = json.loads(getattr(target, "spec_json", "") or "{}")
        data.setdefault("id", getattr(target, "id", ""))
        data.setdefault("name", getattr(target, "name", ""))
        data.setdefault("kind", target.kind)
        return validate_spec(data)
    except (ValueError, TypeError):
        return None


def load_specs(
    session: Any,
    statuses: Iterable[str] = (STATUS_APPROVED,),
    kinds: Iterable[str] = KINDS,
) -> List[ExternalSpec]:
    """External sources from the targets table, filtered by status and kind (enabled rows only)."""
    from application.database import db

    want_status, want_kinds = set(statuses), set(kinds)
    rows = (
        session.query(db.IngestionTarget)
        .filter(db.IngestionTarget.kind.in_(list(want_kinds)))
        .all()
    )
    out = []
    for row in rows:
        spec = spec_from_target(row)
        if (
            spec
            and spec.status in want_status
            and (row.enabled or spec.status != STATUS_APPROVED)
        ):
            out.append(spec)
    return out
