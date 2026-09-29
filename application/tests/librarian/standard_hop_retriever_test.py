"""Hermetic tests for Standard-prose retrieval + Link hop into CRE ids."""

from cre_logging import get_logger

logger = get_logger(__name__)

import unittest

from application.utils.librarian.candidate_retriever import (
    CandidatePool,
    CandidateRetriever,
)
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit
from application.utils.librarian.standard_hop_retriever import (
    StandardHopRetriever,
    merge_cre_audits,
)

_VECTORS = {
    "nist-ac2": [1.0, 0.0],
    "cre-only": [0.0, 1.0],
}


def _embed(text: str):
    return _VECTORS[text]


class _Inner:
    def __init__(self, audit: RetrievalAudit) -> None:
        self._audit = audit
        self.calls: list[str] = []

    def retrieve(self, text: str, *, allowlist=None):
        self.calls.append(text)
        return self._audit


def _audit(*ids: str, retriever: str = "inner") -> RetrievalAudit:
    return RetrievalAudit(
        retriever=retriever,
        candidates=[CreCandidate(cre_id=i, score_vector=0.5) for i in ids],
        reranked=[],
        threshold=0.8,
    )


class MergeCreAuditsTest(unittest.TestCase):
    def test_union_keeps_max_score_and_inner_order_bias(self) -> None:
        cre = RetrievalAudit(
            retriever="cre",
            candidates=[
                CreCandidate(cre_id="aaa", score_vector=0.4),
                CreCandidate(cre_id="bbb", score_vector=0.9),
            ],
            reranked=[],
            threshold=0.8,
        )
        hop = RetrievalAudit(
            retriever="hop",
            candidates=[
                CreCandidate(cre_id="aaa", score_vector=0.7),
                CreCandidate(cre_id="ccc", score_vector=0.8),
            ],
            reranked=[],
            threshold=0.8,
        )
        merged = merge_cre_audits(cre, hop, tag="cre+std-hop")
        self.assertEqual([c.cre_id for c in merged.candidates], ["bbb", "ccc", "aaa"])
        scores = {c.cre_id: c.score_vector for c in merged.candidates}
        self.assertAlmostEqual(scores["aaa"], 0.7)
        self.assertEqual(merged.retriever, "cre+std-hop")


class StandardHopRetrieverTest(unittest.TestCase):
    def setUp(self) -> None:
        # Node n-ac2 embedding aligns with query nist-ac2; n-junk is orthogonal.
        self.std_retriever = CandidateRetriever(
            embed_fn=_embed,
            pool=CandidatePool.from_mapping(
                {
                    "n-ac2": [1.0, 0.0],
                    "n-junk": [0.0, 1.0],
                }
            ),
            top_k=2,
            threshold=0.8,
        )
        self.inner = _Inner(_audit("cre-from-hub"))

    def test_hops_standard_hit_to_linked_cres(self) -> None:
        hop = StandardHopRetriever(
            inner=self.inner,
            standard_retriever=self.std_retriever,
            node_to_cres={"n-ac2": ("cre-ac2",), "n-junk": ("cre-unrelated",)},
            node_contents={
                "n-ac2": "Account Management AC-2 organizations.",
                "n-junk": "unrelated",
            },
            node_names={"n-ac2": "NIST 800-53 v5", "n-junk": "NIST 800-53 v5"},
        )
        audit = hop.retrieve("nist-ac2")
        ids = [c.cre_id for c in audit.candidates]
        self.assertIn("cre-from-hub", ids)
        self.assertIn("cre-ac2", ids)
        self.assertNotIn("cre-unrelated", ids)

    def test_firewall_drops_standard_whose_content_echoes_the_query(self) -> None:
        hop = StandardHopRetriever(
            inner=self.inner,
            standard_retriever=self.std_retriever,
            node_to_cres={"n-ac2": ("leaked-cre",)},
            node_contents={"n-ac2": "nist-ac2 exact eval row text nist-ac2"},
            node_names={"n-ac2": "ASVS"},
        )
        audit = hop.retrieve("nist-ac2")
        self.assertEqual([c.cre_id for c in audit.candidates], ["cre-from-hub"])

    def test_junk_frame_buster_content_is_skipped(self) -> None:
        hop = StandardHopRetriever(
            inner=self.inner,
            standard_retriever=self.std_retriever,
            node_to_cres={"n-ac2": ("cre-ac2",)},
            node_contents={
                "n-ac2": "you are viewing this page in an unauthorized frame window"
            },
            node_names={"n-ac2": "NIST 800-53 v5"},
        )
        audit = hop.retrieve("nist-ac2")
        self.assertEqual([c.cre_id for c in audit.candidates], ["cre-from-hub"])

    def test_family_allowlist_skips_other_standards(self) -> None:
        hop = StandardHopRetriever(
            inner=self.inner,
            standard_retriever=self.std_retriever,
            node_to_cres={"n-ac2": ("cre-ac2",)},
            node_contents={"n-ac2": "Account Management"},
            node_names={"n-ac2": "NIST 800-53 v5"},
            allowed_families=("PCI DSS",),
        )
        audit = hop.retrieve("nist-ac2")
        self.assertEqual([c.cre_id for c in audit.candidates], ["cre-from-hub"])

    def test_caps_cres_per_standard_hit(self) -> None:
        hop = StandardHopRetriever(
            inner=self.inner,
            standard_retriever=self.std_retriever,
            node_to_cres={"n-ac2": ("c1", "c2", "c3", "c4", "c5")},
            node_contents={"n-ac2": "Account Management"},
            node_names={"n-ac2": "PCI DSS"},
            max_cres_per_hit=2,
        )
        audit = hop.retrieve("nist-ac2")
        hopped = [c.cre_id for c in audit.candidates if c.cre_id != "cre-from-hub"]
        self.assertEqual(hopped, ["c1", "c2"])
