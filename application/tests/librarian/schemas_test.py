"""Tests for Module C contracts.

The point of these tests is to enforce the RFC #734 contract — every Pydantic
model in ``schemas.py`` is dumped to JSON and validated against the **vendored
canonical JSON Schema** under ``application/utils/librarian/_rfc_schemas/``.
If the upstream schema and the Pydantic model ever drift, this fails.
"""

import json
import os
import unittest

import jsonschema
from pydantic import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from application.utils.librarian.schemas import (
    SCHEMA_VERSION,
    CreCandidate,
    Filter,
    FilterStage,
    GoldenDatasetRow,
    KnowledgeContent,
    KnowledgeItem,
    KnowledgeQueueItem,
    KnowledgeSnapshot,
    KnowledgeStatus,
    LinkProposal,
    Locator,
    LocatorKind,
    ProposedLink,
    Rejection,
    RetrievalAudit,
    ReviewItem,
    SourceRef,
    SourceType,
    UpdateDetection,
)

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_RFC_DIR = os.path.join(_REPO_ROOT, "application", "utils", "librarian", "_rfc_schemas")
_GOLDEN_SCHEMA = os.path.join(_HERE, "fixtures", "golden_dataset.schema.json")


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _build_registry() -> Registry:
    """Register every vendored RFC schema under its $id so $refs resolve."""
    resources = []
    for name in os.listdir(_RFC_DIR):
        if name.endswith(".json"):
            schema = _load(os.path.join(_RFC_DIR, name))
            resources.append((schema["$id"], DRAFT202012.create_resource(schema)))
    return Registry().with_resources(resources)


_REGISTRY = _build_registry()


def _validator_for(schema_filename: str) -> jsonschema.Draft202012Validator:
    schema = _load(os.path.join(_RFC_DIR, schema_filename))
    return jsonschema.Draft202012Validator(schema, registry=_REGISTRY)


def _round_trip_through_canonical(self, model_instance, schema_filename: str):
    """Dump the Pydantic model to plain JSON and assert canonical schema accepts it."""
    payload = json.loads(model_instance.model_dump_json(exclude_none=True))
    errors = sorted(_validator_for(schema_filename).iter_errors(payload), key=str)
    self.assertEqual(
        errors,
        [],
        msg=f"{type(model_instance).__name__} failed canonical schema: {errors}",
    )


# Shared fixtures for envelope tests
GITHUB_SOURCE = SourceRef(
    type=SourceType.github,
    repo="OWASP/ASVS",
    commit_sha="abc1234",
    committed_at="2026-02-01T01:00:00Z",
)
REPO_LOCATOR = Locator(
    kind=LocatorKind.repo_path,
    id="4.0/en/0x11-V2-Authentication.md",
    path="4.0/en/0x11-V2-Authentication.md",
)
KNOWLEDGE_SNAPSHOT = KnowledgeSnapshot(
    text="Verify MFA.", source=GITHUB_SOURCE, locator=REPO_LOCATOR
)
RETRIEVAL = RetrievalAudit(
    retriever="pgvector+cross-encoder/0.1.0",
    candidates=[
        CreCandidate(
            cre_id="123-456", cre_name="Auth", score_vector=0.72, score_rerank=0.76
        )
    ],
    reranked=[CreCandidate(cre_id="123-456", score_rerank=0.76)],
    threshold=0.8,
)
UPDATE_NEW = UpdateDetection(is_update=False)


class TestSourceRef(unittest.TestCase):
    def test_github_requires_repo_and_commit_sha(self):
        with self.assertRaises(ValidationError):
            SourceRef(type=SourceType.github, committed_at="2026-01-01T00:00:00Z")
        with self.assertRaises(ValidationError):
            SourceRef(
                type=SourceType.github, repo="r", committed_at="2026-01-01T00:00:00Z"
            )

    def test_url_type_does_not_require_repo(self):
        SourceRef(
            type=SourceType.url,
            url="https://x",
            committed_at="2026-01-01T00:00:00Z",
        )

    def test_extra_field_forbidden(self):
        with self.assertRaises(ValidationError):
            SourceRef(
                type=SourceType.url,
                url="https://x",
                committed_at="2026-01-01T00:00:00Z",
                surprise=1,
            )


class TestLocator(unittest.TestCase):
    def test_repo_path_requires_path(self):
        with self.assertRaises(ValidationError):
            Locator(kind=LocatorKind.repo_path, id="x")

    def test_url_kind_requires_url(self):
        with self.assertRaises(ValidationError):
            Locator(kind=LocatorKind.url, id="x")
        Locator(kind=LocatorKind.url, id="x", url="https://x")

    def test_feed_item_requires_url(self):
        with self.assertRaises(ValidationError):
            Locator(kind=LocatorKind.feed_item, id="x")


class TestKnowledgeItemRFC(unittest.TestCase):
    def _accepted(self, **over):
        base = dict(
            schema_version=SCHEMA_VERSION,
            chunk_id="chk:1",
            artifact_id="art:1",
            event_id="evt:1",
            pipeline_run_id="20260201T020000Z",
            filtered_at="2026-02-01T02:00:00Z",
            status=KnowledgeStatus.accepted,
            source=GITHUB_SOURCE,
            locator=REPO_LOCATOR,
            content=KnowledgeContent(text="x"),
            filter=Filter(
                stages=[FilterStage(name="llm_relevance", passed=True)],
                is_security_knowledge=True,
                confidence=0.9,
            ),
        )
        base.update(over)
        return KnowledgeItem(**base)

    def test_accepted_round_trips_canonical(self):
        _round_trip_through_canonical(self, self._accepted(), "knowledge-item.json")

    def test_accepted_requires_content(self):
        with self.assertRaises(ValidationError):
            self._accepted(content=None)

    def test_rejected_requires_rejection(self):
        with self.assertRaises(ValidationError):
            self._accepted(status=KnowledgeStatus.rejected, content=None)

    def test_rejected_round_trips_canonical(self):
        item = self._accepted(
            status=KnowledgeStatus.rejected,
            content=None,
            rejection=Rejection(reason_code="NOISE", reason_message="ext denylisted"),
        )
        _round_trip_through_canonical(self, item, "knowledge-item.json")

    def test_schema_version_pattern_enforced(self):
        with self.assertRaises(ValidationError):
            self._accepted(schema_version="bad")


class TestLinkProposalRFC(unittest.TestCase):
    def _proposal(self, **over):
        base = dict(
            schema_version=SCHEMA_VERSION,
            chunk_id="chk:1",
            artifact_id="art:1",
            pipeline_run_id="20260201T020000Z",
            classified_at="2026-02-01T02:25:00Z",
            knowledge=KNOWLEDGE_SNAPSHOT,
            retrieval=RETRIEVAL,
            links=[
                ProposedLink(cre_id="123-456", link_type="Related", confidence=0.94)
            ],
            update_detection=UPDATE_NEW,
        )
        base.update(over)
        return LinkProposal(**base)

    def test_round_trips_canonical(self):
        _round_trip_through_canonical(self, self._proposal(), "link-proposal.json")

    def test_status_is_fixed_to_linked(self):
        self.assertEqual(self._proposal().status, "linked")

    def test_links_min_length(self):
        with self.assertRaises(ValidationError):
            self._proposal(links=[])

    def test_pipeline_run_id_required(self):
        with self.assertRaises(ValidationError):
            self._proposal(pipeline_run_id=None)

    def test_extra_field_forbidden(self):
        # Building a proposal and tacking an extra key onto the JSON should fail
        # canonical validation (extra="forbid" + additionalProperties:false).
        payload = json.loads(self._proposal().model_dump_json(exclude_none=True))
        payload["surprise"] = 1
        errors = list(_validator_for("link-proposal.json").iter_errors(payload))
        self.assertTrue(errors, "canonical schema must reject extra fields")


class TestReviewItemRFC(unittest.TestCase):
    def _review(self, **over):
        base = dict(
            schema_version=SCHEMA_VERSION,
            review_id="rev_1",
            chunk_id="chk:1",
            artifact_id="art:1",
            pipeline_run_id="20260201T020000Z",
            created_at="2026-02-01T02:40:00Z",
            reason_code="BELOW_THRESHOLD",
            knowledge=KNOWLEDGE_SNAPSHOT,
            retrieval=RETRIEVAL,
            update_detection=UPDATE_NEW,
        )
        base.update(over)
        return ReviewItem(**base)

    def test_round_trips_canonical(self):
        _round_trip_through_canonical(self, self._review(), "review-item.json")

    def test_status_is_fixed_to_review_required(self):
        self.assertEqual(self._review().status, "review_required")

    def test_pipeline_run_id_required(self):
        with self.assertRaises(ValidationError):
            self._review(pipeline_run_id=None)

    def test_module_c_librarian_md_example_round_trips(self):
        """Re-validate the literal example from docs/owasp-graph/apis/module-c-librarian.md."""
        example = {
            "schema_version": "0.2.0",
            "review_id": "rev_20260201_00042",
            "chunk_id": "chk:art:OWASP/wstg:x:4",
            "artifact_id": "art:OWASP/wstg:document/4-Web_Application_Security_Testing/x",
            "pipeline_run_id": "20260201T020000Z",
            "created_at": "2026-02-01T02:40:00Z",
            "status": "review_required",
            "reason_code": "BELOW_THRESHOLD",
            "knowledge": {
                "text": "Do not use MD5 for password hashing.",
                "source": {
                    "type": "github",
                    "repo": "OWASP/wstg",
                    "commit_sha": "def7890",
                    "committed_at": "2026-02-01T01:30:00Z",
                },
                "locator": {
                    "kind": "repo_path",
                    "id": "document/4-Web_Application_Security_Testing/x",
                    "path": "document/4-Web_Application_Security_Testing/x",
                },
            },
            "retrieval": {
                "retriever": "pgvector+cross-encoder/0.1.0",
                "threshold": 0.8,
                "candidates": [
                    {
                        "cre_id": "123-456",
                        "cre_name": "Password storage",
                        "score_vector": 0.72,
                        "score_rerank": 0.76,
                    }
                ],
                "reranked": [{"cre_id": "123-456", "score_rerank": 0.76}],
            },
            "suggested_links": [
                {"cre_id": "123-456", "link_type": "Related", "confidence": 0.76}
            ],
            "update_detection": {"is_update": False, "adversarial_flags": []},
        }
        # Pydantic round-trip
        review = ReviewItem.model_validate(example)
        self.assertEqual(review.review_id, "rev_20260201_00042")
        # canonical round-trip on the Pydantic dump
        _round_trip_through_canonical(self, review, "review-item.json")


class TestKnowledgeQueueItem(unittest.TestCase):
    """Internal model — mirrors B's SQL row. Not an RFC contract."""

    def test_minimal_row(self):
        item = KnowledgeQueueItem(
            id="uuid-1",
            source_repo="OWASP/ASVS",
            source_path="4.0/en/0x11.md",
            source_commit_sha="abc1234567890",
            text="Verify X.",
            confidence=0.9,
            llm_label="KNOWLEDGE",
            created_at="2026-05-25T02:25:00Z",
        )
        self.assertIsNone(item.consumed_at)

    def test_confidence_bounds(self):
        with self.assertRaises(ValidationError):
            KnowledgeQueueItem(
                id="x",
                source_repo="r",
                source_path="p",
                source_commit_sha="c",
                text="t",
                confidence=1.5,
                llm_label="KNOWLEDGE",
                created_at="2026-05-25T02:25:00Z",
            )


class TestGoldenDataset(unittest.TestCase):
    """The internal harness row mirrors fixtures/golden_dataset.schema.json."""

    def _row(self, **over):
        row = {
            "id": "gold:test",
            "schema_version": "0.1.0",
            "slice": "positive",
            "input": {"text": "x"},
            "expected": {"decision": "linked", "cre_ids": ["1-2"]},
            "provenance": {"ground_truth_source": "test"},
        }
        row.update(over)
        return row

    def test_explicit_requires_explicit_cre_ref(self):
        with self.assertRaises(ValidationError):
            GoldenDatasetRow.model_validate(
                self._row(slice="explicit", input={"text": "x"})
            )

    def test_update_requires_prior_text_and_is_update(self):
        with self.assertRaises(ValidationError):
            GoldenDatasetRow.model_validate(
                self._row(slice="update", input={"text": "x"})
            )

    def test_review_requires_reason_code(self):
        with self.assertRaises(ValidationError):
            GoldenDatasetRow.model_validate(self._row(expected={"decision": "review"}))

    def test_linked_requires_cre_ids(self):
        with self.assertRaises(ValidationError):
            GoldenDatasetRow.model_validate(self._row(expected={"decision": "linked"}))

    def test_valid_row_round_trips(self):
        GoldenDatasetRow.model_validate(self._row())


if __name__ == "__main__":
    unittest.main()
