"""Tests for the C.1 semantic candidate retriever (Week 3).

Hermetic: the embedding function and the CRE vector hub are injected as
controlled vectors, so cosine ordering, top-K truncation, the dim gate, and
the RetrievalAudit shape are all assertable without an LLM or a DB.
"""

import unittest
from unittest.mock import MagicMock

from application.utils.librarian.candidate_retriever import (
    PGVECTOR_RETRIEVER_NAME,
    RETRIEVER_NAME,
    CandidatePool,
    CandidateRetriever,
    DimensionMismatchError,
    EmptyPoolError,
    PgVectorRetriever,
    RetrieverBackend,
    RetrieverError,
    build_retriever,
    to_pgvector_literal,
)

# A controlled hub. Query [1,0,0] -> cosine a=1.0, c=0.707, b=0.0 -> order a,c,b.
HUB = {
    "111-111": [1.0, 0.0, 0.0],  # "a"
    "222-222": [0.0, 1.0, 0.0],  # "b"
    "333-333": [1.0, 1.0, 0.0],  # "c"
}

# Deterministic embedder: text -> a fixed query vector.
_VECTORS = {
    "about-a": [1.0, 0.0, 0.0],
    "about-b": [0.0, 1.0, 0.0],
    "wrong-width": [1.0, 0.0],
}


def fake_embed(text):
    return _VECTORS[text]


def make_retriever(top_k=20, threshold=0.8, cre_names=None):
    return CandidateRetriever(
        embed_fn=fake_embed,
        pool=CandidatePool.from_mapping(HUB),
        top_k=top_k,
        threshold=threshold,
        cre_names=cre_names,
    )


class CandidatePoolTest(unittest.TestCase):
    def test_from_mapping_builds_aligned_matrix(self) -> None:
        pool = CandidatePool.from_mapping(HUB)
        self.assertEqual(pool.dim, 3)
        self.assertEqual(set(pool.cre_ids), set(HUB))
        self.assertEqual(pool.matrix.shape, (3, 3))

    def test_empty_pool_rejected(self) -> None:
        with self.assertRaises(EmptyPoolError):
            CandidatePool.from_mapping({})

    def test_ragged_vectors_rejected(self) -> None:
        with self.assertRaises(DimensionMismatchError):
            CandidatePool.from_mapping({"a": [1.0, 0.0], "b": [1.0]})

    def test_zero_width_vectors_rejected(self) -> None:
        with self.assertRaises(DimensionMismatchError):
            CandidatePool.from_mapping({"a": [], "b": []})


class RetrieveTest(unittest.TestCase):
    def test_candidates_rank_ordered_by_cosine(self) -> None:
        audit = make_retriever().retrieve("about-a")
        self.assertEqual(
            [c.cre_id for c in audit.candidates],
            ["111-111", "333-333", "222-222"],
        )
        # score_vector is the cosine; populated and descending.
        scores = [c.score_vector for c in audit.candidates]
        self.assertAlmostEqual(scores[0], 1.0)
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_top_k_truncates_and_caps_at_pool_size(self) -> None:
        # top_k larger than the hub returns the whole hub, no error.
        self.assertEqual(
            len(make_retriever(top_k=20).retrieve("about-a").candidates), 3
        )
        # top_k smaller than the hub returns exactly the best k.
        top1 = make_retriever(top_k=1).retrieve("about-a")
        self.assertEqual([c.cre_id for c in top1.candidates], ["111-111"])

    def test_audit_shape_for_w3(self) -> None:
        audit = make_retriever(threshold=0.8).retrieve("about-b")
        self.assertEqual(audit.retriever, RETRIEVER_NAME)
        self.assertEqual(audit.reranked, [])  # cross-encoder lands W4
        self.assertEqual(audit.threshold, 0.8)
        # The closest to [0,1,0] is b, then c (0.707), then a (0.0).
        self.assertEqual(audit.candidates[0].cre_id, "222-222")

    def test_cre_names_populated_when_provided(self) -> None:
        audit = make_retriever(cre_names={"111-111": "Authentication"}).retrieve(
            "about-a"
        )
        self.assertEqual(audit.candidates[0].cre_name, "Authentication")
        # Unnamed candidates stay None, never KeyError.
        self.assertIsNone(audit.candidates[-1].cre_name)

    def test_query_dim_mismatch_is_caught(self) -> None:
        with self.assertRaises(DimensionMismatchError):
            make_retriever().retrieve("wrong-width")


class ConstructionTest(unittest.TestCase):
    def test_non_positive_top_k_rejected(self) -> None:
        with self.assertRaises(RetrieverError):
            make_retriever(top_k=0)


# --- pgvector backend (hermetic: the DB is a fake recording connection) ---


class _FakeRow:
    def __init__(self, cre_id, score):
        self.cre_id = cre_id
        self.score = score


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConnection:
    """Records the last execute() call and returns canned, pre-ordered rows."""

    def __init__(self, rows):
        self._rows = rows
        self.last_sql = None
        self.last_params = None

    def execute(self, sql, params):
        self.last_sql = str(sql)
        self.last_params = params
        return _FakeResult(self._rows)


class PgVectorRetrieverTest(unittest.TestCase):
    def test_pgvector_literal_format(self) -> None:
        self.assertEqual(to_pgvector_literal([1, 2.5, 0]), "[1.0,2.5,0.0]")

    def test_parses_db_rows_in_order(self) -> None:
        # The DB does the ranking; the retriever preserves ORDER BY order.
        conn = _FakeConnection([_FakeRow("111-111", 0.97), _FakeRow("333-333", 0.71)])
        retriever = PgVectorRetriever(
            embed_fn=fake_embed, connection=conn, top_k=20, threshold=0.8
        )
        audit = retriever.retrieve("about-a")
        self.assertEqual(audit.retriever, PGVECTOR_RETRIEVER_NAME)
        self.assertEqual([c.cre_id for c in audit.candidates], ["111-111", "333-333"])
        self.assertAlmostEqual(audit.candidates[0].score_vector, 0.97)
        self.assertEqual(audit.reranked, [])

    def test_binds_query_vector_doctype_and_limit(self) -> None:
        conn = _FakeConnection([])
        PgVectorRetriever(
            embed_fn=fake_embed, connection=conn, top_k=7, threshold=0.8
        ).retrieve("about-a")
        self.assertEqual(conn.last_params["q"], "[1.0,0.0,0.0]")
        self.assertEqual(conn.last_params["doc_type"], "CRE")
        self.assertEqual(conn.last_params["k"], 7)
        # Cosine via the <=> operator, scored as similarity (1 - distance).
        self.assertIn("<=>", conn.last_sql)


class BuildRetrieverTest(unittest.TestCase):
    def test_in_memory_requires_pool(self) -> None:
        with self.assertRaises(RetrieverError):
            build_retriever(
                RetrieverBackend.in_memory, fake_embed, top_k=20, threshold=0.8
            )

    def test_pgvector_requires_connection(self) -> None:
        with self.assertRaises(RetrieverError):
            build_retriever(
                RetrieverBackend.pgvector, fake_embed, top_k=20, threshold=0.8
            )

    def test_factory_routes_to_each_backend(self) -> None:
        in_mem = build_retriever(
            RetrieverBackend.in_memory,
            fake_embed,
            top_k=20,
            threshold=0.8,
            pool=CandidatePool.from_mapping(HUB),
        )
        self.assertIsInstance(in_mem, CandidateRetriever)
        pg = build_retriever(
            RetrieverBackend.pgvector,
            fake_embed,
            top_k=20,
            threshold=0.8,
            connection=_FakeConnection([]),
        )
        self.assertIsInstance(pg, PgVectorRetriever)

    def test_pgvector_backend_exits_on_sqlite_connection(self) -> None:
        conn = MagicMock()
        conn.dialect.name = "sqlite"
        with self.assertRaises(SystemExit) as cm:
            build_retriever(
                RetrieverBackend.pgvector,
                fake_embed,
                top_k=20,
                threshold=0.8,
                connection=conn,
            )
        self.assertIn("pgvector embeddings are required", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
