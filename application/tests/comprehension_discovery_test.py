import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from application import create_app, sqla
from application.database import db
from application.utils.admin_panel import external_targets as et
from application.utils.comprehension import discovery, external
from application.utils.comprehension import link_suggestions as ls
from application.utils.comprehension import web_source
from application.utils.comprehension.web_source import Crawler, Page, CrawlResult
from application.utils.oie_scheduler import external_sources, jobs, schedule_settings
from application.tests.comprehension_web_source_test import (
    Site,
    html,
    ok,
    PARA,
)

NOW = datetime(2026, 10, 29, 9, 0)


def site_spec(**kw):
    return external.ExternalSpec(
        id="src",
        name="Src",
        status=external.STATUS_APPROVED,
        start_urls=["https://src.org/"],
        **kw,
    )


def result_with(*links):
    r = CrawlResult()
    r.external_links = list(links)
    return r


class CrawlCollectsLinksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def crawl(self, routes, site=None, **kw):
        s = site or Site(routes)
        if site is None:
            self.addCleanup(s.close)
        self.last_site = s
        spec = external.ExternalSpec(
            id="t", name="T", start_urls=[s.base + "/"], max_depth=2, **kw
        )
        return Crawler(spec, delay=0, cache_dir=Path(self.tmp.name)).crawl()

    def test_external_links_collected_deduped_and_filtered(self):
        links = [
            "/a",
            "https://2026.appsec.eu/program",
            "https://2026.appsec.eu/program#x",
            "mailto:a@b.org",
            "#top",
            "https://cdn.example.org/logo.png",
            "javascript:void(0)",
        ]
        result = self.crawl(
            {
                "/": ok(html("Home", links)),
                "/a": ok(html("A", ["https://2026.appsec.eu/program"])),
                "/robots.txt": (404, {}, ""),
            }
        )
        urls = [e[0] for e in result.external_links]
        self.assertEqual(urls, ["https://2026.appsec.eu/program"])
        url, text, page = result.external_links[0]
        self.assertEqual(text, "link")
        self.assertTrue(page.endswith("/"))

    def test_cap(self):
        many = [
            f"https://h{i}.example.org/"
            for i in range(web_source.MAX_EXTERNAL_LINKS + 20)
        ]
        result = self.crawl({"/": ok(html("Home", many)), "/robots.txt": (404, {}, "")})
        self.assertEqual(len(result.external_links), web_source.MAX_EXTERNAL_LINKS)

    def test_external_links_survive_a_304(self):
        routes = {
            "/": ok(html("Home", ["https://2026.appsec.eu/program"]), ETag='"h"'),
            "/robots.txt": (404, {}, ""),
        }
        first = self.crawl(routes)
        second = self.crawl(routes, site=self.last_site)
        self.assertEqual(second.not_modified, 1)
        self.assertEqual(second.external_links, first.external_links)


class StripNavTest(unittest.TestCase):
    def pages(self, n, menu="Register | Program | Conference | Sponsor"):
        return [
            Page(
                f"https://s.org/{i}",
                f"P{i}",
                f"{menu}\n\n# Page {i}\n\nUnique body number {i}.\n\nFooter: Donate",
                "2026-10-29",
                "",
                str(i),
            )
            for i in range(n)
        ]

    def test_repeated_lines_removed_content_kept(self):
        pages = self.pages(5)
        web_source.strip_nav(pages)
        for i, p in enumerate(pages):
            self.assertNotIn("Register", p.markdown)
            self.assertNotIn("Donate", p.markdown)
            self.assertIn(f"Unique body number {i}.", p.markdown)
        chunks = web_source.page_chunks(pages[0])
        self.assertTrue(chunks[0][2].startswith("Source: https://s.org/0"))

    def test_small_crawls_and_minority_lines_untouched(self):
        few = self.pages(3)
        web_source.strip_nav(few)
        self.assertIn("Register", few[0].markdown)
        pages = self.pages(5)
        for p in pages[:3]:
            p.markdown = p.markdown.replace("Register | Program", "Other menu")
        web_source.strip_nav(pages)  # 2/5 pages share the menu: below 60%
        self.assertIn("Register", pages[3].markdown)

    def test_crawl_strips_menus(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        menu = "<ul>" + "".join(f"<li>Menu{i}</li>" for i in range(4)) + "</ul>"

        def page(title, links=()):
            body = "".join(f"<p>{PARA}{title} {i}.</p>" for i in range(3))
            a = "".join(f'<a href="{h}">{h}</a>' for h in links)
            return ok(
                f"<html><head><title>{title}</title></head><body><article><h1>{title}</h1>"
                f"{body}<p>Menu line</p><p>Footer line</p>{a}</article></body></html>"
            )

        s = Site(
            {
                "/": page("Home", ["/a", "/b", "/c", "/d"]),
                "/a": page("A"),
                "/b": page("B"),
                "/c": page("C"),
                "/d": page("D"),
                "/robots.txt": (404, {}, ""),
            }
        )
        self.addCleanup(s.close)
        spec = external.ExternalSpec(id="t", name="T", start_urls=[s.base + "/"])
        result = Crawler(spec, delay=0, cache_dir=Path(tmp.name)).crawl()
        self.assertEqual(len(result.pages), 5)
        for p in result.pages:
            self.assertNotIn("Menu line", p.markdown)
            self.assertNotIn("Footer line", p.markdown)
            self.assertIn("OWASP chapters", p.markdown)


class RelevanceTest(unittest.TestCase):
    def test_keywords_and_year(self):
        s_prog, ev = discovery.score_link(
            "https://2026.appsec.eu/program", "Program", NOW
        )
        s_plain, _ = discovery.score_link("https://acme.io/blog", "our friends", NOW)
        self.assertTrue(ev)
        self.assertGreater(s_prog, discovery.MIN_SCORE)
        self.assertLess(s_plain, discovery.MIN_SCORE)

    def test_event_year_awareness(self):
        cur, _ = discovery.score_link("https://appsec.eu/2026/", "AppSec EU", NOW)
        last, _ = discovery.score_link("https://appsec.eu/2025/", "AppSec EU", NOW)
        stale, _ = discovery.score_link("https://appsec.eu/2019/", "AppSec EU", NOW)
        self.assertGreater(cur, last)
        self.assertGreater(last, stale)
        self.assertLess(stale, 0)
        self.assertEqual(
            discovery.event_years("https://x.org/2024/2026/p"), [2024, 2026]
        )

    def test_candidates_ranked_and_filtered(self):
        res = result_with(
            ("https://2026.appsec.eu/program", "Program", "https://src.org/e"),
            ("https://appsec.eu/schedule", "Schedule", "https://src.org/e2"),
            ("https://old-conf.org/2018/", "Conference 2018", "https://src.org/e"),
            ("https://bit.ly/abc", "Conference", "https://src.org/e"),
            ("https://cdn.cloudflare.com/x", "Conference", "https://src.org/e"),
            ("https://forms.gle/x", "Register", "https://src.org/e"),
            ("https://docs.src.org/conference", "Conference", "https://src.org/e"),
            ("https://rejected.org/conference", "Conference", "https://src.org/e"),
            ("https://boring.io/", "Blog", "https://src.org/e"),
            ("https://x.com/owasp", "Conference", "https://src.org/e"),
        )
        cands = discovery.candidates_from_crawl(
            site_spec(), res, registered_hosts=["rejected.org"], now=NOW
        )
        self.assertEqual([c["host"] for c in cands], ["appsec.eu"])
        c = cands[0]
        self.assertEqual(c["url"], "https://2026.appsec.eu/program")
        self.assertEqual(c["allow_prefixes"], ["https://2026.appsec.eu/"])
        self.assertEqual(
            (c["max_pages"], c["max_depth"], c["refresh_days"]), (30, 2, 7)
        )
        pages = {f["page"] for f in c["found_in"]}
        self.assertEqual(pages, {"https://src.org/e", "https://src.org/e2"})
        self.assertEqual(c["found_in"][0]["source"], "crawl")
        self.assertEqual(ls.candidate_id(c), "appsec-eu")

    def test_non_event_page_refreshes_monthly(self):
        res = result_with(
            ("https://handbook.io/chapter", "Chapter guide", "https://src.org/")
        )
        c = discovery.candidates_from_crawl(site_spec(), res, now=NOW)
        self.assertEqual(c[0]["refresh_days"], 7)  # keyword "chapter" => event-like
        res = result_with(("https://x-sec.io/", "Event", "https://src.org/"))
        res.external_links[0] = ("https://x-sec.io/news", "events", "https://src.org/")
        self.assertEqual(
            discovery.candidates_from_crawl(site_spec(), res, now=NOW)[0][
                "refresh_days"
            ],
            7,
        )


class ResolutionTest(unittest.TestCase):
    def cand(self):
        res = result_with(
            ("https://appsec.eu/", "AppSec EU conference", "https://src.org/e")
        )
        return discovery.candidates_from_crawl(site_spec(), res, now=NOW)[0]

    def test_apex_to_year_host_keeps_final_url_and_both_prefixes(self):
        c = discovery.apply_resolution(self.cand(), "https://2026.appsec.eu/en/", "")
        self.assertEqual(c["url"], "https://2026.appsec.eu/en/")
        self.assertEqual(
            c["allow_prefixes"], ["https://2026.appsec.eu/", "https://appsec.eu/"]
        )
        self.assertIn("appsec.eu", c["notes"])

    def test_failed_resolution_keeps_original_with_note(self):
        c = discovery.apply_resolution(
            self.cand(), "https://appsec.eu/", "not resolved: HTTP 404"
        )
        self.assertEqual(c["url"], "https://appsec.eu/")
        self.assertIn("not resolved", c["notes"])

    def test_resolution_cap(self):
        cands = [
            {"kind": "site", "url": f"https://h{i}.org/", "host": f"h{i}.org"}
            for i in range(5)
        ]
        calls = []

        def resolver(url):
            calls.append(url)
            return url, ""

        out, done = discovery.resolve_candidates(cands, resolver, max_resolve=2)
        self.assertEqual((len(calls), done, len(out)), (2, 2, 5))

    def test_http_resolver_follows_redirect_politely(self):
        site = Site(
            {
                "/": (301, {"Location": "/2026/"}, ""),
                "/2026/": ok("<html>hi</html>"),
                "/robots.txt": (
                    200,
                    {"Content-Type": "text/plain"},
                    "User-agent: *\nDisallow: /nope\n",
                ),
                "/nope": (301, {"Location": "/2026/"}, ""),
            }
        )
        self.addCleanup(site.close)
        sleeps = []
        resolve = discovery.http_resolver(sleep=sleeps.append)
        final, note = resolve(site.base + "/")
        self.assertEqual((final, note), (site.base + "/2026/", ""))
        self.assertTrue(all(s == discovery.RESOLVE_DELAY for s in sleeps) and sleeps)
        self.assertEqual(
            resolve(site.base + "/nope"),
            (site.base + "/nope", "not resolved: robots.txt"),
        )


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        os.environ["INSECURE_REQUESTS"] = "True"

    def tearDown(self):
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def links(self, *urls):
        return result_with(*[(u, "Conference", "https://src.org/e") for u in urls])

    def test_crawl_suggestions_stored_disabled_with_provenance_and_resolved(self):
        resolver = lambda url: ("https://2026.appsec.eu/en/", "")
        out = discovery.suggest_from_crawl(
            site_spec(),
            self.links("https://appsec.eu/"),
            sqla.session,
            resolver=resolver,
            now=NOW,
        )
        self.assertEqual(out["created"], ["appsec-eu"])
        row = sqla.session.query(db.IngestionTarget).get("appsec-eu")
        self.assertFalse(row.enabled)
        spec = external.spec_from_target(row)
        self.assertEqual(spec.status, external.STATUS_SUGGESTED)
        self.assertEqual(spec.start_urls, ["https://2026.appsec.eu/en/"])
        self.assertEqual(
            spec.allow_prefixes, ["https://2026.appsec.eu/", "https://appsec.eu/"]
        )
        self.assertEqual(spec.found_in[0]["page"], "https://src.org/e")
        self.assertEqual(external.load_specs(sqla.session), [])

    def test_rejected_and_registered_hosts_never_resuggested(self):
        et.add_manual({"id": "reg", "name": "Reg", "start_urls": ["https://reg.org/"]})
        et.upsert_suggestions(
            [{"kind": "site", "host": "rej.org", "url": "https://rej.org/", "score": 3}]
        )
        et.reject("rej-org")
        out = discovery.suggest_from_crawl(
            site_spec(),
            self.links("https://reg.org/conference", "https://rej.org/conference"),
            sqla.session,
            resolver=lambda u: (u, ""),
            now=NOW,
        )
        self.assertEqual(out["candidates"], 0)
        self.assertEqual(out["created"], [])

    def test_resolution_into_a_registered_host_is_dropped(self):
        et.add_manual({"id": "reg", "name": "Reg", "start_urls": ["https://reg.org/"]})
        out = discovery.suggest_from_crawl(
            site_spec(),
            self.links("https://short-conf.org/"),
            sqla.session,
            resolver=lambda u: ("https://reg.org/x", ""),
            now=NOW,
        )
        self.assertEqual(out["created"], [])

    def test_new_suggestion_cap_but_known_ones_still_merge(self):
        urls = [f"https://conf{i}.org/2026/" for i in range(5)]
        first = discovery.suggest_from_crawl(
            site_spec(),
            self.links(*urls[:1]),
            sqla.session,
            resolver=lambda u: (u, ""),
            now=NOW,
        )
        self.assertEqual(len(first["created"]), 1)
        cands = discovery.candidates_from_crawl(site_spec(), self.links(*urls), now=NOW)
        out = discovery.store_candidates(
            sqla.session, cands, limit=2, resolver=lambda u: (u, "")
        )
        self.assertEqual(len(out["created"]), 2)
        self.assertEqual(out["merged"], ["conf0-org"])

    def test_suggest_from_repos_caps_dry_run_and_marks_github(self):
        for i in range(3):
            sqla.session.add(
                db.HarvestInput(
                    pipeline_run_id="r",
                    artifact_id=f"a{i}",
                    source_repo=f"OWASP/p{i}",
                    payload={},
                )
            )
        sqla.session.commit()
        chunks = lambda s, repo: [
            ("README.md", 0, f"[Site](https://{repo[-2:]}-conf.org/)")
        ]
        with mock.patch(
            "application.utils.comprehension.sources.chunks_for_repo",
            side_effect=chunks,
        ):
            dry = discovery.suggest_from_repos(sqla.session, 2, apply=False)
            self.assertEqual((dry["candidates"], dry["created"]), (3, []))
            self.assertEqual(sqla.session.query(db.IngestionTarget).count(), 0)
            res = discovery.suggest_from_repos(
                sqla.session, 2, resolver=lambda u: (u, ""), max_resolve=1
            )
        self.assertEqual(len(res["created"]), 2)
        self.assertEqual(res["resolved"], 1)
        row = sqla.session.query(db.IngestionTarget).get(res["created"][0])
        self.assertEqual(external.spec_from_target(row).found_in[0]["source"], "github")

    def test_approved_discovery_joins_the_schedule(self):
        discovery.suggest_from_crawl(
            site_spec(),
            self.links("https://appsec.eu/2026/"),
            sqla.session,
            resolver=lambda u: (u, ""),
            now=NOW,
        )
        specs = external.load_specs(sqla.session, kinds=(external.KIND_SITE,))
        self.assertEqual(external_sources.due_specs(specs, NOW), [])
        et.accept("appsec-eu")
        specs = external.load_specs(sqla.session, kinds=(external.KIND_SITE,))
        with mock.patch.object(external_sources, "last_run", return_value=None):
            due = external_sources.due_specs(specs, NOW)
        self.assertEqual([s.id for s in due], ["appsec-eu"])
        self.assertEqual(due[0].refresh_days, 7)


class WiringTest(unittest.TestCase):
    def test_job_registered_and_default_on(self):
        self.assertIn("external_discovery", jobs.JOBS)
        self.assertIn("external_discovery", jobs.JOB_ORDER)
        with mock.patch.object(
            schedule_settings.runtime_settings, "get_setting", return_value=None
        ):
            self.assertTrue(schedule_settings.job_enabled("external_discovery"))

    def test_stage_runs_suggest_from_repos_and_honours_dry_run(self):
        ctx = mock.Mock(dry_run=True)
        with mock.patch.object(
            discovery,
            "suggest_from_repos",
            return_value={
                "repos": 2,
                "candidates": 3,
                "created": [],
                "merged": [],
                "resolved": 0,
            },
        ) as call:
            result = jobs.stage_external_discovery(ctx)
        self.assertEqual(result.status, "ok")
        self.assertFalse(call.call_args.kwargs["apply"])

    def test_ingest_spec_queues_crawl_suggestions_only_when_applying(self):
        from application.utils.comprehension import external_ingest

        result = CrawlResult()
        result.external_links = [
            ("https://a.org/conference", "Conference", "https://src.org/")
        ]
        with mock.patch.object(
            web_source, "crawl_chunks", return_value=([], result)
        ), mock.patch.object(discovery, "suggest_from_crawl") as sug:
            sug.return_value = {"created": ["a-org"], "merged": []}
            external_ingest.ingest_spec(site_spec(), apply=False, database=mock.Mock())
            sug.assert_not_called()
            counts = external_ingest.ingest_spec(
                site_spec(), apply=True, database=mock.Mock(), embed=None
            )
        sug.assert_called_once()
        self.assertEqual(counts["suggested"], 1)


if __name__ == "__main__":
    unittest.main()
