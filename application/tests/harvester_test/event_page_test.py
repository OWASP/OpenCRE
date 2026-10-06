"""Jekyll event pages: front matter + JSON-LD become clean prose; templating is dropped."""

import unittest
from pathlib import Path

from unittest.mock import patch

from application.prompt_client import prompt_client
from application.utils.harvester.event_page import (
    clean_embedding_text,
    prepare_event_page,
)

FIXTURE = Path(__file__).parent / "fixtures" / "event_index.md.txt"


class PrepareEventPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = FIXTURE.read_text(encoding="utf-8")
        self.out = prepare_event_page(self.text)

    def test_title_comes_from_the_event_name(self) -> None:
        self.assertTrue(
            self.out.startswith("# AppSec Days - Summer of Security 2020\n"), self.out
        )

    def test_event_facts_are_stated_as_prose(self) -> None:
        self.assertIn("Dates: 2020-06-23 to 2020-08-26", self.out)
        self.assertIn("Location: https://appsecdays.org/", self.out)
        self.assertIn("virtual AppSec Days", self.out)

    def test_markup_noise_is_removed(self) -> None:
        for noise in (
            "schema.org",
            "@context",
            "application/ld+json",
            "layout: event",
            "{%",
            "{{",
            "<!--",
            "<ul>",
            "OnlineEventAttendanceMode",
        ):
            self.assertNotIn(noise, self.out)

    def test_markdown_body_is_kept(self) -> None:
        self.assertIn("### Training Sessions Include", self.out)
        self.assertIn("threat modeling with the OWASP Top 10", self.out)
        self.assertIn("https://appsecdays.org/sponsors/swag/", self.out)

    def test_falls_back_to_front_matter_title_without_json_ld(self) -> None:
        out = prepare_event_page(
            "---\ntitle: Local Meetup\nlayout: event\n---\n\nCome and learn about XSS.\n"
        )
        self.assertTrue(out.startswith("# Local Meetup\n"), out)
        self.assertIn("Come and learn about XSS.", out)
        self.assertNotIn("layout", out)

    def test_malformed_json_ld_is_dropped_not_fatal(self) -> None:
        out = prepare_event_page(
            '---\ntitle: T\n---\n<script type="application/ld+json">{not json</script>\nBody text here.\n'
        )
        self.assertIn("Body text here.", out)
        self.assertNotIn("not json", out)

    def test_raw_newlines_inside_json_strings_are_tolerated(self) -> None:
        out = prepare_event_page(
            '<script type="application/ld+json">{"@type": "Event", "name": "N",\n'
            ' "description": "line one\n        line two", "startDate": "2020-01-01"}'
            "</script>\nBody.\n"
        )
        self.assertIn("# N", out)
        self.assertIn("line one line two", out)

    def test_json_ld_graph_and_list_forms(self) -> None:
        out = prepare_event_page(
            '<script type="application/ld+json">'
            '{"@graph": [{"@type": "Organization", "name": "Org"},'
            '{"@type": "Event", "name": "Graph Event", "startDate": "2025-01-02",'
            ' "location": {"@type": "Place", "name": "Lisbon", "address": "Rua 1"}}]}'
            "</script>\nBody.\n"
        )
        self.assertIn("# Graph Event", out)
        self.assertIn("Dates: 2025-01-02", out)
        self.assertIn("Location: Lisbon", out)

    def test_page_with_no_content_is_blank(self) -> None:
        self.assertEqual(
            prepare_event_page("---\nlayout: event\n---\n{% include x.md %}\n"), ""
        )

    def test_plain_markdown_passes_through(self) -> None:
        self.assertEqual(
            prepare_event_page("# Hello\n\nWorld.\n").strip(), "# Hello\n\nWorld."
        )


class AdversarialInputTests(unittest.TestCase):
    """Page content is untrusted repo text; unclosed constructs must not blow up."""

    def test_unterminated_markup_is_linear_enough(self) -> None:
        import time

        for text in (
            "{% if x %} text\n" * 20000,
            '<script type="application/ld+json">' * 5000,
            "{% if a %}" * 5000 + "{% endif %}" * 5000,
            "{{ " * 50000,
            "<!-- " * 50000,
            "{% " * 50000,
            "<script " * 50000,
        ):
            started = time.monotonic()
            prepare_event_page(text)
            self.assertLess(time.monotonic() - started, 5.0, text[:20])

    def test_unterminated_block_keeps_the_prose_around_it(self) -> None:
        out = prepare_event_page("Before.\n{% if x %}\nAfter.\n")
        self.assertIn("Before.", out)
        self.assertIn("After.", out)

    def test_nested_blocks_are_removed_whole(self) -> None:
        out = prepare_event_page(
            "Keep.\n{% if a %}\n{% for b in c %}x{% endfor %}\ngone\n{% endif %}\nKeep too.\n"
        )
        self.assertNotIn("gone", out)
        self.assertIn("Keep too.", out)


RAW = (
    "https://raw.githubusercontent.com/OWASP/www-event-2020-07-virtual/master/index.md"
)


class CleanEmbeddingTextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = FIXTURE.read_text(encoding="utf-8")

    def test_event_repo_pages_are_cleaned(self) -> None:
        out = clean_embedding_text(RAW, self.text)
        self.assertIn("Dates: 2020-06-23 to 2020-08-26", out)
        self.assertNotIn("ld+json", out)

    def test_github_blob_and_raw_forms_of_event_repos_match(self) -> None:
        for url in (
            "https://github.com/OWASP/www-event-2024-global-appsec-lisbon/raw/main/index.md",
            "https://raw.githubusercontent.com/OWASP/www-event-2024-global-appsec-lisbon/main/index.md",
        ):
            self.assertNotIn("ld+json", clean_embedding_text(url, self.text))

    def test_other_repos_and_non_markdown_are_untouched(self) -> None:
        for url in (
            "https://raw.githubusercontent.com/OWASP/ASVS/master/README.md",
            "https://raw.githubusercontent.com/someone/www-event-x/main/index.md",
            "https://raw.githubusercontent.com/OWASP/www-event-x/main/data.json",
            "https://example.com/OWASP/www-event-x/main/index.md",
        ):
            self.assertEqual(clean_embedding_text(url, self.text), self.text, url)

    def test_empty_cleaned_text_falls_back_to_the_original(self) -> None:
        text = "---\nlayout: event\n---\n{% include x.md %}\n"
        self.assertEqual(clean_embedding_text(RAW, text), text)

    def test_get_content_cleans_event_pages(self) -> None:
        emb = prompt_client.in_memory_embeddings.__new__(
            prompt_client.in_memory_embeddings
        )
        with patch.object(
            prompt_client, "_fetch_plain_http_text", return_value=self.text
        ):
            out = emb.get_content(RAW)
        self.assertIn("Dates: 2020-06-23", out)
        self.assertNotIn("schema.org", out)


if __name__ == "__main__":
    unittest.main()
