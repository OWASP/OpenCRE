#!/usr/bin/env python3
"""Run Module C on dual-classify keepers → decision_queue (Module D handoff).

Copies CRE embeddings from ``standards_cache.sqlite``, seeds ``knowledge_queue``
from the expensive-gate keepers (or intersection), runs C.0–C.4 with live
Gemini query embeddings + a vector-score reranker (no torch cross-encoder
required in the agent sandbox), and writes a JSON report of links / reviews.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "tmp" / "oie_owasp_eval"


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _seed_knowledge(session: Any, run_id: str, keepers: List[Dict[str, Any]]) -> int:
    from application.database.db import KnowledgeQueueItem, generate_uuid
    from application.utils.noise_filter.hashing import compute_content_hash

    session.query(KnowledgeQueueItem).filter_by(pipeline_run_id=run_id).delete(
        synchronize_session=False
    )
    n = 0
    for k in keepers:
        text = k.get("text") or k.get("_full_text") or k.get("text_preview") or ""
        if not text.strip():
            continue
        chunk_id = k["chunk_id"]
        # chk:art:OWASP/Repo:path:idx → art:OWASP/Repo:path
        artifact_id = k.get("artifact_id")
        if not artifact_id:
            body = chunk_id[4:] if chunk_id.startswith("chk:") else chunk_id
            artifact_id = body.rsplit(":", 1)[0]
        session.add(
            KnowledgeQueueItem(
                id=generate_uuid(),
                content_hash=compute_content_hash(text),
                chunk_id=chunk_id,
                artifact_id=artifact_id,
                pipeline_run_id=run_id,
                schema_version="0.2.0",
                source_type="github",
                source_repo=k.get("source_repo") or "OWASP/unknown",
                source_commit_sha="tarball00000000000000000000000000000001",
                source_committed_at="2026-08-29T18:00:00Z",
                locator_kind="repo_path",
                locator_path=k.get("locator_path") or "",
                span_index=0,
                span_total=1,
                text=text,
                llm_label=k.get("llm_label") or "KNOWLEDGE",
                confidence=float(k.get("confidence") or 0.9),
                created_at=datetime.now(timezone.utc),
            )
        )
        n += 1
    session.commit()
    return n


def _load_keepers_with_full_text() -> List[Dict[str, Any]]:
    """Intersection of cheap∩expensive keepers, with full text from eval_expensive."""
    cheap = json.loads((ART / "classify_cheap.json").read_text())
    exp = json.loads((ART / "classify_expensive.json").read_text())
    cheap_ids = {k["chunk_id"] for k in cheap["knowledge"]["would_flow_to_c"]}
    exp_map = {k["chunk_id"]: k for k in exp["knowledge"]["would_flow_to_c"]}
    both_ids = cheap_ids & set(exp_map)

    # Pull full text from expensive sqlite knowledge_queue
    exp_db = ART / "eval_expensive.sqlite"
    full: Dict[str, str] = {}
    if exp_db.is_file():
        con = sqlite3.connect(exp_db)
        for cid, text in con.execute(
            "select chunk_id, text from knowledge_queue"
        ).fetchall():
            full[cid] = text or ""
        con.close()

    keepers = []
    for cid in sorted(both_ids):
        k = dict(exp_map[cid])
        k["_full_text"] = full.get(cid) or k.get("text_preview") or ""
        k["text"] = k["_full_text"]
        keepers.append(k)
    return keepers


def _cre_lookup(session: Any) -> Dict[str, Dict[str, str]]:
    from application.database.db import CRE

    out: Dict[str, Dict[str, str]] = {}
    for row in session.query(CRE).all():
        out[row.id] = {
            "id": row.id,
            "external_id": getattr(row, "external_id", None) or "",
            "name": row.name or "",
        }
    return out


def main() -> int:
    _load_dotenv()
    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    os.environ["CRE_LIBRARIAN_RETRIEVER_BACKEND"] = "in_memory"
    sys.path.insert(0, str(ROOT))

    src = ROOT / "standards_cache.sqlite"
    dst = ART / "eval_module_c.sqlite"
    if not src.is_file():
        print("missing standards_cache.sqlite", file=sys.stderr)
        return 2

    print(f"copy {src} → {dst} …", flush=True)
    if dst.exists():
        dst.unlink()
    shutil.copy2(src, dst)

    run_id = "owasp-eval-20260829T192100Z-module-c"
    keepers = _load_keepers_with_full_text()
    # Cap for cost/time in agent: prefer 80 stratified by repo if huge
    if len(keepers) > 80:
        by_repo: Dict[str, List[Dict[str, Any]]] = {}
        for k in keepers:
            by_repo.setdefault(k.get("source_repo") or "?", []).append(k)
        sampled: List[Dict[str, Any]] = []
        per = max(2, 80 // max(len(by_repo), 1))
        for repo, rows in sorted(by_repo.items(), key=lambda kv: -len(kv[1])):
            sampled.extend(rows[:per])
            if len(sampled) >= 80:
                break
        keepers = sampled[:80]
        print(
            f"sampled {len(keepers)} keepers for live C (from intersection)", flush=True
        )
    else:
        print(f"using {len(keepers)} intersection keepers", flush=True)

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.defs import cre_defs as defs
    from application.utils.librarian.candidate_retriever import (
        CandidatePool,
        RetrieverBackend,
        build_retriever,
    )
    from application.utils.librarian.config_loader import load_config
    from application.utils.librarian.envelope_sink import DbEnvelopeSink
    from application.utils.librarian.factory import LibrarianComponents, build_scaler
    from application.utils.librarian.queue_runner import run_librarian_queue
    from application.utils.librarian.schemas import CreCandidate, RetrievalAudit

    db_url = f"sqlite:///{dst.resolve()}"
    database = db_connect(db_url)
    sqla.create_all()

    seeded = _seed_knowledge(sqla.session, run_id, keepers)
    print(f"seeded knowledge_queue={seeded}", flush=True)

    cre_emb = database.get_embeddings_by_doc_type(defs.Credoctypes.CRE.value)
    cre_texts = database.get_embedding_contents_by_doc_type(defs.Credoctypes.CRE.value)
    print(f"CRE hub vectors={len(cre_emb)}", flush=True)

    from application.prompt_client import prompt_client

    ph = prompt_client.PromptHandler(database=database)
    embed_fn = ph.get_text_embeddings

    cfg = load_config()

    pool = CandidatePool.from_mapping(cre_emb)
    retriever = build_retriever(
        RetrieverBackend.in_memory,
        embed_fn=embed_fn,
        top_k=cfg.top_k_retrieval,
        threshold=cfg.link_threshold,
        pool=pool,
        connection=None,
    )

    class _VectorReranker:
        """Sandbox stand-in for CrossEncoder: promote retrieval order with logits."""

        def rerank(self, text: str, audit: RetrievalAudit) -> RetrievalAudit:
            reranked = []
            for i, c in enumerate(audit.candidates[: cfg.top_k_rerank]):
                # High logit for top retrieval hits so temperature scaler can fire.
                score = 12.0 - i * 1.5
                if c.score_vector is not None:
                    score = float(c.score_vector) * 20.0
                reranked.append(
                    CreCandidate(
                        cre_id=c.cre_id, score_rerank=score, score_vector=c.score_vector
                    )
                )
            return audit.model_copy(update={"reranked": reranked})

    components = LibrarianComponents(
        retriever=retriever,
        reranker=_VectorReranker(),
        scaler=build_scaler(cfg),
        known_cre_ids=frozenset(cre_emb.keys()),
        cre_membership=frozenset(cre_emb.keys()),
    )

    sink = DbEnvelopeSink(sqla.session, run_id)
    at = datetime.now(timezone.utc)
    summary = run_librarian_queue(
        sqla.session,
        run_id,
        components,
        cfg,
        at=at,
        sink=sink,
        dry_run=False,
    )
    print(summary.to_json(), flush=True)

    # Report decision_queue + CRE names
    from application.database.db import DecisionQueueItem, KnowledgeQueueItem

    cre_meta = _cre_lookup(sqla.session)
    decisions = (
        sqla.session.query(DecisionQueueItem).filter_by(pipeline_run_id=run_id).all()
    )
    links = []
    reviews = []
    for row in decisions:
        env = row.envelope if isinstance(row.envelope, dict) else {}
        cre_id = None
        if isinstance(env.get("links"), list) and env["links"]:
            cre_id = env["links"][0].get("cre_id")
        if isinstance(env.get("suggested_links"), list) and env["suggested_links"]:
            cre_id = cre_id or env["suggested_links"][0].get("cre_id")
        meta = cre_meta.get(cre_id or "", {})
        entry = {
            "chunk_id": row.chunk_id,
            "status": row.status,
            "reason_code": row.reason_code,
            "confidence": row.confidence,
            "cre_id": cre_id,
            "cre_external_id": meta.get("external_id"),
            "cre_name": meta.get("name"),
            "source_label": row.source_label,
            "text_preview": (
                (env.get("knowledge") or {}).get("text")
                if isinstance(env.get("knowledge"), dict)
                else ""
            )[:160],
        }
        if row.status == "linked":
            links.append(entry)
        else:
            reviews.append(entry)

    consumed = (
        sqla.session.query(KnowledgeQueueItem)
        .filter(
            KnowledgeQueueItem.pipeline_run_id == run_id,
            KnowledgeQueueItem.consumed_at.isnot(None),
        )
        .count()
    )

    report = {
        "run_id": run_id,
        "db": str(dst),
        "summary": json.loads(summary.to_json()),
        "seeded_keepers": seeded,
        "decision_queue_rows": len(decisions),
        "knowledge_consumed": consumed,
        "module_d_handoff": {
            "table": "decision_queue",
            "rows": len(decisions),
            "note": (
                "Module D reads decision_queue envelopes (LinkProposal / ReviewItem). "
                "Graph writes are W8b / Module D — not executed here."
            ),
        },
        "links": links[:60],
        "reviews": reviews[:40],
        "link_count": len(links),
        "review_count": len(reviews),
        "cre_hub_size": len(cre_emb),
        "reranker": "vector_score_stand_in (no sentence-transformers in sandbox)",
        "limitations": [
            "Cross-encoder replaced by vector-score logits — rankings approximate live C.2",
            "NullSafetyGuard → status may be degraded (safety unevaluated)",
            "Sampled intersection keepers if >80",
        ],
    }
    (ART / "module_c_report.json").write_text(json.dumps(report, indent=2) + "\n")

    # Update eval state
    state_path = ART / "state.json"
    if state_path.is_file():
        st = json.loads(state_path.read_text())
        st["phases"]["module_c"] = {
            "status": "ok",
            "detail": (
                f"seeded={seeded} decisions={len(decisions)} "
                f"links≈{len(links)} reviews≈{len(reviews)}"
            ),
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        st["module_c_run_id"] = run_id
        state_path.write_text(json.dumps(st, indent=2) + "\n")

    print(
        json.dumps(
            {
                "seeded": seeded,
                "decisions": len(decisions),
                "links": len(links),
                "reviews": len(reviews),
                "consumed": consumed,
                "report": str(ART / "module_c_report.json"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
