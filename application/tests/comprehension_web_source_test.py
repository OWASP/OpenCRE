import tempfile
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from application.utils.comprehension import external, external_ingest, web_source
from application.utils.comprehension.web_source import Crawler, RobotsRules
from application.utils.oie_scheduler import external_sources, jobs, schedule_settings

PARA = (
    "OWASP chapters organise meetups, training days and conferences for local security people, "
    "and this page describes how the programme, the venue and the sponsors fit together. "
)


def html(title, links=(), head="", paras=3):
    body = "".join(f"<p>{PARA}{title} part {i}.</p>" for i in range(paras))
    anchors = "".join(f'<a href="{h}">link</a> ' for h in links)
    return (
        f"<html><head><title>{title}</title>{head}</head><body><nav>{anchors}</nav>"
        f"<article><h1>{title}</h1>{body}</article></body></html>"
    )


class Site:
    """Local HTTP server with a routes table ``path -> (status, headers, body)``."""

    def __init__(self, routes):
        self.routes, self.log = routes, []
        site = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                site.log.append(self.path)
                route = site.routes.get(self.path)
                if callable(route):
                    route = route(site)
                if route is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                status, headers, body = route
                headers = dict(headers)
                etag = headers.get("ETag")
                if etag and self.headers.get("If-None-Match") == etag:
                    self.send_response(304)
                    self.end_headers()
                    return
                data = body.encode() if isinstance(body, str) else body
                self.send_response(status)
                headers.setdefault("Content-Type", "text/html; charset=utf-8")
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def ok(body, **headers):
    return (200, headers, body)


def build_routes(with_sitemap=False):
    r = {
        "/": ok(
            html(
                "Home",
                [
                    "/a",
                    "/b",
                    "/private/x",
                    "/noindex",
                    "/hdr-noindex",
                    "/noai/x",
                    "/usage-header",
                    "/dup",
                    "/short",
                    "/deep1",
                    "/logo.png",
                    "/data",
                    "http://elsewhere.invalid/x",
                ],
            )
        ),
        "/a": ok(
            html("Page A"),
            ETag='"a1"',
            **{"Last-Modified": "Wed, 01 Oct 2025 10:00:00 GMT"},
        ),
        "/b": ok(html("Page B")),
        "/dup": ok(html("Page A")),
        "/short": ok("<html><body><p>tiny</p></body></html>"),
        "/private/x": ok(html("Private")),
        "/noindex": ok(
            html("No index", head='<meta name="robots" content="noindex, follow">')
        ),
        "/hdr-noindex": ok(html("Hdr"), **{"X-Robots-Tag": "noai"}),
        "/noai/x": ok(html("NoAI path")),
        "/usage-header": ok(html("Usage hdr"), **{"Content-Usage": "train-ai=n"}),
        "/deep1": ok(html("Deep 1", ["/deep2"])),
        "/deep2": ok(html("Deep 2", ["/deep3"])),
        "/deep3": ok(html("Deep 3")),
        "/data": (200, {"Content-Type": "image/png"}, b"\x89PNG"),
        "/robots.txt": lambda site: ok(
            "User-agent: *\nDisallow: /private/\nContent-Usage: /noai/ train-ai=n\n"
            + (f"Sitemap: {site.base}/sitemap.xml\n" if with_sitemap else ""),
            **{"Content-Type": "text/plain"},
        ),
    }
    if with_sitemap:
        r["/sitemap.xml"] = lambda site: ok(
            '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{site.base}/a</loc></url><url><loc>{site.base}/b</loc></url>"
            f"<url><loc>{site.base}/private/x</loc></url>"
            "<url><loc>http://elsewhere.invalid/z</loc></url></urlset>",
            **{"Content-Type": "application/xml"},
        )
    return r


def spec_for(site, **kw):
    return external.ExternalSpec(
        id="test-site",
        name="Test",
        status=external.STATUS_APPROVED,
        start_urls=[site.base + "/"],
        **kw,
    )


class WebSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sites = []

    def site(self, **kw):
        s = Site(build_routes(**kw))
        self.sites.append(s)
        self.addCleanup(s.close)
        return s

    def crawler(self, site, **kw):
        kw.setdefault("delay", 0)
        kw.setdefault("cache_dir", Path(self.tmp.name))
        spec_kw = {k: kw.pop(k) for k in ("max_pages", "max_depth") if k in kw}
        spec_kw.setdefault("max_depth", 2)
        max_pages = spec_kw.pop("max_pages", None)
        return Crawler(spec_for(site, **spec_kw), max_pages=max_pages, **kw)

    def test_crawl_respects_robots_and_ai_preferences(self):
        site = self.site()
        res = self.crawler(site).crawl()
        urls = {p.url.replace(site.base, "") for p in res.pages}
        self.assertEqual(urls, {"/", "/a", "/b", "/deep1", "/deep2"})
        reasons = {u.replace(site.base, ""): r for u, r in res.skipped}
        self.assertEqual(reasons["/private/x"], "robots")
        self.assertEqual(reasons["/noai/x"], "robots-content-usage")
        self.assertEqual(reasons["/noindex"], "robots-meta:noindex")
        self.assertEqual(reasons["/hdr-noindex"], "robots-meta:noai")
        self.assertEqual(reasons["/usage-header"], "content-usage")
        self.assertEqual(reasons["/short"], "too-short")
        self.assertEqual(reasons["/dup"], "duplicate")
        self.assertEqual(reasons["/data"], "type:image/png")
        for never in ("/private/x", "/noai/x", "/logo.png"):
            self.assertNotIn(never, site.log)
        self.assertFalse(any("elsewhere" in u for u, _ in res.skipped))

    def test_caps(self):
        site = self.site()
        self.assertEqual(len(self.crawler(site, max_pages=2).crawl().pages), 2)
        res = self.crawler(site, max_depth=0).crawl()
        self.assertEqual([p.url for p in res.pages], [site.base + "/"])
        res = self.crawler(site, max_depth=1).crawl()
        self.assertNotIn("/deep2", {p.url.replace(site.base, "") for p in res.pages})
        # the CLI cap can only lower the spec's cap
        self.assertEqual(self.crawler(site, max_pages=3).max_pages, 3)
        c = Crawler(spec_for(site, max_pages=4), max_pages=50, delay=0)
        self.assertEqual(c.max_pages, 4)

    def test_time_budget_stops_a_runaway_crawl(self):
        site = self.site()
        ticks = iter(range(0, 1000, 10))  # every clock read advances 10 "seconds"
        res = self.crawler(
            site, clock=lambda: float(next(ticks)), budget_seconds=25
        ).crawl()
        self.assertEqual(res.stopped, "time-budget")
        self.assertLess(len(res.pages), 5)

    def test_progress_is_logged_so_a_stall_shows_where(self):
        site = self.site()
        with self.assertLogs("opencrebot.crawler", level="DEBUG") as cm:
            self.crawler(site, max_pages=2).crawl()
        text = "\n".join(cm.output)
        self.assertIn("GET ", text)
        self.assertIn("page ok ", text)
        self.assertIn("crawl: ", text)

    def test_pdfs_are_off_unless_enabled(self):
        from unittest import mock

        from application.utils.comprehension import web_source

        with mock.patch.dict("os.environ", {}, clear=False):
            __import__("os").environ.pop("OWASP_CRAWL_PDF", None)
            self.assertFalse(web_source.pdf_enabled())
        with mock.patch.dict("os.environ", {"OWASP_CRAWL_PDF": "1"}):
            self.assertTrue(web_source.pdf_enabled())

    def test_throttle_between_requests(self):
        site = self.site()
        sleeps = []
        res = self.crawler(site, delay=1.0, sleep=sleeps.append, max_pages=3).crawl()
        self.assertGreaterEqual(len(sleeps), res.requests - 1)
        self.assertTrue(all(0 < s <= 1.0 for s in sleeps))

    def test_sitemap_is_the_inventory(self):
        site = self.site(with_sitemap=True)
        res = self.crawler(site).crawl()
        self.assertTrue(res.used_sitemap)
        urls = {p.url.replace(site.base, "") for p in res.pages}
        self.assertEqual(
            urls, {"/", "/a", "/b"}
        )  # no link following, robots still applies
        self.assertNotIn("/deep1", site.log)
        self.assertNotIn("/private/x", site.log)

    def test_conditional_requests_use_cache_only_when_written(self):
        site = self.site()
        self.crawler(site, max_depth=1).crawl()
        again = self.crawler(site, max_depth=1).crawl()
        self.assertEqual(again.not_modified, 1)
        self.assertNotIn("/a", {p.url.replace(site.base, "") for p in again.pages})
        # a dry run (write_cache=False) must not teach the cache about pages nobody stored
        with tempfile.TemporaryDirectory() as fresh:
            self.crawler(
                site, max_depth=1, cache_dir=Path(fresh), write_cache=False
            ).crawl()
            second = self.crawler(site, max_depth=1, cache_dir=Path(fresh)).crawl()
            self.assertEqual(second.not_modified, 0)

    def test_chunks_shape_and_provenance_header(self):
        site = self.site()
        now = datetime(2026, 10, 29)
        chunks, res = web_source.crawl_chunks(
            spec_for(site, max_depth=1),
            delay=0,
            cache_dir=Path(self.tmp.name),
            now=lambda: now,
        )
        self.assertTrue(chunks)
        for url, idx, text in chunks:
            self.assertTrue(url.startswith(site.base))
            self.assertIsInstance(idx, int)
            self.assertIsInstance(text, str)
        first_a = next(c for c in chunks if c[0] == site.base + "/a" and c[1] == 0)
        self.assertTrue(
            first_a[2].startswith(
                f"Source: {site.base}/a | fetched 2026-10-29 | last modified 2025-10-01\n"
            )
        )
        later = [c for c in chunks if c[1] > 0]
        self.assertFalse(any(c[2].startswith("Source:") for c in later))

    def test_dry_run_writes_nothing_and_apply_goes_through_write_raw(self):
        site = self.site()
        spec = spec_for(site, max_depth=1)
        with mock.patch(
            "application.utils.comprehension.store.write_raw"
        ) as write, mock.patch.object(
            web_source, "default_cache_dir", return_value=Path(self.tmp.name)
        ), mock.patch.object(
            web_source, "default_delay", return_value=0
        ):
            out = external_ingest.ingest_spec(spec, apply=False)
            write.assert_not_called()
            self.assertEqual(out["written"], 0)
            self.assertEqual(list(Path(self.tmp.name).iterdir()), [])
            write.return_value = 7
            embed = mock.Mock()
            out = external_ingest.ingest_spec(
                spec, apply=True, database="db", embed=embed, workers=3
            )
        self.assertEqual(out["written"], 7)
        args, kw = write.call_args
        self.assertEqual(args[:2], ("db", "ext-test-site"))
        self.assertEqual(kw["url_for"]("https://x/y"), "https://x/y")
        self.assertEqual(kw["workers"], 3)
        self.assertTrue(all(len(c) == 3 for c in args[2]))

    def test_unreachable_robots_means_no_crawl(self):
        site = self.site()
        site.routes["/robots.txt"] = (503, {}, "down")
        res = self.crawler(site).crawl()
        self.assertEqual(res.pages, [])
        self.assertEqual(res.skipped[0][1], "robots")


class RobotsRulesTest(unittest.TestCase):
    def test_longest_match_wildcards_and_both_agents(self):
        r = RobotsRules(
            "User-agent: *\nDisallow: /a/\nAllow: /a/ok\nDisallow: /*.pdf$\n"
            "User-agent: OpenCREBot\nDisallow: /bot-only\nCrawl-delay: 5\n"
        )
        self.assertFalse(r.allowed("http://h/a/x"))
        self.assertTrue(r.allowed("http://h/a/ok"))
        self.assertFalse(r.allowed("http://h/doc.pdf"))
        self.assertTrue(r.allowed("http://h/doc.pdf.html"))
        self.assertFalse(r.allowed("http://h/bot-only"))
        self.assertEqual(r.crawl_delay(), 5)

    def test_content_usage_lines(self):
        r = RobotsRules(
            "User-agent: *\nContent-Usage: train-ai=n\nContent-Usage: /ai-ok/ train-ai=y\n"
        )
        self.assertTrue(r.ai_forbidden("http://h/page"))
        self.assertFalse(r.ai_forbidden("http://h/ai-ok/page"))
        self.assertFalse(
            RobotsRules("User-agent: *\nDisallow:\n").ai_forbidden("http://h/")
        )

    def test_usage_parse(self):
        self.assertTrue(web_source.usage_forbids_ai("ai-use=n"))
        self.assertTrue(web_source.usage_forbids_ai("search=y, train-genai=?0"))
        self.assertFalse(web_source.usage_forbids_ai("train-ai=y"))
        self.assertFalse(web_source.usage_forbids_ai("search=n"))

    def test_x_robots_tag_scoping(self):
        self.assertIsNone(
            web_source.exclusion_reason({"X-Robots-Tag": "googlebot: noindex"})
        )
        self.assertEqual(
            web_source.exclusion_reason({"X-Robots-Tag": "opencrebot: noindex"}),
            "robots-meta:noindex",
        )


class ExternalSourcesJobTest(unittest.TestCase):
    NOW = datetime(2026, 10, 29, 9, 0)

    def spec(self, sid, **kw):
        kw.setdefault("status", external.STATUS_APPROVED)
        return external.ExternalSpec(
            id=sid, name=sid, start_urls=["https://x.org/"], **kw
        )

    def test_due_selection(self):
        last = {
            "never": None,
            "fresh": datetime(2026, 10, 20),
            "stale": datetime(2026, 9, 1),
        }
        specs = [
            self.spec("never"),
            self.spec("fresh"),
            self.spec("stale"),
            self.spec("suggested", status=external.STATUS_SUGGESTED),
            external.ExternalSpec(
                id="yt",
                name="yt",
                kind=external.KIND_YOUTUBE,
                channel_id="c",
                status=external.STATUS_APPROVED,
            ),
        ]
        with mock.patch.object(
            external_sources, "last_run", side_effect=lambda i: last.get(i)
        ):
            due = external_sources.due_specs(specs, self.NOW)
        self.assertEqual([s.id for s in due], ["never", "stale"])

    def test_refresh_days_is_per_spec(self):
        with mock.patch.object(
            external_sources, "last_run", return_value=datetime(2026, 10, 20)
        ):
            self.assertEqual(
                external_sources.due_specs([self.spec("s", refresh_days=7)], self.NOW)[
                    0
                ].id,
                "s",
            )
            self.assertEqual(
                external_sources.due_specs([self.spec("s", refresh_days=30)], self.NOW),
                [],
            )

    def test_job_registered_and_off_by_default(self):
        self.assertIn("external_sources", jobs.JOBS)
        self.assertIn("external_sources", jobs.JOB_ORDER)
        with mock.patch.object(
            schedule_settings.runtime_settings, "get_setting", return_value=None
        ):
            self.assertFalse(schedule_settings.job_enabled("external_sources"))
            self.assertTrue(schedule_settings.job_enabled("owasp"))
        with mock.patch.object(
            schedule_settings.runtime_settings, "get_setting", return_value="1"
        ):
            self.assertTrue(schedule_settings.job_enabled("external_sources"))

    def test_default_off_job_is_left_out_of_tick_and_health(self):
        from application.utils.oie_scheduler import health, runner

        with mock.patch.object(
            schedule_settings.runtime_settings, "get_setting", return_value=None
        ), mock.patch.object(runner, "run_job") as run_job, mock.patch.object(
            health, "job_health", return_value={"state": "ok"}
        ) as job_health, mock.patch.object(
            health, "queue_depths", return_value={}
        ):
            runner.run_due_jobs(mock.Mock(), cache_file="x")
            health.evaluate_health(mock.Mock())
        self.assertEqual(
            [c.args[1] for c in run_job.call_args_list], ["owasp", "cre_expansion"]
        )
        self.assertNotIn(
            "external_sources", [c.args[1] for c in job_health.call_args_list]
        )

    def test_stage_runs_due_sites_and_records_last_run(self):
        ctx = mock.Mock(now=self.NOW, dry_run=False)
        with mock.patch.object(
            external_sources.external,
            "load_specs",
            return_value=[self.spec("a-site"), self.spec("b-site")],
        ), mock.patch.object(
            external_sources, "last_run", return_value=None
        ), mock.patch(
            "application.prompt_client.prompt_client.PromptHandler"
        ), mock.patch(
            "application.utils.comprehension.external_ingest.ingest_spec",
            side_effect=[{"pages": 2, "chunks": 4, "written": 4}, RuntimeError("boom")],
        ), mock.patch.object(
            external_sources.runtime_settings, "set_setting"
        ) as put:
            result = jobs.stage_external_sources(ctx)
        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.summary["sites"]["a-site"]["written"], 4)
        self.assertIn("boom", result.summary["sites"]["b-site"]["error"])
        put.assert_called_once_with("OIE_EXT_LAST_RUN_A_SITE", "2026-10-29T09:00:00")

    def test_stage_skipped_when_nothing_due(self):
        ctx = mock.Mock(now=self.NOW, dry_run=False)
        with mock.patch.object(
            external_sources.external, "load_specs", return_value=[]
        ):
            self.assertEqual(jobs.stage_external_sources(ctx).status, "skipped")


if __name__ == "__main__":
    unittest.main()
