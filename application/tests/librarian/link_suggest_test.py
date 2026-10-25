"""Tests for ``POST /rest/v1/link/suggest`` and the service behind it (#275).

Hermetic: the retriever is a stub returning a fixed ``RetrievalAudit``, so no
embedding call is made. The web tests go through the real Flask route with the
builder seam patched, which is the only way to prove the route's validation,
auth bypass and error mapping without a model or a key.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import os
import unittest
from unittest import mock

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils.librarian import link_suggest
from application.utils.librarian.link_suggest import (
    DEFAULT_TOP_K,
    MAX_TOP_K,
    InvalidStandardError,
    clamp_top_k,
    standard_query_text,
    suggest_links,
)
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit


def _audit() -> RetrievalAudit:
    return RetrievalAudit(
        retriever="stub/1.0.0",
        candidates=[
            CreCandidate(
                cre_id="287-251", cre_name="from retriever", score_vector=0.91234
            ),
            CreCandidate(cre_id="000-001", score_vector=0.5),
        ],
        reranked=[],
        threshold=0.8,
    )


class _StubRetriever:
    def __init__(self) -> None:
        self.calls = []

    def retrieve(self, text: str) -> RetrievalAudit:
        self.calls.append(text)
        return _audit()


def _standard(**overrides):
    doc = {
        "doctype": "Standard",
        "name": "ASVS",
        "sectionID": "V2.9.2",
        "section": (
            "Verify that the challenge nonce is at least 64 bits in length, and "
            "statistically unique or unique over the lifetime of the cryptographic device."
        ),
        "hyperlink": "https://github.com/OWASP/ASVS/blob/v4.0.2/4.0/en/0x11-V2-Authentication.md",
        "links": [],
    }
    doc.update(overrides)
    return doc


class StandardQueryTextTest(unittest.TestCase):
    def test_joins_the_text_fields_and_ignores_provenance(self) -> None:
        text = standard_query_text(
            _standard(subsection="Nonce size", description="Use 64-bit nonces")
        )
        self.assertTrue(text.startswith("Verify that the challenge nonce"))
        self.assertIn("Nonce size. Use 64-bit nonces", text)
        self.assertNotIn("ASVS", text)
        self.assertNotIn("V2.9.2", text)

    def test_rejects_non_standard_doctype(self) -> None:
        with self.assertRaises(InvalidStandardError):
            standard_query_text(_standard(doctype="CRE"))

    def test_rejects_missing_name(self) -> None:
        with self.assertRaises(InvalidStandardError):
            standard_query_text(_standard(name=""))

    def test_rejects_a_document_with_no_text_to_embed(self) -> None:
        with self.assertRaises(InvalidStandardError):
            standard_query_text(_standard(section="", subsection="", description=""))

    def test_rejects_non_string_text_fields(self) -> None:
        with self.assertRaises(InvalidStandardError):
            standard_query_text(_standard(section=["not", "a", "string"]))

    def test_rejects_non_object_bodies(self) -> None:
        with self.assertRaises(InvalidStandardError):
            standard_query_text(["a", "list"])  # type: ignore[arg-type]


class ClampTopKTest(unittest.TestCase):
    def test_absent_means_default(self) -> None:
        self.assertEqual(clamp_top_k(None), DEFAULT_TOP_K)
        self.assertEqual(clamp_top_k(""), DEFAULT_TOP_K)

    def test_parses_and_caps(self) -> None:
        self.assertEqual(clamp_top_k("7"), 7)
        self.assertEqual(clamp_top_k(99), MAX_TOP_K)

    def test_rejects_non_positive_and_non_integer(self) -> None:
        for bad in ("0", "-3", "x", 2.5, "--3", "\u00b2", "2_0", " 7 x", True):
            with self.assertRaises(InvalidStandardError):
                clamp_top_k(bad)


class SuggestLinksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.collection = db.Node_collection()
        self.added = self.collection.add_cre(
            defs.CRE(
                id="287-251",
                name="Use a unique challenge nonce of sufficient size",
                tags=["Cryptography"],
            )
        )

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_a_failing_cre_lookup_is_logged_with_the_candidate(self) -> None:
        """A lookup that raises is not a miss: it is logged, named, and the
        candidate still comes back unresolved so the shortlist survives."""
        broken = mock.Mock()
        broken.get_CREs.side_effect = RuntimeError("database gone")
        with self.assertLogs(link_suggest.logger, level="WARNING") as logs:
            self.assertIsNone(link_suggest._resolve_cre(broken, "287-251"))
        self.assertIn("287-251", logs.output[0])
        self.assertIn("database gone", logs.output[0])

    def test_internal_uuid_candidates_resolve_to_the_public_cre_id(self) -> None:
        """The embeddings table keys vectors by the CRE row's internal UUID, so
        that is what the retriever returns. A caller must only ever see
        "287-251"; this is the bug a stub keyed by external ids would hide."""
        internal_id = self.added.id

        class _UuidRetriever:
            def retrieve(self, text):
                return RetrievalAudit(
                    retriever="stub/1.0.0",
                    candidates=[CreCandidate(cre_id=internal_id, score_vector=0.9)],
                    reranked=[],
                    threshold=0.8,
                )

        (result,) = suggest_links(
            self.collection, _standard(), retriever=_UuidRetriever()
        )

        self.assertEqual(result["id"], "287-251")
        self.assertEqual(
            result["name"], "Use a unique challenge nonce of sufficient size"
        )
        self.assertEqual(result["tags"], ["Cryptography"])

    def test_returns_the_issue_275_shape_best_first(self) -> None:
        results = suggest_links(
            self.collection, _standard(), retriever=_StubRetriever()
        )

        self.assertEqual(
            results[0],
            {
                "doctype": "CRE",
                "id": "287-251",
                "name": "Use a unique challenge nonce of sufficient size",
                "tags": ["Cryptography"],
                "score": 0.9123,
            },
        )

    def test_a_candidate_missing_from_the_graph_is_returned_not_dropped(self) -> None:
        """A stale embedding for a CRE the graph no longer has is still a
        result the caller should see; silently dropping it would hide the
        drift that caused it."""
        results = suggest_links(
            self.collection, _standard(), retriever=_StubRetriever()
        )

        self.assertEqual(results[1]["id"], "000-001")
        self.assertEqual(results[1]["name"], "")
        self.assertEqual(results[1]["tags"], [])

    def test_graph_name_wins_over_the_retrievers_label(self) -> None:
        results = suggest_links(
            self.collection, _standard(), retriever=_StubRetriever()
        )
        self.assertNotEqual(results[0]["name"], "from retriever")

    def test_top_k_slices_the_shortlist(self) -> None:
        results = suggest_links(
            self.collection, _standard(), top_k=1, retriever=_StubRetriever()
        )
        self.assertEqual(len(results), 1)

    def test_top_k_outside_bounds_is_refused(self) -> None:
        for bad in (0, MAX_TOP_K + 1):
            with self.assertRaises(InvalidStandardError):
                suggest_links(
                    self.collection, _standard(), top_k=bad, retriever=_StubRetriever()
                )

    def test_embeds_the_section_text_not_the_whole_document(self) -> None:
        stub = _StubRetriever()
        suggest_links(self.collection, _standard(), retriever=stub)
        self.assertEqual(len(stub.calls), 1)
        self.assertTrue(stub.calls[0].startswith("Verify that the challenge nonce"))

    def test_a_supplied_retriever_means_no_builder_is_invoked(self) -> None:
        def _must_not_run(database):
            raise AssertionError("builder must not be called")

        suggest_links(
            self.collection,
            _standard(),
            retriever=_StubRetriever(),
            retriever_factory=_must_not_run,
        )

    def test_invalid_document_fails_before_any_retrieval(self) -> None:
        stub = _StubRetriever()
        with self.assertRaises(InvalidStandardError):
            suggest_links(self.collection, _standard(section=""), retriever=stub)
        self.assertEqual(stub.calls, [])


class LinkSuggestRouteTest(unittest.TestCase):
    """The real Flask route, with only the retriever builder seam patched."""

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        os.environ["INSECURE_REQUESTS"] = "True"
        os.environ["NO_LOGIN"] = "1"
        self.collection = db.Node_collection()
        self.collection.add_cre(
            defs.CRE(
                id="287-251", name="Use a unique challenge nonce", tags=["Cryptography"]
            )
        )

    def tearDown(self) -> None:
        os.environ.pop("NO_LOGIN", None)
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _post(self, body, query=""):
        with mock.patch.object(
            link_suggest, "_default_retriever", return_value=_StubRetriever()
        ):
            with self.app.test_client() as c:
                return c.post(f"/rest/v1/link/suggest{query}", json=body)

    def test_returns_ranked_cres(self) -> None:
        resp = self._post(_standard())
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        body = resp.get_json()
        self.assertEqual([r["id"] for r in body], ["287-251", "000-001"])
        self.assertEqual(body[0]["doctype"], "CRE")
        self.assertEqual(body[0]["tags"], ["Cryptography"])

    def test_top_k_from_the_query_string(self) -> None:
        resp = self._post(_standard(), query="?top_k=1")
        self.assertEqual(len(resp.get_json()), 1)

    def test_non_object_body_is_400(self) -> None:
        resp = self._post(["not", "an", "object"])
        self.assertEqual(resp.status_code, 400)

    def test_document_without_text_is_400_with_the_reason(self) -> None:
        resp = self._post(_standard(section=""))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("section", resp.get_data(as_text=True))

    def test_bad_top_k_is_400(self) -> None:
        resp = self._post(_standard(), query="?top_k=zero")
        self.assertEqual(resp.status_code, 400)

    def test_missing_ml_dependencies_is_503(self) -> None:
        with mock.patch.object(
            link_suggest, "_default_retriever", side_effect=ImportError("no torch")
        ):
            with self.app.test_client() as c:
                resp = c.post("/rest/v1/link/suggest", json=_standard())
        self.assertEqual(resp.status_code, 503)

    def test_missing_litellm_is_503(self) -> None:
        with mock.patch.object(
            link_suggest,
            "_default_retriever",
            side_effect=RuntimeError("litellm is not installed"),
        ):
            with self.app.test_client() as c:
                resp = c.post("/rest/v1/link/suggest", json=_standard())
        self.assertEqual(resp.status_code, 503)

    def test_other_runtime_errors_get_the_generic_body_not_flasks_500_page(
        self,
    ) -> None:
        """Only a missing litellm is a 503; any other RuntimeError must go
        through the same generic handling as every other failure."""
        with mock.patch.object(
            link_suggest,
            "_default_retriever",
            side_effect=RuntimeError("index file /srv/cre/secret.idx is corrupt"),
        ):
            with self.app.test_client() as c:
                resp = c.post("/rest/v1/link/suggest", json=_standard())
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(
            resp.get_json(),
            {"error": "Link suggestion failed upstream; see server logs."},
        )
        self.assertNotIn("secret.idx", resp.get_data(as_text=True))

    def test_malformed_top_k_strings_are_400_not_500(self) -> None:
        for bad in ("--3", "\u00b2", "2_0"):
            resp = self._post(_standard(), query=f"?top_k={bad}")
            self.assertEqual(resp.status_code, 400, bad)

    def test_provider_failure_is_reported_not_swallowed(self) -> None:
        class _Boom(Exception):
            status_code = 502

        with mock.patch.object(
            link_suggest, "_default_retriever", side_effect=_Boom("upstream down")
        ):
            with self.app.test_client() as c:
                resp = c.post("/rest/v1/link/suggest", json=_standard())
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())
        # the client gets a status and a generic message, never the raw text
        self.assertNotIn("upstream down", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
