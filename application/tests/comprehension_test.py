import json
import unittest

from application.utils.comprehension import digest, sources, store, synthesize
from application.utils.comprehension.answer import (
    answer_from_candidates,
    is_comprehension_hit,
)


def _row(repo, art, path, idx, text):
    return (
        repo,
        art,
        {"text": text, "span": {"index": idx}, "locator": {"path": path}},
    )


class SourcesTest(unittest.TestCase):
    def test_skips_translated_pages(self):
        body = "x" * 100
        docs = sources.docs_from_rows(
            [
                _row("O/S", "a1", "content/en/intro.md", 0, body),
                _row("O/S", "a2", "content/es/intro.md", 0, body),
                _row("O/S", "a3", "es/intro.md", 0, body),
            ]
        )
        self.assertEqual([d.path for d in docs], ["content/en/intro.md"])

    def test_people_profile_verifies_quotes_and_stores_doc_claims(self):
        doc = sources.SourceDoc(
            "O/e",
            "a",
            "e.md",
            "Jane Roe will speak on Threat Modeling at AppSec USA, Washington DC, 2026-11-05.",
        )
        raw = json.dumps(
            {
                "summary": "event",
                "claims": [
                    {
                        "statement": "Jane Roe speaks on Threat Modeling at AppSec USA, 2026-11-05",
                        "quote": "Jane Roe will speak on Threat Modeling at AppSec USA",
                    },
                    {"statement": "invented", "quote": "Bob keynote"},
                ],
            }
        )
        dd = digest.digest_doc(doc, lambda s, u: raw, system=digest.PEOPLE_SYSTEM)
        self.assertEqual((len(dd.claims), dd.dropped), (1, 1))
        d = digest.StandardDigest("O/e", "", [], [dd])
        slugs = [x[0] for x in store.documents(d)]
        self.assertTrue(any("-dclaim-" in x for x in slugs))

    def test_orders_chunks_and_drops_noise(self):
        body = "x" * 100
        docs = sources.docs_from_rows(
            [
                _row("O/S", "a1", "Model/intro.md", 1, "second " + body),
                _row("O/S", "a1", "Model/intro.md", 0, "first " + body),
                _row("O/S", "a2", "CODE_OF_CONDUCT.md", 0, body),
            ]
        )
        self.assertEqual([d.path for d in docs], ["Model/intro.md"])
        self.assertTrue(docs[0].text.startswith("first"))


class DigestTest(unittest.TestCase):
    def test_unsupported_quotes_are_dropped_and_sources_must_exist(self):
        doc = sources.SourceDoc(
            "O/S", "a", "p.md", "SAMM has three maturity levels per practice, always."
        )

        def bulk(system, user):
            return json.dumps(
                {
                    "summary": "s",
                    "claims": [
                        {
                            "statement": "three levels",
                            "quote": "three maturity levels per practice",
                        },
                        {
                            "statement": "invented",
                            "quote": "this sentence is not in the doc",
                        },
                    ],
                }
            )

        def overview(system, user):
            return json.dumps(
                {
                    "overview": "o",
                    "claims": [
                        {"statement": "ok", "sources": ["p.md"]},
                        {"statement": "bad", "sources": ["nope.md"]},
                    ],
                }
            )

        d = digest.digest_standard("O/S", [doc], bulk, overview, workers=1)
        self.assertEqual(len(d.docs[0].claims), 1)
        self.assertEqual(d.docs[0].dropped, 1)
        self.assertEqual([c.statement for c in d.claims], ["ok"])
        slugs = [s for s, _, _ in store.documents(d)]
        self.assertIn("comprehension-o-s-overview", slugs)


class SynthesizeTest(unittest.TestCase):
    def test_unknown_falls_through_and_citations_map(self):
        hits = [("a fact", ["https://x/a"]), ("b fact", ["https://x/b"])]
        self.assertEqual(
            synthesize.synthesize("q", hits, lambda s, u: "UNKNOWN"), ("", [])
        )
        ans, cites = synthesize.synthesize("q", hits, lambda s, u: "Three. [2]")
        self.assertEqual(cites, ["https://x/b"])

    def test_answer_hook_only_uses_comprehension_hits(self):
        class H:
            def __init__(self, url, content):
                self.url, self.content = url, content

        cands = [
            H("owasp-agent://meta/project/asvs", "Leaders: x"),
            H(
                "owasp-agent://evidence/comprehension-o-s-overview",
                "SAMM: 3 levels\n\nCitations: https://x/a",
            ),
        ]
        self.assertFalse(is_comprehension_hit(cands[0]))
        out = answer_from_candidates("q", cands, lambda m: "Three. [1]")
        self.assertEqual(out, ("Three. [1]", ["https://x/a"]))
        self.assertIsNone(answer_from_candidates("q", cands[:1], lambda m: "x"))


if __name__ == "__main__":
    unittest.main()


class RetrieveScopeTest(unittest.TestCase):
    def test_scopes_to_named_projects_only(self):
        from application.utils.comprehension.retrieve import matched_slugs

        sl = ["owasp-asvs", "owasp-www-project-top-ten", "owasp-api-security"]
        self.assertEqual(
            matched_slugs("How many leaders does ASVS list?", sl), ["owasp-asvs"]
        )
        self.assertEqual(matched_slugs("what is the weather", sl), [])
        self.assertEqual(
            set(matched_slugs("Compare Top Ten and API Security", sl)),
            {"owasp-www-project-top-ten", "owasp-api-security"},
        )
