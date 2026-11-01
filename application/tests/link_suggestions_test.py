import unittest

from application.utils.comprehension import link_suggestions as ls

ROOT_README = """# OWASP Foo

[![Build](https://img.shields.io/badge/b.svg)](https://travis-ci.org/OWASP/foo)
Visit our [website](https://www.foo-project.org/about) or the
[GitHub org](https://github.com/OWASP/foo). Follow us on https://twitter.com/foo.
Chat: [slack](https://owasp.slack.com/x), short https://bit.ly/abc
Page: https://owasp.org/www-project-foo/ and <a href="https://conf.example.org/2025">Conference</a>.
Videos: [channel](https://www.youtube.com/@FooSec) and [talk](https://www.youtube.com/watch?v=abc123).
Playlist: https://www.youtube.com/playlist?list=PLxyz.
"""

FRONT = """---
title: Bar
homepage: https://bar-security.io/
---
Body text without links.
"""


class TestLinkSuggestions(unittest.TestCase):
    def test_extract_links_kinds_and_front_matter(self):
        links = ls.extract_links(FRONT + "[docs](https://docs.bar.io/)")
        self.assertEqual(links[0]["front_key"], "homepage")
        self.assertEqual(links[0]["url"], "https://bar-security.io/")
        self.assertIn(
            ("https://docs.bar.io/", "docs"),
            [(l["url"], l["link_text"]) for l in links],
        )

    def test_bare_urls_trim_punctuation_and_skip_markdown_dupes(self):
        links = ls.extract_links("see https://a.org/x. and [t](https://b.org/y)")
        urls = sorted(l["url"] for l in links)
        self.assertEqual(urls, ["https://a.org/x", "https://b.org/y"])

    def test_skip_list_and_owasp_pages_dropped(self):
        cands = ls.suggest_links({"OWASP/foo": [("README.md", 0, ROOT_README)]})
        hosts = {c["host"] for c in cands if c["kind"] == "site"}
        self.assertEqual(hosts, {"foo-project.org", "example.org"})

    def test_youtube_channels_only_not_watch_links(self):
        cands = ls.suggest_links({"OWASP/foo": [("README.md", 0, ROOT_README)]})
        yt = [c for c in cands if c["kind"] == "youtube"]
        self.assertEqual(
            sorted(c.get("channel_id") or c.get("playlist_id") for c in yt),
            ["@FooSec", "PLxyz"],
        )
        self.assertEqual(ls.candidate_id(yt[0])[:3], "yt-")

    def test_ranking_root_and_text_signals_beat_deep_body(self):
        chunks = {
            "OWASP/foo": [
                ("README.md", 0, "[website](https://good.org/)"),
                ("docs/a.md", 0, "see https://meh.net/page"),
            ]
        }
        cands = ls.suggest_links(chunks)
        self.assertEqual([c["host"] for c in cands], ["good.org", "meh.net"])
        self.assertGreater(cands[0]["score"], cands[1]["score"])

    def test_front_matter_beats_body(self):
        cands = ls.suggest_links(
            {
                "OWASP/bar": [("index.md", 0, FRONT)],
                "OWASP/z": [("a/b.md", 0, "https://q.org")],
            }
        )
        self.assertEqual(cands[0]["host"], "bar-security.io")

    def test_multiple_projects_raise_score_and_dedupe_by_registrable_host(self):
        chunks = {
            "OWASP/a": [("doc/x.md", 0, "https://docs.shared.org/a")],
            "OWASP/b": [("doc/x.md", 0, "https://www.shared.org/b")],
            "OWASP/c": [("doc/x.md", 0, "https://solo.org/")],
        }
        cands = ls.suggest_links(chunks)
        self.assertEqual(len(cands), 2)
        shared = cands[0]
        self.assertEqual(shared["host"], "shared.org")
        self.assertEqual(
            {f["repo"] for f in shared["found_in"]}, {"OWASP/a", "OWASP/b"}
        )
        self.assertGreater(shared["score"], cands[1]["score"])

    def test_registered_hosts_excluded(self):
        chunks = {"OWASP/a": [("README.md", 0, "[site](https://docs.known.org/)")]}
        self.assertEqual(ls.suggest_links(chunks, registered_hosts=["known.org"]), [])

    def test_name_guess_and_id(self):
        c = ls.suggest_links(
            {"o/a": [("README.md", 0, "[OWASP Benelux](https://owasp-benelux.eu/)")]}
        )[0]
        self.assertEqual(c["name_guess"], "OWASP Benelux")
        self.assertEqual(c["kind"], "site")
        self.assertEqual(ls.candidate_id(c), "owasp-benelux-eu")
        d = ls.suggest_links({"o/a": [("README.md", 0, "https://my-thing.org/")]})[0]
        self.assertEqual(d["name_guess"], "My Thing")

    def test_registrable_host(self):
        self.assertEqual(ls.registrable_host("a.b.foo.co.uk"), "foo.co.uk")
        self.assertEqual(ls.registrable_host("docs.foo.org"), "foo.org")

    def test_image_and_asset_urls_ignored(self):
        self.assertEqual(
            ls.suggest_links(
                {
                    "o/a": [
                        (
                            "README.md",
                            0,
                            "![x](https://cdn.foo.org/a.png) https://cdn.foo.org/b.png",
                        )
                    ]
                }
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
