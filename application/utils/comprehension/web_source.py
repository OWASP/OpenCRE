"""Polite crawler turning an approved ``external_site`` spec into raw chunks.

Output has the repository chunk shape ``(path, index, text)`` where ``path`` is the page URL (the
citation URL for sites, see ``external.page_url``), so ``store.write_raw(..., url_for=lambda p: p)``
makes the site retrievable like any repository.

Politeness and consent, in the order a request meets them:
  * robots.txt (RFC 9309) for our user agent and ``*``; unreachable (5xx / network) means do not crawl;
  * ``Crawl-delay`` and at least ``OWASP_CRAWL_DELAY`` seconds (default 1) between requests to a host;
  * AI-preference signals: ``Content-Usage`` (IETF aipref) in robots.txt and as a response header,
    ``X-Robots-Tag`` and ``<meta name=robots>`` with noindex / none / noai / noarchive. Any of them
    means "do not index" and the page is skipped;
  * conditional requests (ETag / Last-Modified) against a small on-disk cache.
HTML goes through trafilatura (main content as markdown), PDFs through Docling.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

from application.utils.comprehension.external import ExternalSpec
from application.utils.comprehension.sources import split_markdown

USER_AGENT = "OpenCREBot/1.0 (+https://opencre.org; contact via repo issues)"
ROBOTS_TOKEN = "opencrebot"
MIN_PAGE_CHARS = 80
MAX_HTML_BYTES = 5_000_000
MAX_PDF_BYTES = 20_000_000
MAX_REDIRECTS = 3
MAX_SITEMAPS = 20
MAX_CRAWL_DELAY = 30.0  # a Crawl-delay above this is capped, not obeyed to the letter

# Content-Usage keys whose "n" means we must not index the page for AI retrieval.
AI_USAGE_KEYS = ("train-ai", "train-genai", "ai-use", "ai")
BLOCKING_ROBOTS_DIRECTIVES = {"noindex", "none", "noai", "noarchive"}
_SKIP_EXTENSIONS = re.compile(
    r"\.(?:png|jpe?g|gif|svg|webp|ico|css|js|json|xml|zip|gz|tgz|tar|mp[34]|mov|avi|webm|"
    r"docx?|xlsx?|pptx?|woff2?|ttf|eot|rss|atom)$",
    re.IGNORECASE,
)


def default_delay() -> float:
    try:
        return max(0.0, float(os.environ.get("OWASP_CRAWL_DELAY", "1")))
    except ValueError:
        return 1.0


def default_cache_dir() -> Path:
    return Path(
        os.environ.get("OWASP_CRAWL_CACHE_DIR")
        or Path(tempfile.gettempdir()) / "opencre-crawl-cache"
    )


# --------------------------------------------------------------------------- robots.txt


def _pattern_regex(pattern: str) -> "re.Pattern[str]":
    anchored = pattern.endswith("$")
    body = re.escape(pattern.rstrip("$") if anchored else pattern).replace(r"\*", ".*")
    return re.compile(body + ("$" if anchored else ""))


@dataclass
class _Group:
    agents: List[str] = field(default_factory=list)
    rules: List[Tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)
    usage: List[Tuple[str, str]] = field(default_factory=list)  # (path pattern, pref)
    delay: Optional[float] = None


def parse_usage(pref: str) -> Dict[str, bool]:
    """A Content-Usage value (structured-field dictionary, e.g. ``train-ai=n, search=y``) as {key: allowed}."""
    out: Dict[str, bool] = {}
    for item in (pref or "").split(","):
        key, sep, value = item.strip().partition("=")
        if key and sep:
            out[key.strip().lower()] = value.strip().strip('"').lower() not in (
                "n",
                "no",
                "?0",
            )
    return out


def usage_forbids_ai(pref: str) -> bool:
    usage = parse_usage(pref)
    return any(usage.get(k) is False for k in AI_USAGE_KEYS)


class RobotsRules:
    def __init__(self, text: str = "", *, reachable: bool = True) -> None:
        self.reachable = reachable
        self.groups: List[_Group] = []
        self.sitemaps: List[str] = []
        cur: Optional[_Group] = None
        after_agent = False
        for raw in (text or "").splitlines():
            line = raw.split("#", 1)[0].strip()
            name, sep, value = line.partition(":")
            if not sep:
                continue
            name, value = name.strip().lower(), value.strip()
            if name == "user-agent":
                if cur is None or not after_agent:
                    cur = _Group()
                    self.groups.append(cur)
                cur.agents.append(value.lower())
                after_agent = True
                continue
            after_agent = False
            if name == "sitemap":
                self.sitemaps.append(value)
            elif cur is None:
                continue
            elif name in ("allow", "disallow"):
                if value:
                    cur.rules.append((name == "allow", value))
            elif name == "content-usage":
                m = re.match(r"^(\S+)\s+(.+)$", value)
                if m and "=" not in m.group(1):
                    cur.usage.append((m.group(1), m.group(2)))
                else:
                    cur.usage.append(("", value))
            elif name == "crawl-delay":
                try:
                    cur.delay = float(value)
                except ValueError:
                    pass

    def _selected(self, agent: str) -> List[_Group]:
        if agent == "*":
            return [g for g in self.groups if "*" in g.agents]
        return [
            g for g in self.groups if any(a != "*" and a in agent for a in g.agents)
        ]

    @staticmethod
    def _longest(
        patterns: List[Tuple[bool, str]], target: str
    ) -> Optional[Tuple[bool, str]]:
        best: Optional[Tuple[bool, str]] = None
        for allow, pat in patterns:
            if _pattern_regex(pat).match(target) and (
                best is None
                or len(pat) > len(best[1])
                or (len(pat) == len(best[1]) and allow)
            ):
                best = (allow, pat)
        return best

    def allowed(self, url: str) -> bool:
        """Allowed for BOTH our token and ``*`` (stricter than RFC 9309's most-specific-group rule)."""
        if not self.reachable:
            return False
        u = urlparse(url)
        target = (u.path or "/") + (f"?{u.query}" if u.query else "")
        for agent in (ROBOTS_TOKEN, "*"):
            rules = [r for g in self._selected(agent) for r in g.rules]
            hit = self._longest(rules, target)
            if hit is not None and not hit[0]:
                return False
        return True

    def ai_forbidden(self, url: str) -> bool:
        """The longest matching Content-Usage line (a bare one covers everything) forbids AI use."""
        u = urlparse(url)
        target = (u.path or "/") + (f"?{u.query}" if u.query else "")
        for agent in (ROBOTS_TOKEN, "*"):
            best: Optional[Tuple[int, str]] = None
            for g in self._selected(agent):
                for path, pref in g.usage:
                    if (not path or _pattern_regex(path).match(target)) and (
                        best is None or len(path) > best[0]
                    ):
                        best = (len(path), pref)
            if best is not None and usage_forbids_ai(best[1]):
                return True
        return False

    def crawl_delay(self) -> float:
        delays = [
            g.delay
            for agent in (ROBOTS_TOKEN, "*")
            for g in self._selected(agent)
            if g.delay is not None
        ]
        return min(max(delays, default=0.0), MAX_CRAWL_DELAY)


# --------------------------------------------------------------------------- page signals


def _robots_directives(value: str) -> Set[str]:
    """Directives from an X-Robots-Tag / meta robots value that apply to us (unscoped or for our token)."""
    out: Set[str] = set()
    for part in (value or "").lower().split(","):
        part = part.strip()
        scope, sep, rest = part.partition(":")
        if sep and scope.strip() and " " not in scope.strip():
            if scope.strip() not in (ROBOTS_TOKEN, "*"):
                continue
            part = rest.strip()
        out.add(part)
    return out


def exclusion_reason(headers: Dict[str, str], html: str = "") -> Optional[str]:
    """Why a response must not be indexed (AI preference / noindex signals), or ``None``."""
    h = {k.lower(): v for k, v in headers.items()}
    if usage_forbids_ai(h.get("content-usage", "")):
        return "content-usage"
    found = _robots_directives(h.get("x-robots-tag", ""))
    for m in re.finditer(r"<meta\b[^>]*>", html[:200_000], re.IGNORECASE):
        tag = m.group(0)
        name = re.search(r"name\s*=\s*[\"']?([\w-]+)", tag, re.IGNORECASE)
        content = re.search(r"content\s*=\s*[\"']([^\"']*)", tag, re.IGNORECASE)
        if name and content and name.group(1).lower() in ("robots", ROBOTS_TOKEN):
            found |= _robots_directives(content.group(1))
    hit = sorted(found & BLOCKING_ROBOTS_DIRECTIVES)
    return f"robots-meta:{hit[0]}" if hit else None


def _nofollow(headers: Dict[str, str], html: str) -> bool:
    h = {k.lower(): v for k, v in headers.items()}
    found = _robots_directives(h.get("x-robots-tag", ""))
    for m in re.finditer(
        r"<meta\b[^>]*name\s*=\s*[\"']robots[\"'][^>]*content\s*=\s*[\"']([^\"']*)",
        html[:200_000],
        re.IGNORECASE,
    ):
        found |= _robots_directives(m.group(1))
    return bool(found & {"nofollow", "none"})


def _date(value: str) -> str:
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        return "unknown"


def _bare(url: str) -> str:
    """``scheme``-less, ``www``-less form used to compare scope prefixes."""
    u = urlparse(url)
    return u.netloc.lower().removeprefix("www.") + (u.path or "")


def normalize_url(url: str) -> str:
    u = urlparse(urldefrag(url)[0])
    path = u.path or "/"
    return urlunparse((u.scheme.lower(), u.netloc.lower(), path, "", u.query, ""))


# --------------------------------------------------------------------------- crawler


@dataclass
class Page:
    url: str
    title: str
    markdown: str
    fetched_at: str
    last_modified: str
    content_hash: str


@dataclass
class CrawlResult:
    pages: List[Page] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)  # (url, reason)
    requests: int = 0
    not_modified: int = 0
    used_sitemap: bool = False


def _html_to_markdown(html: str, url: str) -> Tuple[str, str]:
    import trafilatura

    text = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_tables=True,
        include_comments=False,
        favor_recall=True,
    )
    meta = trafilatura.extract_metadata(html, default_url=url)
    return (text or "").strip(), ((meta.title if meta else "") or "").strip()


def _pdf_to_markdown(data: bytes) -> str:
    from docling.document_converter import DocumentConverter

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "doc.pdf"
        path.write_bytes(data)
        return DocumentConverter().convert(str(path)).document.export_to_markdown()


class Crawler:
    def __init__(
        self,
        spec: ExternalSpec,
        *,
        max_pages: Optional[int] = None,
        delay: Optional[float] = None,
        cache_dir: Optional[Path] = None,
        write_cache: bool = True,
        use_cache: bool = True,
        session: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        import requests

        self.spec = spec
        self.max_pages = min(max_pages or spec.max_pages, spec.max_pages)
        self.delay = default_delay() if delay is None else delay
        self.cache_dir = cache_dir or default_cache_dir()
        self.write_cache, self.use_cache = write_cache, use_cache
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._sleep, self._clock = sleep, clock
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._last: Dict[str, float] = {}
        self._robots: Dict[str, RobotsRules] = {}
        self.result = CrawlResult()
        self._hosts = {
            urlparse(u).netloc.lower().removeprefix("www.") for u in spec.start_urls
        }
        self._prefixes = [normalize_url(p) for p in spec.allow_prefixes]

    # scope
    def in_scope(self, url: str) -> bool:
        """Same host as a start URL (``www.`` is not a different site) or under an allow prefix."""
        u = urlparse(url)
        if u.scheme not in ("http", "https"):
            return False
        if self._prefixes:
            return any(
                _bare(url).startswith(_bare(p).rstrip("/")) for p in self._prefixes
            )
        return u.netloc.lower().removeprefix("www.") in self._hosts

    # http
    def _throttle(self, host: str, extra: float = 0.0) -> None:
        wait = max(self.delay, extra)
        last = self._last.get(host)
        if last is not None and self._clock() - last < wait:
            self._sleep(wait - (self._clock() - last))
        self._last[host] = self._clock()

    def _get(self, url: str, headers: Optional[Dict[str, str]] = None):
        """One throttled GET; follows up to MAX_REDIRECTS hops that stay in scope and pass robots."""
        for _ in range(MAX_REDIRECTS + 1):
            host = urlparse(url).netloc.lower()
            self._throttle(host, self._robots_for(url).crawl_delay() if url else 0.0)
            self.result.requests += 1
            resp = self.session.get(
                url,
                headers=headers or {},
                timeout=20,
                allow_redirects=False,
                stream=True,
            )
            if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get(
                "Location"
            ):
                nxt = normalize_url(urljoin(url, resp.headers["Location"]))
                resp.close()
                if not self.in_scope(nxt) or not self._robots_for(nxt).allowed(nxt):
                    self.result.skipped.append((nxt, "redirect-out-of-scope"))
                    return None
                url = nxt
                continue
            resp.url = url
            return resp
        return None

    def _body(self, resp: Any, limit: int) -> Optional[bytes]:
        data = b""
        for part in resp.iter_content(65536):
            data += part
            if len(data) > limit:
                resp.close()
                return None
        return data

    def _robots_for(self, url: str) -> RobotsRules:
        u = urlparse(url)
        origin = f"{u.scheme}://{u.netloc}"
        if origin not in self._robots:
            rules = RobotsRules(reachable=False)
            try:
                self._throttle(u.netloc.lower())
                self.result.requests += 1
                resp = self.session.get(
                    origin + "/robots.txt", timeout=20, allow_redirects=True
                )
                if resp.status_code < 400:
                    rules = RobotsRules(resp.text)
                elif resp.status_code < 500:  # RFC 9309: unavailable -> no restrictions
                    rules = RobotsRules("")
            except Exception:  # noqa: BLE001 - unreachable: assume complete disallow
                pass
            self._robots[origin] = rules
        return self._robots[origin]

    # cache
    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")

    def _cache_get(self, url: str) -> Dict[str, Any]:
        if not self.use_cache:
            return {}
        try:
            return json.loads(self._cache_path(url).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _cache_put(self, url: str, entry: Dict[str, Any]) -> None:
        if not (self.write_cache and self.use_cache):
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path(url).write_text(json.dumps(entry), encoding="utf-8")
        except OSError:
            pass

    # discovery
    def sitemap_urls(self) -> List[str]:
        """In-scope page URLs listed in the sitemaps of the start origins ([] when there are none)."""
        found: List[str] = []
        seen_maps: Set[str] = set()
        queue: List[str] = []
        for start in self.spec.start_urls:
            u = urlparse(start)
            origin = f"{u.scheme}://{u.netloc}"
            robots = self._robots_for(start)
            queue += robots.sitemaps or [origin + "/sitemap.xml"]
        while queue and len(seen_maps) < MAX_SITEMAPS:
            sm = queue.pop(0)
            if sm in seen_maps or not self._robots_for(sm).allowed(sm):
                continue
            seen_maps.add(sm)
            try:
                resp = self._get(sm)
                if resp is None or resp.status_code != 200:
                    continue
                data = self._body(resp, MAX_HTML_BYTES * 4)
            except Exception:  # noqa: BLE001 - a bad sitemap just means no sitemap
                continue
            if not data:
                continue
            if data[:2] == b"\x1f\x8b":
                try:
                    data = gzip.decompress(data)
                except OSError:
                    continue
            kids, pages = _parse_sitemap(data)
            queue += [k for k in kids if self.in_scope(normalize_url(k))]
            found += [normalize_url(p) for p in pages]
        out: List[str] = []
        for u in found:
            if (
                self.in_scope(u)
                and u not in out
                and not _SKIP_EXTENSIONS.search(urlparse(u).path)
            ):
                out.append(u)
        return out

    # one page
    def _fetch_page(self, url: str, depth: int) -> List[str]:
        """Fetch and (if allowed) record one URL; returns the in-scope links found on it."""
        skip = self.result.skipped
        if not self._robots_for(url).allowed(url):
            skip.append((url, "robots"))
            return []
        if self._robots_for(url).ai_forbidden(url):
            skip.append((url, "robots-content-usage"))
            return []
        cached = self._cache_get(url)
        cond: Dict[str, str] = {}
        if cached.get("etag"):
            cond["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            cond["If-Modified-Since"] = cached["last_modified"]
        try:
            resp = self._get(url, cond)
        except (
            Exception
        ) as exc:  # noqa: BLE001 - one broken URL must not stop the crawl
            skip.append((url, f"error:{type(exc).__name__}"))
            return []
        if resp is None:
            return []
        try:
            return self._handle(url, resp, cached, depth)
        finally:
            resp.close()

    def _handle(
        self, url: str, resp: Any, cached: Dict[str, Any], depth: int
    ) -> List[str]:
        skip = self.result.skipped
        headers = dict(resp.headers)
        if resp.status_code == 304:
            self.result.not_modified += 1
            return list(cached.get("links") or [])
        if resp.status_code != 200:
            skip.append((url, f"http-{resp.status_code}"))
            return []
        ctype = (headers.get("Content-Type") or "").split(";")[0].strip().lower()
        last_mod = headers.get("Last-Modified", "")
        if ctype == "application/pdf":
            reason = exclusion_reason(headers)
            if reason:
                skip.append((url, reason))
                return []
            data = self._body(resp, MAX_PDF_BYTES)
            if data is None:
                skip.append((url, "too-large"))
                return []
            try:
                markdown, title, links = _pdf_to_markdown(data).strip(), "", []
            except Exception as exc:  # noqa: BLE001
                skip.append((url, f"pdf-error:{type(exc).__name__}"))
                return []
        elif ctype in ("text/html", "application/xhtml+xml"):
            raw = self._body(resp, MAX_HTML_BYTES)
            if raw is None:
                skip.append((url, "too-large"))
                return []
            html = raw.decode(resp.encoding or "utf-8", errors="replace")
            reason = exclusion_reason(headers, html)
            if reason:
                skip.append((url, reason))
                return []
            links = [] if _nofollow(headers, html) else self._links(url, html)
            markdown, title = _html_to_markdown(html, url)
        else:
            skip.append((url, f"type:{ctype or 'unknown'}"))
            return []
        self._cache_put(
            url,
            {
                "etag": headers.get("ETag", ""),
                "last_modified": last_mod,
                "links": links,
            },
        )
        if len(markdown) < MIN_PAGE_CHARS:
            skip.append((url, "too-short"))
            return links
        if title and not markdown.lstrip().startswith("#"):
            markdown = f"# {title}\n\n{markdown}"
        digest = hashlib.sha1(markdown.encode()).hexdigest()
        if digest in {p.content_hash for p in self.result.pages}:
            skip.append((url, "duplicate"))
            return links
        self.result.pages.append(
            Page(
                url=url,
                title=title,
                markdown=markdown,
                fetched_at=self._now().date().isoformat(),
                last_modified=_date(last_mod),
                content_hash=digest,
            )
        )
        return links

    def _links(self, base: str, html: str) -> List[str]:
        import lxml.html

        try:
            tree = lxml.html.fromstring(html)
        except (ValueError, lxml.etree.ParserError):
            return []
        out: List[str] = []
        for a in tree.iter("a"):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            if "nofollow" in (a.get("rel") or "").lower():
                continue
            target = normalize_url(urljoin(base, href))
            if (
                self.in_scope(target)
                and target not in out
                and not _SKIP_EXTENSIONS.search(urlparse(target).path)
            ):
                out.append(target)
        return out

    def crawl(self) -> CrawlResult:
        starts = [normalize_url(u) for u in self.spec.start_urls]
        mapped = self.sitemap_urls()
        if mapped:
            self.result.used_sitemap = True
            order = list(dict.fromkeys(starts + mapped))
            for url in order:
                if len(self.result.pages) >= self.max_pages:
                    break
                self._fetch_page(url, 0)
            return self.result
        seen: Set[str] = set(starts)
        queue: List[Tuple[str, int]] = [(u, 0) for u in starts]
        while queue and len(self.result.pages) < self.max_pages:
            url, depth = queue.pop(0)
            links = self._fetch_page(url, depth)
            if depth >= self.spec.max_depth:
                continue
            for link in links:
                if link not in seen:
                    seen.add(link)
                    queue.append((link, depth + 1))
        return self.result


def _parse_sitemap(data: bytes) -> Tuple[List[str], List[str]]:
    """(child sitemap URLs, page URLs) of a sitemap or sitemap index; entities and network disabled."""
    from lxml import etree

    try:
        root = etree.fromstring(
            data,
            etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False),
        )
    except etree.XMLSyntaxError:
        return [], []
    locs = [
        (el.text or "").strip()
        for el in root.iter()
        if isinstance(el.tag, str) and el.tag.endswith("}loc") or el.tag == "loc"
    ]
    if root.tag.endswith("sitemapindex"):
        return [u for u in locs if u], []
    return [], [u for u in locs if u]


def page_chunks(page: Page, size: int = 1500) -> List[Tuple[str, int, str]]:
    """``(url, index, text)`` chunks of a page; the first carries the provenance line."""
    pieces = split_markdown(page.markdown, size)
    if not pieces:
        return []
    header = (
        f"Source: {page.url} | fetched {page.fetched_at} | "
        f"last modified {page.last_modified}"
    )
    pieces[0] = f"{header}\n\n{pieces[0]}"
    return [(page.url, i, text) for i, text in enumerate(pieces)]


def crawl_chunks(
    spec: ExternalSpec, **kwargs: Any
) -> Tuple[List[Tuple[str, int, str]], CrawlResult]:
    result = Crawler(spec, **kwargs).crawl()
    chunks: List[Tuple[str, int, str]] = []
    for page in result.pages:
        chunks += page_chunks(page)
    return chunks, result
