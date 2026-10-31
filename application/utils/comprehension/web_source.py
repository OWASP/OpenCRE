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
import logging
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

from application.utils.comprehension.external import ExternalSpec
from application.utils.comprehension.sources import split_markdown

logger = logging.getLogger("opencrebot.crawler")

USER_AGENT = "OpenCREBot/1.0 (+https://opencre.org; contact via repo issues)"
ROBOTS_TOKEN = "opencrebot"
MIN_PAGE_CHARS = 80
MAX_HTML_BYTES = 5_000_000
MAX_PDF_BYTES = 20_000_000
MAX_PDF_PAGES = 40  # Docling is slow on CPU: long documents are cut off, not waited for
MAX_BODY_SECONDS = 60.0  # a server that trickles a response is abandoned
MAX_REDIRECTS = 3
MAX_SITEMAPS = 20
MAX_EXTERNAL_LINKS = 500  # out-of-scope links remembered per crawl (discovery input)
NAV_LINE_SHARE = 0.6  # a line on this share of the pages is site chrome, not content
NAV_MIN_PAGES = 4
MAX_CRAWL_DELAY = 30.0  # a Crawl-delay above this is capped, not obeyed to the letter

# Content-Usage keys whose "n" means we must not index the page for AI retrieval.
AI_USAGE_KEYS = ("train-ai", "train-genai", "ai-use", "ai")
BLOCKING_ROBOTS_DIRECTIVES = {"noindex", "none", "noai", "noarchive"}
_SKIP_EXTENSIONS = re.compile(
    r"\.(?:png|jpe?g|gif|svg|webp|ico|css|js|json|xml|zip|gz|tgz|tar|mp[34]|mov|avi|webm|"
    r"docx?|xlsx?|pptx?|woff2?|ttf|eot|rss|atom)$",
    re.IGNORECASE,
)


def max_seconds() -> float:
    """Wall-clock budget of one crawl (OWASP_CRAWL_MAX_SECONDS, default 15 minutes)."""
    try:
        return max(5.0, float(os.environ.get("OWASP_CRAWL_MAX_SECONDS", "900")))
    except ValueError:
        return 900.0


def pdf_enabled() -> bool:
    """PDFs go through Docling (slow on CPU): off unless OWASP_CRAWL_PDF=1."""
    return (os.environ.get("OWASP_CRAWL_PDF", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def js_enabled() -> bool:
    """Render script-only pages in a headless browser: off unless OWASP_CRAWL_JS=1."""
    return (os.environ.get("OWASP_CRAWL_JS", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def pdf_seconds() -> float:
    """Wall-clock cap for converting one PDF (OWASP_CRAWL_PDF_SECONDS, default 60)."""
    try:
        return max(1.0, float(os.environ.get("OWASP_CRAWL_PDF_SECONDS", "60")))
    except ValueError:
        return 60.0


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
    stopped: str = (
        ""  # why the crawl ended early ("time-budget"), empty when it ran to its caps
    )
    # out-of-scope http(s) links seen on crawled pages, never fetched: (url, anchor_text, found_on_page)
    external_links: List[Tuple[str, str, str]] = field(default_factory=list)


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


_PDF_CONVERTER: Any = None


def _pdf_converter() -> Any:
    """One Docling converter per process (loading its models takes ~10 s)."""
    global _PDF_CONVERTER
    if _PDF_CONVERTER is None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        opts = PdfPipelineOptions()
        opts.do_ocr = False  # OCR and table recognition are very slow on CPU
        opts.do_table_structure = False
        _PDF_CONVERTER = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
    return _PDF_CONVERTER


def _pdf_to_markdown(data: bytes) -> str:
    """PDF text via Docling without OCR or table recognition."""
    converter = _pdf_converter()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "doc.pdf"
        path.write_bytes(data)
        result = converter.convert(str(path), max_num_pages=MAX_PDF_PAGES)
        return result.document.export_to_markdown()


RENDER_TIMEOUT_MS = 30_000


def render_with_playwright(url: str) -> str:
    """Rendered HTML of ``url`` from headless Firefox (the browser the images install).

    Requests to other hosts are blocked, so a page cannot pull the crawler into third parties.
    """
    from playwright.sync_api import sync_playwright

    host = urlparse(url).netloc.lower()
    with sync_playwright() as pw:
        browser = pw.firefox.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if urlparse(route.request.url).netloc.lower() == host
                    else route.abort()
                ),
            )
            page.goto(url, wait_until="networkidle", timeout=RENDER_TIMEOUT_MS)
            return page.content()
        finally:
            browser.close()


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
        budget_seconds: Optional[float] = None,
        renderer: Optional[Callable[[str], str]] = None,
    ) -> None:
        import requests

        self._renderer = renderer or render_with_playwright

        self.spec = spec
        self.max_pages = min(max_pages or spec.max_pages, spec.max_pages)
        self.delay = default_delay() if delay is None else delay
        self.cache_dir = cache_dir or default_cache_dir()
        self.write_cache, self.use_cache = write_cache, use_cache
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._sleep, self._clock = sleep, clock
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._budget = max_seconds() if budget_seconds is None else budget_seconds
        self._started: Optional[float] = None
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
            logger.debug("GET %s", url)
            began = self._clock()
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
            logger.info(
                "GET %s -> %s in %.1fs", url, resp.status_code, self._clock() - began
            )
            return resp
        return None

    def _body(self, resp: Any, limit: int) -> Optional[bytes]:
        data = b""
        deadline = self._clock() + MAX_BODY_SECONDS
        for part in resp.iter_content(65536):
            if self._clock() > deadline:
                logger.warning("abandoned slow response %s", getattr(resp, "url", ""))
                return None
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
        before_skips, before_pages = len(skip), len(self.result.pages)
        try:
            return self._fetch_page_inner(url, depth)
        finally:
            for u, why in skip[before_skips:]:
                logger.info("skipped %s (%s)", u, why)
            if len(self.result.pages) > before_pages:
                page = self.result.pages[-1]
                logger.info("page ok %s (%d chars)", page.url, len(page.markdown))

    def _fetch_page_inner(self, url: str, depth: int) -> List[str]:
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
            for ext_url, text, page in cached.get("external") or []:
                self._add_external(ext_url, text, page)
            return list(cached.get("links") or [])
        if resp.status_code != 200:
            skip.append((url, f"http-{resp.status_code}"))
            return []
        ctype = (headers.get("Content-Type") or "").split(";")[0].strip().lower()
        last_mod = headers.get("Last-Modified", "")
        if ctype == "application/pdf":
            if not pdf_enabled():
                skip.append((url, "pdf-disabled"))
                return []
            reason = exclusion_reason(headers)
            if reason:
                skip.append((url, reason))
                return []
            data = self._body(resp, MAX_PDF_BYTES)
            if data is None:
                skip.append((url, "too-large"))
                return []
            logger.info(
                "PDF %s: %d bytes, converting (max %d pages)",
                url,
                len(data),
                MAX_PDF_PAGES,
            )
            began = self._clock()
            try:
                markdown, title, links = self._pdf_text(data).strip(), "", []
                logger.info("PDF %s converted in %.1fs", url, self._clock() - began)
            except TimeoutError:
                logger.warning("PDF %s: gave up after %.0fs", url, pdf_seconds())
                skip.append((url, "pdf-timeout"))
                return []
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
            if len(markdown) < MIN_PAGE_CHARS and js_enabled():
                rendered = self._render(url, skip)
                if rendered is None:
                    return links
                html = rendered
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
                "external": [e for e in self.result.external_links if e[2] == url],
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

    def _pdf_text(self, data: bytes) -> str:
        """Convert in a worker thread so a slow PDF costs at most ``pdf_seconds()``.

        Docling cannot be interrupted: after a timeout the worker finishes in the background
        (bounded by MAX_PDF_PAGES) while the crawl moves on.
        """
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(_pdf_to_markdown, data)
        pool.shutdown(wait=False)
        try:
            return future.result(timeout=pdf_seconds())
        except FutureTimeout as exc:
            raise TimeoutError from exc

    def _render(self, url: str, skip: List[Tuple[str, str]]) -> Optional[str]:
        """HTML of a script-only page from the browser fallback; None (and a skip) on failure."""
        self._throttle(urlparse(url).netloc.lower())
        logger.info("JS fallback: rendering %s", url)
        try:
            return self._renderer(url)
        except Exception as exc:  # noqa: BLE001
            skip.append((url, f"js-error:{type(exc).__name__}"))
            return None

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
            try:
                target = normalize_url(urljoin(base, href))
                if not self.in_scope(target):
                    self._add_external(target, a.text_content(), base)
                    continue
                if target not in out and not _SKIP_EXTENSIONS.search(
                    urlparse(target).path
                ):
                    out.append(target)
            except (
                ValueError
            ):  # a malformed href (e.g. "http://[bad") must not stop the crawl
                logger.debug("ignored malformed link %r on %s", href, base)
        return out

    def _add_external(self, url: str, text: str, found_on: str) -> None:
        """Remember an out-of-scope link (never fetched); deduped by URL and capped."""
        if (
            urlparse(url).scheme not in ("http", "https")
            or len(self.result.external_links) >= MAX_EXTERNAL_LINKS
            or _SKIP_EXTENSIONS.search(urlparse(url).path)
            or any(e[0] == url for e in self.result.external_links)
        ):
            return
        text = re.sub(r"\s+", " ", text or "").strip()[:120]
        self.result.external_links.append((url, text, found_on))

    def _over_budget(self) -> bool:
        if self._started is None:
            self._started = self._clock()
        if self._clock() - self._started > self._budget:
            if not self.result.stopped:
                logger.warning(
                    "crawl stopped: %.0fs time budget used (%d pages so far)",
                    self._budget,
                    len(self.result.pages),
                )
            self.result.stopped = "time-budget"
            return True
        return False

    def crawl(self) -> CrawlResult:
        self._started = self._clock()
        starts = [normalize_url(u) for u in self.spec.start_urls]
        mapped = self.sitemap_urls()
        if mapped:
            self.result.used_sitemap = True
            order = list(dict.fromkeys(starts + mapped))
            for url in order:
                if len(self.result.pages) >= self.max_pages or self._over_budget():
                    break
                self._fetch_page(url, 0)
            strip_nav(self.result.pages)
            return self.result
        seen: Set[str] = set(starts)
        queue: List[Tuple[str, int]] = [(u, 0) for u in starts]
        while queue and len(self.result.pages) < self.max_pages:
            if self._over_budget():
                break
            url, depth = queue.pop(0)
            logger.debug(
                "crawl: %d/%d pages, %d queued, depth %d",
                len(self.result.pages),
                self.max_pages,
                len(queue),
                depth,
            )
            links = self._fetch_page(url, depth)
            if depth >= self.spec.max_depth:
                continue
            for link in links:
                if link not in seen:
                    seen.add(link)
                    queue.append((link, depth + 1))
        strip_nav(self.result.pages)
        return self.result


def strip_nav(pages: List[Page]) -> None:
    """Drop lines repeated verbatim on most pages (site menus, footers) from every page's markdown."""
    if len(pages) < NAV_MIN_PAGES:
        return
    counts: Dict[str, int] = {}
    for page in pages:
        for line in {ln.strip() for ln in page.markdown.splitlines()}:
            if re.search(r"\w", line):
                counts[line] = counts.get(line, 0) + 1
    chrome = {ln for ln, n in counts.items() if n >= NAV_LINE_SHARE * len(pages)}
    if not chrome:
        return
    for page in pages:
        page.markdown = "\n".join(
            ln for ln in page.markdown.splitlines() if ln.strip() not in chrome
        ).strip()


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
