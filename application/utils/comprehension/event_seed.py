"""Curated OWASP event/chapter sites (``docs/oie/owasp-event-sites.json``) as external-source suggestions.

Pure helpers: load and validate the list, build discovery-style candidates, plan and store them.
Everything lands as ``suggested`` + disabled via ``external_targets.upsert_suggestions``; nothing is
fetched here, and an admin still approves each site.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from application.utils.comprehension import discovery, external, link_suggestions

SOURCE_SEED = "seed"
DOC = "docs/oie/owasp-event-sites.md"
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "docs/oie/owasp-event-sites.json"
KINDS = ("global", "regional", "chapter")
STATUSES = ("registered", "candidate")
MIN_PAGES, MAX_PAGES, DEFAULT_PAGES = 30, 60, 40
MAX_DEPTH = 2
_REQUIRED = ("id", "name", "url", "start_url", "kind", "year", "status")


def load_sites(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    data = json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))
    sites = data.get("sites") if isinstance(data, dict) else None
    if not isinstance(sites, list):
        raise ValueError("seed file needs a top-level 'sites' list")
    seen = set()
    for s in sites:
        validate_site(s)
        if s["id"] in seen:
            raise ValueError(f"duplicate site id {s['id']}")
        seen.add(s["id"])
    return sites


def validate_site(s: Any) -> None:
    if not isinstance(s, dict):
        raise ValueError("a site must be an object")
    for k in _REQUIRED:
        if s.get(k) in (None, ""):
            raise ValueError(f"site {s.get('id') or '?'}: missing {k}")
    for k in ("url", "start_url"):
        u = urlparse(str(s[k]))
        if u.scheme not in ("http", "https") or not u.netloc:
            raise ValueError(f"site {s['id']}: {k} must be an http(s) URL")
    if s["kind"] not in KINDS:
        raise ValueError(f"site {s['id']}: kind must be one of {KINDS}")
    if s["status"] not in STATUSES:
        raise ValueError(f"site {s['id']}: status must be one of {STATUSES}")
    if not isinstance(s["year"], int) or isinstance(s["year"], bool):
        raise ValueError(f"site {s['id']}: year must be an integer")
    pages = s.get("max_pages", DEFAULT_PAGES)
    if not isinstance(pages, int) or not MIN_PAGES <= pages <= MAX_PAGES:
        raise ValueError(f"site {s['id']}: max_pages must be {MIN_PAGES}..{MAX_PAGES}")
    if (
        not isinstance(s.get("robots"), dict)
        or "generic_agents_allowed" not in s["robots"]
    ):
        raise ValueError(f"site {s['id']}: robots.generic_agents_allowed is required")
    if s.get("needs_review") and not s.get("review_reasons"):
        raise ValueError(f"site {s['id']}: needs_review requires review_reasons")


def _bare(host: str) -> str:
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def to_candidate(s: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Discovery-style candidate for ``external_targets.upsert_suggestions``."""
    year = (now or datetime.now(timezone.utc)).year
    start = s["start_url"]
    host = _bare(urlparse(start).hostname or "")
    root = f"{urlparse(start).scheme}://{urlparse(start).netloc}/"
    notes = ["seed: " + DOC]
    if s.get("needs_review"):
        notes.append("needs-review: " + "; ".join(s["review_reasons"]))
    if s["robots"].get("notes"):
        notes.append("robots: " + str(s["robots"]["notes"]))
    return {
        "url": start,
        "host": host,
        "kind": "site",
        "subdomain": host != link_suggestions.registrable_host(host),
        "name_guess": s["name"],
        "score": 0.0,
        "found_in": [
            {
                "source": SOURCE_SEED,
                "page": DOC,
                "link_text": s["name"],
                "url": s["url"],
            }
        ],
        "allow_prefixes": [root],
        "max_pages": s.get("max_pages", DEFAULT_PAGES),
        "max_depth": MAX_DEPTH,
        "refresh_days": 7 if s["year"] >= year else 30,
        "notes": " | ".join(notes)[:500],
    }


def candidates(
    sites: List[Dict[str, Any]], now: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """Candidates for sites flagged ``suggest`` and not already ``registered``."""
    return [
        to_candidate(s, now)
        for s in sites
        if s.get("suggest") and s["status"] != "registered"
    ]


def plan(cands: List[Dict[str, Any]], session: Any) -> List[Dict[str, Any]]:
    """What :func:`apply` would do per candidate, without writing: create / merge / skip."""
    from application.database import db
    from application.utils.admin_panel import external_targets

    known = external_targets.registered_hosts(session)
    known_reg = {link_suggestions.registrable_host(h) for h in known}
    out = []
    for c in cands:
        cid = link_suggestions.candidate_id(c)
        row = session.query(db.IngestionTarget).filter_by(id=cid).first()
        if row is not None:
            spec = external.spec_from_target(row)
            ok = spec is not None and spec.status == external.STATUS_SUGGESTED
            action, why = ("merge", "") if ok else ("skip", "already approved/rejected")
        elif (
            (c["host"] in known)
            if c["subdomain"]
            else (link_suggestions.registrable_host(c["host"]) in known_reg)
        ):
            action, why = "skip", "host already registered or rejected"
        else:
            action, why = "create", ""
        if action == "create":
            known.add(c["host"])
            known_reg.add(link_suggestions.registrable_host(c["host"]))
        out.append({"id": cid, "action": action, "why": why, "candidate": c})
    return out


def apply(
    cands: List[Dict[str, Any]], session: Any, limit: int = discovery.DEFAULT_LIMIT
) -> Dict[str, Any]:
    """Store candidates as disabled suggestions (at most ``limit`` new rows); no network."""
    return discovery.store_candidates(session, cands, limit=limit, max_resolve=0)
