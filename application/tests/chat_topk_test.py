"""#1075: OpenCRE Chat retrieves top-k passages through the Librarian seams.

Hermetic: no DB, no LLM. The database is a MagicMock shaped like
``Node_collection``; the AI client is a stub that records the prompt it was
given. Covers the success criteria listed on the issue:

- ``generate_text`` grounds on several passages and returns them all in ``table``
- the rendered prompt contains more than one numbered passage
- below-threshold path falls back to ``query_llm`` and does not claim ``accurate``
- the break-off rule (Rob's #962 question) as a pure function
- the non-pgvector (SQLite) lane returns a correctly ordered top-k across pages
- the pgvector top-k SQL / DB method validate inputs and degrade safely
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import unittest
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Tuple
from unittest.mock import MagicMock, patch

from application.database import pgvector_utils
from application.prompt_client import chat_retrieval
from application.prompt_client import prompt_client as prompt_client_mod
from application.prompt_client.chat_retrieval import (
    KIND_CRE,
    KIND_STANDARD,
    ChatPassage,
    ChatRetriever,
    apply_breakoff,
    render_passages,
    split_budget,
)


# --------------------------------------------------------------------------- helpers
class _Node:
    """Minimal stand-in for cre_defs.Standard / CRE: shallow_copy().todict()."""

    def __init__(self, **fields: Any) -> None:
        self._fields = fields
        self.name = fields.get("name")

    def shallow_copy(self) -> "_Node":
        return self

    def todict(self) -> Dict[str, Any]:
        return dict(self._fields)


def _emb(content: str, url: str = "") -> List[Any]:
    return [SimpleNamespace(embeddings_content=content, embeddings_url=url)]


def _pgvector_database(
    standards: List[Tuple[str, float]],
    cres: List[Tuple[str, float]],
    nodes: Dict[str, _Node],
    embeddings: Dict[str, List[Any]],
) -> MagicMock:
    db = MagicMock()
    db.can_use_pgvector_similarity.return_value = True

    def _top_k(
        _vec: Any, *, doc_type: str, id_column: str, k: int, similarity_threshold: float
    ) -> List[Tuple[str, float]]:
        rows = standards if id_column == "node_id" else cres
        return [(o, s) for o, s in rows if s >= similarity_threshold][:k]

    db.find_top_k_similar_embedding_ids.side_effect = _top_k
    db.get_nodes.side_effect = lambda db_id=None, **_: (
        [nodes[db_id]] if db_id in nodes else []
    )
    db.get_cre_by_db_id.side_effect = lambda oid: nodes[oid]
    db.get_embedding.side_effect = lambda oid: embeddings.get(oid, [])
    return db


# ---------------------------------------------------------------- break-off rule
class BreakoffRuleTest(unittest.TestCase):
    def test_keeps_within_delta_and_above_floor(self) -> None:
        scored = [("a", 0.90), ("b", 0.86), ("c", 0.80), ("d", 0.75), ("e", 0.60)]
        kept = apply_breakoff(scored, floor=0.7, delta=0.08, cap=5)
        # best 0.90, cut = max(0.7, 0.82) = 0.82 -> a and b only
        self.assertEqual(kept, [("a", 0.90), ("b", 0.86)])

    def test_floor_wins_when_best_is_low(self) -> None:
        scored = [("a", 0.72), ("b", 0.71), ("c", 0.69)]
        kept = apply_breakoff(scored, floor=0.7, delta=0.08, cap=5)
        # cut = max(0.7, 0.64) = 0.7 -> c is below the floor
        self.assertEqual([o for o, _ in kept], ["a", "b"])

    def test_cap_and_dedupe_and_unsorted_input(self) -> None:
        scored = [("b", 0.88), ("a", 0.90), ("a", 0.90), ("c", 0.87), ("d", 0.86)]
        kept = apply_breakoff(scored, floor=0.5, delta=0.5, cap=3)
        self.assertEqual([o for o, _ in kept], ["a", "b", "c"])

    def test_empty_and_zero_cap(self) -> None:
        self.assertEqual(apply_breakoff([], floor=0.7, delta=0.1, cap=5), [])
        self.assertEqual(apply_breakoff([("a", 0.9)], floor=0.7, delta=0.1, cap=0), [])

    def test_budget_split(self) -> None:
        self.assertEqual(split_budget(8000, 5), 1600)
        self.assertEqual(split_budget(8000, 1), 8000)
        self.assertEqual(split_budget(8000, 0), 8000)
        self.assertEqual(split_budget(500, 10), 200)  # never starve a passage


# ---------------------------------------------------------- retriever, pgvector
class ChatRetrieverPgvectorTest(unittest.TestCase):
    def _retriever(self, **kw: Any) -> Tuple[ChatRetriever, MagicMock]:
        nodes = {
            "samm": _Node(
                name="SAMM",
                doctype="Standard",
                section="Threat Assessment",
                hyperlink="https://owaspsamm.org/ta",
            ),
            "cheat": _Node(
                name="Cheat Sheets",
                doctype="Standard",
                section="Threat Modeling",
                hyperlink="https://cheatsheetseries.owasp.org/tm",
            ),
            "cheat2": _Node(
                name="Cheat Sheets",
                doctype="Standard",
                section="Threat Modeling Playbook",
                hyperlink="https://cheatsheetseries.owasp.org/tmp",
            ),
            "asvs": _Node(
                name="ASVS", doctype="Standard", section="V1", hyperlink="https://asvs"
            ),
            "cre1": _Node(id="011-010", name="Threat modeling", doctype="CRE"),
        }
        embeddings = {
            "samm": _emb(
                "SAMM threat assessment text " * 200, "https://owaspsamm.org/ta#tm"
            ),
            "cheat": _emb(
                "Cheat sheet threat modeling text",
                "https://cheatsheetseries.owasp.org/tm",
            ),
            "cheat2": _emb("Playbook text"),
            "asvs": _emb("ASVS V1 text"),
            "cre1": _emb("CRE threat modeling description"),
        }
        db = _pgvector_database(
            standards=[
                ("samm", 0.91),
                ("cheat", 0.89),
                ("cheat2", 0.885),
                ("asvs", 0.75),
            ],
            cres=[("cre1", 0.88)],
            nodes=nodes,
            embeddings=embeddings,
        )
        params = dict(
            top_k_retrieve=8,
            top_k_cre=4,
            top_k_prompt=5,
            floor=0.7,
            breakoff_delta=0.08,
            char_budget=8000,
        )
        params.update(kw)
        return ChatRetriever(db, **params), db

    def test_two_lanes_merged_ranked_and_deduped_per_document(self) -> None:
        retriever, db = self._retriever()
        passages = retriever.retrieve(
            "how to pick people for threat modeling", [0.1, 0.2]
        )

        # cut = 0.91 - 0.08 = 0.83: asvs (0.75) drops; cheat2 is a second Cheat Sheets
        # passage and is deduped per document until #1076 gives section rows.
        self.assertEqual([p.object_id for p in passages], ["samm", "cheat", "cre1"])
        self.assertEqual(
            [p.kind for p in passages], [KIND_STANDARD, KIND_STANDARD, KIND_CRE]
        )
        self.assertEqual([p.rank for p in passages], [1, 2, 3])
        # both lanes were queried with the right id column
        cols = sorted(
            c.kwargs["id_column"]
            for c in db.find_top_k_similar_embedding_ids.call_args_list
        )
        self.assertEqual(cols, ["cre_id", "node_id"])

    def test_passage_budget_is_split_across_passages(self) -> None:
        retriever, _ = self._retriever(char_budget=3000)
        passages = retriever.retrieve("q", [0.1, 0.2])
        self.assertEqual(len(passages), 3)
        for p in passages:
            self.assertLessEqual(len(p.content), 1000)

    def test_table_rows_keep_frontend_shape_plus_rank_score_and_url(self) -> None:
        retriever, _ = self._retriever()
        rows = [p.table_row() for p in retriever.retrieve("q", [0.1, 0.2])]
        self.assertEqual(rows[0]["name"], "SAMM")
        self.assertEqual(rows[0]["doctype"], "Standard")
        self.assertEqual(rows[0]["embeddingsUrl"], "https://owaspsamm.org/ta#tm")
        self.assertEqual(rows[0]["rank"], 1)
        self.assertAlmostEqual(rows[0]["score"], 0.91, places=3)
        self.assertNotIn("embeddingsUrl", rows[2])  # CRE row had no URL

    def test_rendered_block_numbers_every_passage_with_source(self) -> None:
        retriever, _ = self._retriever()
        block = render_passages(retriever.retrieve("q", [0.1, 0.2]))
        self.assertIn(
            "[1] SAMM §Threat Assessment (https://owaspsamm.org/ta#tm)", block
        )
        self.assertIn("[2] Cheat Sheets §Threat Modeling", block)
        self.assertIn("[3] CRE 011-010: Threat modeling", block)

    def test_nothing_above_floor_returns_empty(self) -> None:
        db = _pgvector_database(standards=[], cres=[], nodes={}, embeddings={})
        retriever = ChatRetriever(
            db,
            top_k_retrieve=8,
            top_k_cre=4,
            top_k_prompt=5,
            floor=0.7,
            breakoff_delta=0.08,
        )
        self.assertEqual(retriever.retrieve("q", [0.1, 0.2]), [])

    def test_rerank_hook_is_applied(self) -> None:
        def reverse(_q: str, ps: List[ChatPassage]) -> List[ChatPassage]:
            return list(reversed(ps))

        retriever, _ = self._retriever(rerank_fn=reverse)
        passages = retriever.retrieve("q", [0.1, 0.2])
        self.assertEqual([p.object_id for p in passages], ["cre1", "cheat", "samm"])
        self.assertEqual(
            [p.rank for p in passages], [1, 2, 3]
        )  # ranks follow final order

    def test_missing_node_is_skipped_not_fatal(self) -> None:
        retriever, db = self._retriever()
        db.get_nodes.side_effect = lambda db_id=None, **_: []  # every Standard vanished
        passages = retriever.retrieve("q", [0.1, 0.2])
        self.assertEqual([p.object_id for p in passages], ["cre1"])

    def test_invalid_k_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ChatRetriever(MagicMock(), top_k_prompt=0)


# ------------------------------------------------------- retriever, in-memory
def _paginated(
    pages: Dict[int, Dict[str, List[float]]]
) -> Callable[..., Tuple[Dict[str, List[float]], int, int]]:
    def _side_effect(*_a: Any, **kw: Any) -> Tuple[Dict[str, List[float]], int, int]:
        page = kw.get("page", 1)
        return pages.get(page, {}), len(pages), page

    return _side_effect


class ChatRetrieverInMemoryTest(unittest.TestCase):
    def test_top_k_across_pages_is_ordered_and_floored(self) -> None:
        db = MagicMock()
        db.can_use_pgvector_similarity.return_value = False
        db.get_embeddings_by_doc_type_paginated.side_effect = _paginated(
            {
                1: {"n1": [1.0, 0.0], "n2": [0.0, 1.0]},  # 1.0 and 0.0
                2: {"n3": [0.8, 0.6]},  # 0.8
                3: {"n4": [0.9, 0.436]},  # ~0.9
            }
        )
        retriever = ChatRetriever(
            db,
            top_k_retrieve=3,
            top_k_cre=1,
            top_k_prompt=5,
            floor=0.7,
            breakoff_delta=1.0,
        )
        lane = retriever._lane(
            [1.0, 0.0], doc_type="Standard", id_column="node_id", k=3
        )
        self.assertEqual([o for o, _ in lane], ["n1", "n4", "n3"])
        self.assertTrue(all(s >= 0.7 for _, s in lane))
        # every page visited exactly once
        self.assertEqual(db.get_embeddings_by_doc_type_paginated.call_count, 3)
        db.find_top_k_similar_embedding_ids.assert_not_called()

    def test_empty_hub_returns_nothing(self) -> None:
        db = MagicMock()
        db.can_use_pgvector_similarity.return_value = False
        db.get_embeddings_by_doc_type_paginated.side_effect = _paginated({1: {}})
        retriever = ChatRetriever(
            db,
            top_k_retrieve=3,
            top_k_cre=1,
            top_k_prompt=5,
            floor=0.7,
            breakoff_delta=0.1,
        )
        self.assertEqual(
            retriever._lane([1.0, 0.0], doc_type="Standard", id_column="node_id", k=3),
            [],
        )


# ------------------------------------------------------------ generate_text
class _AiStub:
    def __init__(self) -> None:
        self.prompts: List[str] = []
        self.knowledge: List[str] = []
        self.llm_calls = 0

    def get_text_embeddings(self, text: str) -> List[float]:
        return [0.1, 0.2]

    def create_chat_completion(self, prompt: str, closest_object_str: str) -> str:
        self.prompts.append(prompt)
        self.knowledge.append(closest_object_str)
        return "grounded answer [1][2]"

    def query_llm(self, raw_question: str) -> str:
        self.llm_calls += 1
        return "ungrounded essay"

    def get_model_name(self) -> str:
        return "stub-model"


def _handler_with(
    passages: List[ChatPassage],
) -> Tuple[prompt_client_mod.PromptHandler, _AiStub]:
    handler = prompt_client_mod.PromptHandler.__new__(prompt_client_mod.PromptHandler)
    ai = _AiStub()
    handler.ai_client = ai
    handler.database = MagicMock()
    stub_retriever = MagicMock()
    stub_retriever.retrieve.return_value = passages
    handler._chat_retriever_instance = stub_retriever
    return handler, ai


def _passage(
    rank: int, oid: str, title: str, content: str, url: str = ""
) -> ChatPassage:
    return ChatPassage(
        object_id=oid,
        kind=KIND_STANDARD,
        score=0.9 - rank / 100,
        rank=rank,
        title=title,
        content=content,
        url=url or None,
        row={"name": title, "doctype": "Standard", "section": "s"},
    )


class GenerateTextTopKTest(unittest.TestCase):
    def test_multiple_passages_reach_prompt_and_table(self) -> None:
        passages = [
            _passage(1, "a", "SAMM", "samm text", "https://samm#ta"),
            _passage(2, "b", "Cheat Sheets", "cheat text"),
            _passage(3, "c", "ASVS", "asvs text"),
        ]
        handler, ai = _handler_with(passages)

        out = handler.generate_text("how to pick people for threat modeling")

        self.assertTrue(out["accurate"])
        self.assertEqual(out["response"], "Answer: grounded answer [1][2]")
        self.assertEqual(len(out["table"]), 3)
        self.assertEqual([r["rank"] for r in out["table"]], [1, 2, 3])
        self.assertEqual(out["table"][0]["embeddingsUrl"], "https://samm#ta")
        self.assertEqual(ai.llm_calls, 0)
        knowledge = ai.knowledge[0]
        self.assertIn("[1] SAMM (https://samm#ta)", knowledge)
        self.assertIn("[2] Cheat Sheets", knowledge)
        self.assertIn("[3] ASVS", knowledge)

    def test_rendered_prompt_template_carries_numbered_passages(self) -> None:
        passages = [
            _passage(1, "a", "SAMM", "samm text"),
            _passage(2, "b", "ASVS", "asvs text"),
        ]
        rendered = prompt_client_mod._render_chat_prompt(
            question="q", retrieved_knowledge=render_passages(passages)
        )
        self.assertIn("numbered passages [1]..[n]", rendered)
        self.assertIn("[1] SAMM", rendered)
        self.assertIn("[2] ASVS", rendered)
        self.assertIn("cite it inline with its number", rendered)

    def test_below_threshold_falls_back_and_is_not_accurate(self) -> None:
        handler, ai = _handler_with([])
        out = handler.generate_text("something with no match")
        self.assertFalse(out["accurate"])
        self.assertEqual(out["table"], [])
        self.assertEqual(out["response"], "Answer: ungrounded essay")
        self.assertEqual(ai.llm_calls, 1)
        self.assertEqual(ai.prompts, [])  # no grounded completion was attempted

    def test_empty_prompt_short_circuits(self) -> None:
        handler, ai = _handler_with([])
        out = handler.generate_text("")
        self.assertEqual(out["response"], "")
        self.assertEqual(ai.llm_calls, 0)

    def test_retriever_is_built_lazily_over_the_handler_database(self) -> None:
        handler = prompt_client_mod.PromptHandler.__new__(
            prompt_client_mod.PromptHandler
        )
        handler.database = MagicMock()
        with patch.dict(
            "os.environ", {"CHATBOT_TOPK_PROMPT": "3", "CHATBOT_BREAKOFF_DELTA": "0.05"}
        ):
            retriever = handler._chat_retriever()
        self.assertIs(retriever.database, handler.database)
        self.assertEqual(retriever.top_k_prompt, 3)
        self.assertAlmostEqual(retriever.breakoff_delta, 0.05)
        self.assertIs(handler._chat_retriever(), retriever)  # cached


# ---------------------------------------------------------------- DB / SQL
class TopKSqlTest(unittest.TestCase):
    def test_sql_has_limit_param_and_validates_column(self) -> None:
        sql = pgvector_utils.top_k_similar_ids_sql("node_id")
        self.assertIn("LIMIT :k", sql)
        self.assertIn("node_id AS object_id", sql)
        with self.assertRaises(ValueError):
            pgvector_utils.top_k_similar_ids_sql("id")

    def test_db_method_filters_threshold_and_preserves_order(self) -> None:
        from application.database.db import Node_collection

        database = Node_collection.__new__(Node_collection)
        session = MagicMock()
        session.execute.return_value.fetchall.return_value = [
            SimpleNamespace(object_id="a", score=0.95),
            SimpleNamespace(object_id="b", score=0.80),
            SimpleNamespace(object_id="c", score=0.60),
        ]
        session.get_bind.return_value = MagicMock()
        database.session = session
        database._pgvector_similarity_ready = True

        rows = database.find_top_k_similar_embedding_ids(
            [0.1, 0.2],
            doc_type="Standard",
            id_column="node_id",
            k=5,
            similarity_threshold=0.7,
        )
        self.assertEqual(rows, [("a", 0.95), ("b", 0.80)])
        params = session.execute.call_args.args[1]
        self.assertEqual(params["k"], 5)
        self.assertEqual(params["doc_type"], "Standard")

    def test_db_method_degrades_to_empty_on_query_error(self) -> None:
        from application.database.db import Node_collection

        database = Node_collection.__new__(Node_collection)
        session = MagicMock()
        session.execute.side_effect = RuntimeError("driver boom")
        session.get_bind.return_value = MagicMock()
        database.session = session
        database._pgvector_similarity_ready = True
        with patch("application.database.db.logger"):
            rows = database.find_top_k_similar_embedding_ids(
                [0.1], doc_type="CRE", id_column="cre_id", k=3, similarity_threshold=0.7
            )
        self.assertEqual(rows, [])

    def test_db_method_refuses_sqlite_with_systemexit(self) -> None:
        from application.database.db import Node_collection

        database = Node_collection.__new__(Node_collection)
        database.session = MagicMock()
        database._pgvector_similarity_ready = False
        with self.assertRaises(SystemExit):
            database.find_top_k_similar_embedding_ids(
                [0.1], doc_type="CRE", id_column="cre_id", k=3, similarity_threshold=0.7
            )

    def test_db_method_rejects_non_positive_k(self) -> None:
        from application.database.db import Node_collection

        database = Node_collection.__new__(Node_collection)
        database.session = MagicMock()
        database._pgvector_similarity_ready = True
        with self.assertRaises(ValueError):
            database.find_top_k_similar_embedding_ids(
                [0.1], doc_type="CRE", id_column="cre_id", k=0, similarity_threshold=0.7
            )


class SharedTopKHelperTest(unittest.TestCase):
    """Module C's in-memory retriever and Chat now share one ranking primitive."""

    def test_top_k_cosine_orders_and_caps(self) -> None:
        import numpy as np

        from application.utils.librarian.candidate_retriever import top_k_cosine

        matrix = np.asarray([[0.0, 1.0], [1.0, 0.0], [0.7, 0.7]])
        ranked = top_k_cosine(np.asarray([1.0, 0.0]), matrix, ["y", "x", "d"], 2)
        self.assertEqual([o for o, _ in ranked], ["x", "d"])
        self.assertAlmostEqual(ranked[0][1], 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
