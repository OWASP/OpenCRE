import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from application.tests.comprehension_web_source_test import (
    Site,
    html,
    ok,
    spec_for,
)
from application.utils.comprehension import web_source
from application.utils.comprehension.web_source import Crawler

SHELL = (
    "<html><head><title>App</title><script src='/app.js'></script></head>"
    "<body><div id='root'></div></body></html>"
)
ROBOTS = (
    "/robots.txt",
    lambda site: ok("User-agent: *\n", **{"Content-Type": "text/plain"}),
)


class JsFallbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def crawl(self, routes, renderer=None, js="1"):
        site = Site(dict(routes, **dict([ROBOTS])))
        self.addCleanup(site.close)
        env = {"OWASP_CRAWL_JS": js}
        with mock.patch.dict(os.environ, env):
            crawler = Crawler(
                spec_for(site, max_depth=1),
                delay=0,
                cache_dir=Path(self.tmp.name),
                renderer=renderer,
            )
            return crawler.crawl(), site

    def test_js_is_on_by_default_and_can_be_switched_off(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OWASP_CRAWL_JS", None)
            self.assertTrue(web_source.js_enabled())
        with mock.patch.dict(os.environ, {"OWASP_CRAWL_JS": "0"}):
            self.assertFalse(web_source.js_enabled())

    def test_shell_page_is_skipped_and_renderer_untouched_when_off(self):
        renderer = mock.Mock()
        result, _ = self.crawl({"/": ok(SHELL)}, renderer, js="0")
        self.assertEqual(result.pages, [])
        self.assertIn(("{}/".format(_base(result)), "too-short"), _skips(result))
        renderer.assert_not_called()

    def test_shell_page_is_rendered_when_on(self):
        renderer = mock.Mock(return_value=html("Rendered Home", ["/next"], paras=3))
        routes = {"/": ok(SHELL), "/next": ok(html("Next"))}
        result, _ = self.crawl(routes, renderer)
        renderer.assert_called_once()
        titles = sorted(p.title for p in result.pages)
        self.assertEqual(titles, ["Next", "Rendered Home"])

    def test_normal_pages_never_go_through_the_browser(self):
        renderer = mock.Mock()
        result, _ = self.crawl({"/": ok(html("Static"))}, renderer)
        self.assertEqual(len(result.pages), 1)
        renderer.assert_not_called()

    def test_renderer_failure_is_a_skip_not_a_crash(self):
        renderer = mock.Mock(side_effect=RuntimeError("boom"))
        result, _ = self.crawl({"/": ok(SHELL)}, renderer)
        self.assertEqual(result.pages, [])
        self.assertTrue(any(r == "js-error:RuntimeError" for _, r in result.skipped))

    def test_rendered_html_still_honours_robots_meta(self):
        rendered = html("Hidden", head='<meta name="robots" content="noai">')
        result, _ = self.crawl({"/": ok(SHELL)}, mock.Mock(return_value=rendered))
        self.assertEqual(result.pages, [])
        self.assertTrue(any("noai" in r for _, r in result.skipped))


class PdfTimeCapTest(unittest.TestCase):
    def test_default_and_env_cap(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OWASP_CRAWL_PDF_SECONDS", None)
            self.assertEqual(web_source.pdf_seconds(), 60.0)
        with mock.patch.dict(os.environ, {"OWASP_CRAWL_PDF_SECONDS": "7"}):
            self.assertEqual(web_source.pdf_seconds(), 7.0)
        with mock.patch.dict(os.environ, {"OWASP_CRAWL_PDF_SECONDS": "x"}):
            self.assertEqual(web_source.pdf_seconds(), 60.0)

    def crawl_pdf(self, local, llm, extra_env=None):
        site = Site(
            {
                "/": ok(html("Home", ["/doc.pdf"])),
                "/doc.pdf": (200, {"Content-Type": "application/pdf"}, b"%PDF-1.4"),
                ROBOTS[0]: ROBOTS[1],
            }
        )
        self.addCleanup(site.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = {"OWASP_CRAWL_PDF": "1", "OWASP_CRAWL_PDF_SECONDS": "0.2"}
        env.update(extra_env or {})
        with mock.patch.dict(os.environ, env), mock.patch.object(
            web_source, "_pdf_to_markdown", local
        ), mock.patch.object(web_source, "_pdf_via_llm", llm):
            return Crawler(
                spec_for(site, max_depth=1), delay=0, cache_dir=Path(tmp.name)
            ).crawl()

    def slow_local(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def slow(_data):
            release.wait(5)
            return "late"

        return slow

    def test_slow_pdf_with_no_fallback_is_skipped_as_timeout(self):
        llm = mock.Mock()
        result = self.crawl_pdf(self.slow_local(), llm, {"OWASP_CRAWL_PDF_LLM": "0"})
        self.assertEqual([p.title for p in result.pages], ["Home"])
        self.assertTrue(any(r == "pdf-timeout" for _, r in result.skipped))
        llm.assert_not_called()

    def test_slow_pdf_falls_back_to_the_llm(self):
        text = "# Programme\n\n" + PARA_LONG
        result = self.crawl_pdf(self.slow_local(), mock.Mock(return_value=text))
        self.assertEqual(len(result.pages), 2)
        self.assertIn("Programme", result.pages[1].markdown)

    def test_docling_error_falls_back_to_the_llm(self):
        def broken(_data):
            raise ValueError("bad pdf")

        text = "# Doc\n\n" + PARA_LONG
        result = self.crawl_pdf(broken, mock.Mock(return_value=text))
        self.assertEqual(len(result.pages), 2)

    def test_both_routes_failing_keeps_the_original_reason(self):
        llm = mock.Mock(side_effect=RuntimeError("no key"))
        result = self.crawl_pdf(self.slow_local(), llm)
        self.assertTrue(any(r == "pdf-timeout" for _, r in result.skipped))
        self.assertEqual([p.title for p in result.pages], ["Home"])


PARA_LONG = (
    "The programme lists keynotes, training days and the venue for the chapter conference. "
    * 4
)


def _skips(result):
    return list(result.skipped)


def _base(result):
    return result.skipped[0][0].rsplit("/", 1)[0]
