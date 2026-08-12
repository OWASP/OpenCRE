"""Tests for the envelope sinks.

``persists`` is the load-bearing property here: the queue runner reads it to
decide whether retiring a source row would lose work, so a sink that lies about
it would silently destroy chunks.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from application.utils.librarian.envelope_sink import (
    JsonlEnvelopeSink,
    NullEnvelopeSink,
)
from application.utils.librarian.schemas import (
    SCHEMA_VERSION,
    CreCandidate,
    KnowledgeSnapshot,
    LinkProposal,
    Locator,
    ProposedLink,
    RetrievalAudit,
    SourceRef,
    UpdateDetection,
)

AT = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)


def _proposal(chunk_id: str = "chk:1") -> LinkProposal:
    return LinkProposal(
        schema_version=SCHEMA_VERSION,
        chunk_id=chunk_id,
        artifact_id="art:1",
        pipeline_run_id="run-1",
        classified_at=AT,
        knowledge=KnowledgeSnapshot(
            text="Verify passwords are at least 12 characters.",
            source=SourceRef(
                type="github",
                repo="OWASP/ASVS",
                commit_sha="abc1234567890",
                committed_at=AT,
            ),
            locator=Locator(kind="repo_path", id="a.md", path="a.md"),
        ),
        retrieval=RetrievalAudit(
            retriever="stub/1.0.0",
            candidates=[CreCandidate(cre_id="616-305", score_vector=0.9)],
            reranked=[CreCandidate(cre_id="616-305", score_rerank=4.0)],
            threshold=0.8,
        ),
        links=[
            ProposedLink(
                cre_id="616-305", link_type="Automatically linked to", confidence=0.95
            )
        ],
        update_detection=UpdateDetection(is_update=False),
    )


class NullEnvelopeSinkTest(unittest.TestCase):
    def test_declares_that_it_does_not_persist(self) -> None:
        self.assertFalse(NullEnvelopeSink().persists)

    def test_counts_without_keeping(self) -> None:
        sink = NullEnvelopeSink()
        self.assertEqual(sink.write([_proposal(), _proposal("chk:2")]), 2)
        self.assertEqual(sink.written, 2)


class JsonlEnvelopeSinkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "envelopes.jsonl")

    def test_declares_that_it_persists(self) -> None:
        self.assertTrue(JsonlEnvelopeSink(self.path).persists)

    def test_writes_one_rfc_envelope_per_line(self) -> None:
        JsonlEnvelopeSink(self.path).write([_proposal("chk:1"), _proposal("chk:2")])

        with open(self.path, encoding="utf-8") as fh:
            lines = [json.loads(line) for line in fh if line.strip()]

        self.assertEqual([r["chunk_id"] for r in lines], ["chk:1", "chk:2"])
        # The file holds the RFC shape Module D will read, not a Python repr.
        self.assertEqual(lines[0]["status"], "linked")
        self.assertEqual(lines[0]["schema_version"], SCHEMA_VERSION)

    def test_appends_across_runs(self) -> None:
        """Several pipeline runs share one output file; each envelope carries
        its own run id, so truncating would throw away earlier runs."""
        sink = JsonlEnvelopeSink(self.path)
        sink.write([_proposal("chk:1")])
        sink.write([_proposal("chk:2")])

        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(len([ln for ln in fh if ln.strip()]), 2)

    def test_empty_batch_writes_nothing(self) -> None:
        self.assertEqual(JsonlEnvelopeSink(self.path).write([]), 0)
        self.assertFalse(os.path.exists(self.path))

    def test_creates_the_parent_directory(self) -> None:
        nested = os.path.join(self.dir, "a", "b", "envelopes.jsonl")
        JsonlEnvelopeSink(nested).write([_proposal()])
        self.assertTrue(os.path.exists(nested))

    def test_written_envelope_validates_against_the_vendored_rfc_schema(self) -> None:
        """What lands on disk is what Module D validates, so validate it here.

        The RFC types its optional fields as plain ``"string"`` and leaves them
        out of ``required``, so an absent value has to be an absent *key*.
        Pydantic's default dump writes ``"repo": null`` instead, which the
        schema rejects — every envelope failed, and the file still looked
        perfectly well-formed. Asserting "one JSON object per line" cannot catch
        that; only validating against the schema can.
        """
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource

        schema_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "utils",
                "librarian",
                "_rfc_schemas",
            )
        )
        schemas = [
            json.load(open(os.path.join(schema_dir, name), encoding="utf-8"))
            for name in sorted(os.listdir(schema_dir))
            if name.endswith(".json")
        ]
        # The schemas cross-reference each other by ``$id``, and link-proposal
        # also uses local ``#/$defs/...`` pointers, so resolution has to happen
        # in ``$id`` space rather than against a directory path.
        registry = Registry().with_resources(
            [(s["$id"], Resource.from_contents(s)) for s in schemas if "$id" in s]
        )
        schema = next(s for s in schemas if s["$id"].endswith("link-proposal.json"))

        JsonlEnvelopeSink(self.path).write([_proposal()])
        with open(self.path, encoding="utf-8") as fh:
            envelope = json.loads(fh.readline())

        errors = list(
            Draft202012Validator(schema, registry=registry).iter_errors(envelope)
        )

        self.assertEqual(
            errors,
            [],
            "written envelope must satisfy the RFC schema Module D reads:\n"
            + "\n".join(f"  {list(e.path)}: {e.message}" for e in errors[:5]),
        )

    def test_absent_optional_fields_are_omitted_not_nulled(self) -> None:
        # A github-sourced envelope carries no feed_url/post_guid. The key must
        # be gone, not present-and-null, or the RFC validator rejects it.
        JsonlEnvelopeSink(self.path).write([_proposal()])
        with open(self.path, encoding="utf-8") as fh:
            envelope = json.loads(fh.readline())

        def _nulls(node, path=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    yield from _nulls(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    yield from _nulls(v, f"{path}[{i}]")
            elif node is None:
                yield path

        self.assertEqual(list(_nulls(envelope)), [])


if __name__ == "__main__":
    unittest.main()
