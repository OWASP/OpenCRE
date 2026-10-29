"""Discover external knowledge sources and queue them as suggestions (never crawl, never approve).

Two inputs feed the same pipeline: links found in harvested GitHub repos (``suggest_from_repos``) and
out-of-scope links collected while crawling an approved site (``candidates_from_crawl``). Candidates are
ranked, polite-resolved once (redirects, so the suggestion starts at the final URL) and stored with
``external_targets.upsert_suggestions`` as ``suggested`` + disabled rows. An admin approves them in the
Suggestions card, after which the existing ``external_sources`` job crawls them on its schedule.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse

from application.utils.comprehension import external, link_suggestions, web_source

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 25  # new suggestions stored per run
DEFAULT_MAX_RESOLVE = 20  # redirect resolutions per run
RESOLVE_DELAY = 1.0
RESOLVE_TIMEOUT = 10
MIN_SCORE = 2.0  # below this a link is not worth an admin's attention
SOURCE_GITHUB, SOURCE_CRAWL = "github", "crawl"

# Hosts that are never a knowledge source: CDNs, forms, more social/video, on top of link_suggestions.SKIP_HOSTS.
EXTRA_SKIP_HOSTS = frozenset(
    {
        "cloudflare.com",
        "cloudfront.net",
        "amazonaws.com",
        "jsdelivr.net",
        "unpkg.com",
        "cdnjs.cloudflare.com",
        "googleapis.com",
        "gstatic.com",
        "google.com",
        "googletagmanager.com",
        "typeform.com",
        "jotform.com",
        "surveymonkey.com",
        "airtable.com",
        "bsky.app",
        "threads.net",
        "tiktok.com",
        "twitch.tv",
        "mastodon.social",
        "vimeo.com",
        "paypal.com",
        "patreon.com",
        "ko-fi.com",
    }
)
_EVENT_WORDS = (
    "program",
    "schedule",
    "agenda",
    "speaker",
    "cfp",
    "call for papers",
    "call-for-papers",
    "ticket",
    "register",
    "venue",
    "sponsor",
    "conference",
    "event",
    "chapter",
    "summit",
)
_YEAR = re.compile(r"(?<!\d)(20\d\d)(?!\d)")


def _skipped(host: str) -> bool:
    return link_suggestions._skipped_host(host) or any(
        host == s or host.endswith("." + s) for s in EXTRA_SKIP_HOSTS
    )


def event_years(url: str) -> List[int]:
    """Years (20xx) mentioned in the host or path of a URL."""
    u = urlparse(url)
    return [int(y) for y in _YEAR.findall((u.hostname or "") + u.path)]


def score_link(
    url: str, link_text: str, now: Optional[datetime] = None
) -> Tuple[float, bool]:
    """Relevance of an external link as ``(score, event_like)``; pure, no network.

    Keywords in the anchor text weigh most, then in the host/path. A year in the host or path scores
    higher when it is this year or last (live conference sites), and clearly lower when older.
    """
    year = (now or datetime.now(timezone.utc)).year
    u = urlparse(url)
    text = (link_text or "").lower()
    where = ((u.hostname or "") + u.path).lower()
    score = 0.0
    keywords = False
    if any(w in text for w in _EVENT_WORDS):
        score += 2.0
        keywords = True
    if any(w in where for w in _EVENT_WORDS):
        score += 1.5
        keywords = True
    years = event_years(url)
    if years:
        newest = max(years)
        if newest >= year:
            score += 3.0
        elif newest == year - 1:
            score += 2.0
        else:
            score -= 4.0
    if u.path.strip("/") == "" and score > 0:
        score += 0.5  # a bare site root is usually the project's own home
    return score, bool(keywords or (years and max(years) >= year - 1))


def _root(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}/"


def candidates_from_crawl(
    spec: external.ExternalSpec,
    result: Any,
    registered_hosts: Iterable[str] = (),
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Ranked candidates (``link_suggestions`` shape) from ``result.external_links`` of a crawl of ``spec``."""
    own = {
        link_suggestions.registrable_host(link_suggestions.host_of(u))
        for u in list(spec.start_urls) + list(spec.allow_prefixes)
    }
    skip = own | {link_suggestions.registrable_host(h) for h in registered_hosts}
    groups: Dict[str, Dict[str, Any]] = {}
    for url, text, page in result.external_links:
        host = link_suggestions.host_of(url)
        if (
            not host
            or urlparse(url).scheme not in ("http", "https")
            or link_suggestions._IMG_EXT.search(urlparse(url).path)
            or _skipped(host)
        ):
            continue
        reg = link_suggestions.registrable_host(host)
        if reg in skip or _skipped(reg):
            continue
        score, event_like = score_link(url, text, now)
        g = groups.setdefault(
            reg, {"best": None, "score": -99.0, "event": False, "links": []}
        )
        g["links"].append((score, url, text, page))
        g["event"] = g["event"] or event_like
        if score > g["score"]:
            g["best"], g["score"] = (url, text), score
    out = []
    for reg, g in groups.items():
        # extra links to the same host add a little weight, a lone mention does not
        score = g["score"] + min(len(g["links"]) - 1, 3) * 0.5
        if score < MIN_SCORE:
            continue
        url, _text = g["best"]
        found_in = [
            {"source": SOURCE_CRAWL, "page": page, "link_text": text, "url": u}
            for _s, u, text, page in sorted(g["links"], key=lambda x: -x[0])
        ][:10]
        out.append(
            {
                "url": url,
                "host": reg,
                "kind": "site",
                "name_guess": link_suggestions._name_guess(
                    reg, [x[2] for x in g["links"] if x[2]]
                ),
                "score": round(score, 2),
                "found_in": found_in,
                "allow_prefixes": [_root(url)],
                "max_pages": 30,
                "max_depth": 2,
                "refresh_days": 7 if g["event"] else 30,
            }
        )
    out.sort(key=lambda c: (-c["score"], c["host"], c["url"]))
    return out


# --------------------------------------------------------------------------- redirect resolution


def http_resolver(
    *,
    sleep: Callable[[float], None] = time.sleep,
    delay: float = RESOLVE_DELAY,
    timeout: float = RESOLVE_TIMEOUT,
    session: Any = None,
) -> Callable[[str], Tuple[str, str]]:
    """A resolver ``url -> (final_url, note)``: polite GETs (robots, UA, delay), no cookies, no body read."""
    import requests
    from http.cookiejar import DefaultCookiePolicy

    sess = session or requests.Session()
    sess.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))
    sess.headers["User-Agent"] = web_source.USER_AGENT

    def allowed(url: str) -> bool:
        origin = _root(url)
        sleep(delay)
        try:
            resp = sess.get(
                origin + "robots.txt", timeout=timeout, allow_redirects=True
            )
        except Exception:  # noqa: BLE001 - unreachable robots: do not touch the site
            return False
        if resp.status_code >= 500:
            return False
        rules = web_source.RobotsRules(resp.text if resp.status_code < 400 else "")
        return rules.allowed(url)

    def resolve(url: str) -> Tuple[str, str]:
        current = url
        for _ in range(web_source.MAX_REDIRECTS + 1):
            if not allowed(current):
                return url, "not resolved: robots.txt"
            sleep(delay)
            try:
                resp = sess.get(
                    current, timeout=timeout, allow_redirects=False, stream=True
                )
            except Exception as exc:  # noqa: BLE001
                return url, f"not resolved: {type(exc).__name__}"
            try:
                loc = resp.headers.get("Location")
                if resp.status_code in (301, 302, 303, 307, 308) and loc:
                    current = web_source.normalize_url(urljoin(current, loc))
                    continue
                if resp.status_code >= 400:
                    return url, f"not resolved: HTTP {resp.status_code}"
                return current, ""
            finally:
                resp.close()
        return url, "not resolved: too many redirects"

    return resolve


def apply_resolution(cand: Dict[str, Any], final: str, note: str) -> Dict[str, Any]:
    """Store the final URL as start_url; both hosts become allowed when the redirect changed host."""
    cand = dict(cand)
    if note:
        cand["notes"] = note
        return cand
    if final == cand["url"]:
        return cand
    prefixes = [_root(final)]
    if link_suggestions.host_of(final) != link_suggestions.host_of(cand["url"]):
        prefixes.append(_root(cand["url"]))
    cand["notes"] = f"redirects from {cand['url']}"
    cand["url"] = final
    cand["allow_prefixes"] = list(dict.fromkeys(prefixes))
    cand["host"] = link_suggestions.registrable_host(link_suggestions.host_of(final))
    return cand


def resolve_candidates(
    cands: Sequence[Dict[str, Any]],
    resolver: Optional[Callable[[str], Tuple[str, str]]] = None,
    max_resolve: int = DEFAULT_MAX_RESOLVE,
    registered_hosts: Iterable[str] = (),
) -> Tuple[List[Dict[str, Any]], int]:
    """Resolve the first ``max_resolve`` site candidates; drops those whose final host is skipped/registered."""
    registered = {link_suggestions.registrable_host(h) for h in registered_hosts}
    resolver = resolver or (http_resolver() if max_resolve > 0 else None)
    out: List[Dict[str, Any]] = []
    done = 0
    for cand in cands:
        if cand.get("kind") == "site" and resolver is not None and done < max_resolve:
            done += 1
            final, note = resolver(cand["url"])
            cand = apply_resolution(cand, final, note)
            host = link_suggestions.host_of(cand["url"])
            if _skipped(host) or cand["host"] in registered:
                continue
        out.append(cand)
    return out, done


def _existing_ids(session: Any) -> set:
    from application.database import db

    return {
        r[0]
        for r in session.query(db.IngestionTarget.id).filter(
            db.IngestionTarget.kind.in_(list(external.KINDS))
        )
    }


def store_candidates(
    session: Any,
    cands: Sequence[Dict[str, Any]],
    *,
    limit: int = DEFAULT_LIMIT,
    max_resolve: int = DEFAULT_MAX_RESOLVE,
    resolver: Optional[Callable[[str], Tuple[str, str]]] = None,
) -> Dict[str, Any]:
    """Resolve and upsert candidates as suggestions: at most ``limit`` new rows; known ones just merge."""
    from application.utils.admin_panel import external_targets

    known = _existing_ids(session)
    registered = external_targets.registered_hosts(session)
    merge = [c for c in cands if link_suggestions.candidate_id(c) in known]
    fresh = [c for c in cands if link_suggestions.candidate_id(c) not in known]
    fresh, resolved = resolve_candidates(fresh, resolver, max_resolve, registered)
    fresh = fresh[:limit]
    res = external_targets.upsert_suggestions(merge + fresh, session=session)
    return {
        "created": res["created"],
        "merged": res["merged"],
        "skipped": res["skipped"],
        "resolved": resolved,
    }


def suggest_from_crawl(
    spec: external.ExternalSpec,
    result: Any,
    session: Any,
    *,
    limit: int = DEFAULT_LIMIT,
    max_resolve: int = DEFAULT_MAX_RESOLVE,
    resolver: Optional[Callable[[str], Tuple[str, str]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Queue the out-of-scope links of a finished crawl as suggestions (nothing is fetched but redirects)."""
    from application.utils.admin_panel import external_targets

    cands = candidates_from_crawl(
        spec, result, external_targets.registered_hosts(session), now
    )
    out = store_candidates(
        session, cands, limit=limit, max_resolve=max_resolve, resolver=resolver
    )
    out["candidates"] = len(cands)
    return out


def suggest_from_repos(
    session: Any,
    limit: int = DEFAULT_LIMIT,
    *,
    like: Optional[str] = None,
    apply: bool = True,
    max_resolve: int = DEFAULT_MAX_RESOLVE,
    resolver: Optional[Callable[[str], Tuple[str, str]]] = None,
) -> Dict[str, Any]:
    """Links in harvested repos -> suggestions. Reads stored chunks only; ``apply=False`` is a dry run."""
    from application.database import db as db_mod
    from application.utils.admin_panel import external_targets
    from application.utils.comprehension import sources

    q = session.query(db_mod.HarvestInput.source_repo).distinct()
    if like:
        q = q.filter(db_mod.HarvestInput.source_repo.ilike(like))
    repos = sorted(r[0] for r in q if r[0])
    repo_chunks = {r: sources.chunks_for_repo(session, r) for r in repos}
    cands = link_suggestions.suggest_links(
        repo_chunks, external_targets.registered_hosts(session)
    )
    for c in cands:
        for f in c["found_in"]:
            f.setdefault("source", SOURCE_GITHUB)
    out: Dict[str, Any] = {
        "repos": len(repos),
        "candidates": len(cands),
        "ranked": cands,
        "created": [],
        "merged": [],
        "skipped": [],
        "resolved": 0,
    }
    if apply:
        out.update(
            store_candidates(
                session, cands, limit=limit, max_resolve=max_resolve, resolver=resolver
            )
        )
    return out
