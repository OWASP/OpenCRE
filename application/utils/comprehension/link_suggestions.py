"""Suggest external knowledge sources (project websites, YouTube channels) from links in harvested repos.

Pure functions, no network: they read chunk text and return ranked candidates. Persisting them as
``suggested`` targets is ``admin_panel.external_targets.upsert_suggestions``; nothing here crawls.

A candidate is ``{url, host, name_guess, kind (site|youtube), score, found_in:[{repo,file,link_text,url}]}``
(youtube candidates also carry ``channel_id`` / ``playlist_id``).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qs, urlparse

# Hosts that are never a knowledge source of their own (code hosting, social, chat, shorteners, badges, images).
SKIP_HOSTS = frozenset(
    {
        "github.com",
        "githubusercontent.com",
        "youtube.com",
        "gitlab.com",
        "bitbucket.org",
        "twitter.com",
        "x.com",
        "t.co",
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "reddit.com",
        "slack.com",
        "owasp.slack.com",
        "meetup.com",
        "discord.com",
        "discord.gg",
        "bit.ly",
        "tinyurl.com",
        "goo.gl",
        "ow.ly",
        "buff.ly",
        "shields.io",
        "badgen.net",
        "badge.fury.io",
        "travis-ci.org",
        "codecov.io",
        "coveralls.io",
        "img.shields.io",
        "imgur.com",
        "gravatar.com",
        "googleusercontent.com",
        "docs.google.com",
        "drive.google.com",
        "forms.gle",
        "creativecommons.org",
        "wikipedia.org",
        "medium.com",
        "youtu.be",
        "w3.org",
        "mozilla.org",
        "npmjs.com",
        "pypi.org",
        "hub.docker.com",
        "example.com",
    }
)
_IMG_EXT = re.compile(r"\.(png|jpe?g|gif|svg|webp|ico|bmp|pdf|zip|tar|gz)$", re.I)
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}

_FRONT_KEYS = {"homepage", "website", "url", "site"}
_TEXT_HINTS = (
    "website",
    "web site",
    "docs",
    "documentation",
    "conference",
    "event",
    "home",
    "homepage",
    "www",
)

_MD_LINK = re.compile(r"(?<!!)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*<?(https?://[^)\s>]+)")
_HTML_LINK = re.compile(
    r"<a\s[^>]*href=[\"'](https?://[^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S
)
_BARE = re.compile(r"https?://[^\s<>\"')\]]+")
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)
_TAGS = re.compile(r"<[^>]+>|!\[[^\]]*\]\([^)]*\)")


def _strip_url(url: str) -> str:
    return url.rstrip(".,;:!?*_`'\"")


def host_of(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def registrable_host(host: str) -> str:
    """Heuristic eTLD+1 (no public-suffix list): ``docs.foo.org`` -> ``foo.org``, ``a.foo.co.uk`` -> ``foo.co.uk``."""
    parts = [p for p in host.lower().split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    if len(parts[-1]) == 2 and parts[-2] in _SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _skipped_host(host: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in SKIP_HOSTS)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub("", text or "")).strip()


def extract_links(text: str) -> List[Dict[str, Any]]:
    """External http(s) links in markdown/HTML/front-matter text: ``{url, link_text, front_key}``."""
    out: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()

    def add(url: str, link_text: str = "", front_key: str = "") -> None:
        url = _strip_url(url)
        if url and (url, link_text) not in seen:
            seen.add((url, link_text))
            out.append({"url": url, "link_text": link_text, "front_key": front_key})

    body = text or ""
    fm = _FRONT.match(body)
    if fm:
        for line in fm.group(1).splitlines():
            key, _, val = line.partition(":")
            if key.strip().lower() in _FRONT_KEYS:
                m = _BARE.search(val)
                if m:
                    add(m.group(0), front_key=key.strip().lower())
        body = body[fm.end() :]
    spans: List[Tuple[int, int]] = []
    for m in _MD_LINK.finditer(body):
        add(m.group(2), _clean_text(m.group(1)))
        spans.append(m.span())
    for m in _HTML_LINK.finditer(body):
        add(m.group(1), _clean_text(m.group(2)))
        spans.append(m.span())
    for m in _BARE.finditer(body):
        if not any(a <= m.start() < b for a, b in spans):
            add(m.group(0))
    return out


def _is_root_doc(path: str) -> bool:
    p = (path or "").lstrip("./")
    return "/" not in p and p.lower().startswith(("readme", "index"))


def _youtube_ref(url: str) -> Optional[Dict[str, str]]:
    """Channel / playlist / handle reference of a YouTube URL; ``None`` for watch links and the like."""
    u = urlparse(url)
    host = host_of(url)
    if host not in ("youtube.com", "m.youtube.com"):
        return None
    segs = [s for s in u.path.split("/") if s]
    if not segs:
        return None
    if segs[0].startswith("@"):
        return {"channel_id": segs[0]}
    if segs[0] == "channel" and len(segs) > 1:
        return {"channel_id": segs[1]}
    if segs[0] in ("c", "user") and len(segs) > 1:
        return {"channel_id": "@" + segs[1]}
    if segs[0] == "playlist":
        pl = (parse_qs(u.query).get("list") or [""])[0]
        return {"playlist_id": pl} if pl else None
    return None


def _name_guess(host: str, texts: Sequence[str]) -> str:
    for t in texts:
        low = t.lower()
        if 3 <= len(t) <= 60 and not any(h == low for h in _TEXT_HINTS) and " " in t:
            if "http" not in low and "." not in low:
                return t
    label = registrable_host(host).split(".")[0]
    return label.replace("-", " ").replace("_", " ").title()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60]


def _signal(link: Dict[str, Any], path: str) -> float:
    if link["front_key"]:
        loc = 5.0
    elif _is_root_doc(path):
        loc = 3.0
    else:
        loc = 1.0
    text = (link["link_text"] or "").lower()
    if any(h in text for h in _TEXT_HINTS):
        loc += 2.0
    return loc


def collect_links(
    repo: str, chunks: Iterable[Tuple[str, int, str]]
) -> List[Dict[str, Any]]:
    """Every candidate-able external link of one repo as ``{repo, file, link_text, url, signal}``."""
    out = []
    for path, _idx, text in chunks:
        for link in extract_links(text):
            out.append(
                {
                    "repo": repo,
                    "file": path,
                    "link_text": link["link_text"],
                    "url": link["url"],
                    "signal": _signal(link, path),
                }
            )
    return out


def rank_candidates(
    links: Iterable[Dict[str, Any]], registered_hosts: Iterable[str] = ()
) -> List[Dict[str, Any]]:
    """Group links by registrable host (or YouTube channel), drop skipped/registered ones, rank by score."""
    registered = {registrable_host(h) for h in registered_hosts}
    groups: Dict[str, Dict[str, Any]] = {}
    for ln in links:
        url = ln["url"]
        host = host_of(url)
        if not host or _IMG_EXT.search(urlparse(url).path):
            continue
        yt = _youtube_ref(url)
        if yt:
            ident = yt.get("channel_id") or yt.get("playlist_id", "")
            key, kind, reg = f"yt:{ident.lower()}", "youtube", "youtube.com"
        else:
            reg = registrable_host(host)
            if _skipped_host(host) or reg in registered or _skipped_host(reg):
                continue
            # owasp.org project/chapter pages are GitHub-backed, already covered as repos
            if reg == "owasp.org" and urlparse(url).path.startswith("/www-"):
                continue
            key, kind = reg, "site"
        g = groups.setdefault(
            key,
            {"kind": kind, "host": reg, "links": [], "yt": yt or {}, "best": ln},
        )
        g["links"].append(ln)
        if ln["signal"] > g["best"]["signal"]:
            g["best"] = ln
    out = []
    for key, g in groups.items():
        projects = {ln["repo"] for ln in g["links"]}
        score = g["best"]["signal"] + min(len(projects) - 1, 5) * 1.5
        found_in = []
        seen = set()
        for ln in sorted(g["links"], key=lambda x: -x["signal"]):
            k = (ln["repo"], ln["file"], ln["url"])
            if k in seen:
                continue
            seen.add(k)
            found_in.append({f: ln[f] for f in ("repo", "file", "link_text", "url")})
        texts = [ln["link_text"] for ln in g["links"] if ln["link_text"]]
        cand: Dict[str, Any] = {
            "url": g["best"]["url"],
            "host": g["host"],
            "kind": g["kind"],
            "score": round(score, 2),
            "found_in": found_in[:10],
        }
        if g["kind"] == "youtube":
            cand.update(g["yt"])
            ident = g["yt"].get("channel_id") or g["yt"].get("playlist_id", "")
            cand["name_guess"] = ident.lstrip("@") or "YouTube"
        else:
            cand["name_guess"] = _name_guess(g["host"], texts)
        out.append(cand)
    out.sort(key=lambda c: (-c["score"], c["host"], c["url"]))
    return out


def suggest_links(
    repo_chunks: Dict[str, Sequence[Tuple[str, int, str]]],
    registered_hosts: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    """Ranked candidates from ``{repo: [(path, idx, text)]}``."""
    links: List[Dict[str, Any]] = []
    for repo, chunks in repo_chunks.items():
        links.extend(collect_links(repo, chunks))
    return rank_candidates(links, registered_hosts)


def candidate_id(cand: Dict[str, Any]) -> str:
    """Target id for a candidate: slug of the host (``yt-<handle>`` for YouTube)."""
    if cand.get("kind") == "youtube":
        ident = cand.get("channel_id") or cand.get("playlist_id") or "channel"
        return ("yt-" + _slugify(ident))[:61]
    return _slugify(cand["host"])
