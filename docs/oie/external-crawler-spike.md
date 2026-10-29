# External crawler spike: trafilatura vs Crawl4AI vs Scrapy

Need: HTML main content to markdown, sitemap support, robots.txt (RFC 9309), politeness, JS pages
(Playwright is installed), weight, licence. Claims below were checked against each project's docs
(trafilatura.readthedocs.io, docs.crawl4ai.com + its GitHub README, docs.scrapy.org settings page,
IETF draft-ietf-aipref-attach). "Not documented" means the page we read did not say.

| | trafilatura 2.3.1 | Crawl4AI | Scrapy |
|---|---|---|---|
| Licence | Apache-2.0 (GPLv3+ before 1.8.0) | Apache-2.0 plus a required attribution (badge or text credit) | BSD (not on the settings page) |
| Main content to markdown | Yes (text, markdown, JSON, XML...); jusText/readability fallbacks | Yes (`result.markdown`) | No: it fetches, you extract |
| Sitemaps | Yes (XML/TXT, feeds), CLI `--explore` | Yes (`AsyncUrlSeeder`) | Yes (SitemapSpider) |
| robots.txt | Its spider "implements politeness rules" where applicable; fetch utilities do not enforce it | Not documented on pages read | `ROBOTSTXT_OBEY` exists but defaults to False (only the project template turns it on); `ROBOTSTXT_USER_AGENT` |
| Throttling | Waits between requests to a host, no documented default | Not documented (rate limits quoted are for the hosted cloud) | `DOWNLOAD_DELAY` (+jitter), AutoThrottle, HTTP cache |
| JS pages | No | Yes, drives a browser (Playwright, `crawl4ai-setup` downloads it) | No (needs a plugin) |
| Weight | Light: lxml, courlan, htmldate, jusText (a handful of small pure-Python wheels) | Heavy: browser install, many deps | Medium: Twisted reactor, own event loop |
| aipref (`Content-Usage`) / `noai` | None of the three | None | None |

## Verdict

Use **trafilatura for extraction only** (HTML to markdown, main-content isolation, boilerplate removal) and keep
fetch, robots and politeness in our own small code on `requests`. Reasons:

- No library implements the pieces we are most accountable for: the IETF aipref `Content-Usage` header and
  robots.txt lines, `X-Robots-Tag`/meta `noai`/`noindex`, our own User-Agent, ETag/Last-Modified conditional
  requests, and the allow-prefix/page/depth caps. We must write those whichever we pick, so the framework buys little.
- Scrapy's robots handling is opt-in and it brings a reactor into a Flask/cron codebase; Crawl4AI is a browser
  stack (heavy install, attribution clause) for a crawl of at most a few hundred static chapter pages.
- robots.txt is parsed with the stdlib `urllib.robotparser` (RFC 9309 semantics: longest match, `*` fallback).
- Playwright fallback for JS-only sites is deliberately **not** built yet; no approved site needs it. If one does,
  render with the already installed Playwright and feed the HTML to the same extractor.
- PDFs go through Docling (already a dependency), but they are OFF unless OWASP_CRAWL_PDF=1: with OCR and table recognition disabled and at most 40 pages, one converter load still costs ~10 s on CPU. The crawl also has a wall-clock budget (OWASP_CRAWL_MAX_SECONDS, default 900) and logs every request, page and skip (logger `opencrebot`; `--debug` in the script adds queue steps).

Added dependency: `trafilatura` (requirements.txt).
