#!/usr/bin/env python3
"""Surgically seed node_facts into document_metadata + re-embed evidence only.

Applies only curated ASVS / MASVS / SAMM / OWASP AI Exchange / CRE facts from
``application.utils.owasp_agent.node_facts``, then re-embeds *only* evidence
URLs. Nest project meta rows are never re-embedded with a facts appendix
(structure answers come from evidence docs, not Nest project cards).

Usage (local DB)::

    python scripts/seed_node_facts.py
    python scripts/seed_node_facts.py --dry-run
    python scripts/seed_node_facts.py --skip-embed

Env: standard Flask/OpenCRE DB URL (same as the running app).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _family_node_names() -> Dict[str, List[str]]:
    """DB Node.name values to match per registry family."""
    return {
        "ASVS": ["ASVS", "OWASP ASVS"],
        "MASVS": ["MASVS", "OWASP MASVS"],
        "SAMM": ["SAMM", "OWASP SAMM"],
        "OWASP AI Exchange": [
            "OWASP AI Exchange",
            "AI Exchange",
            "AIX",
        ],
    }


def _seed_nodes(database: Any, *, dry_run: bool) -> Dict[str, int]:
    from application.database import db as db_mod
    from application.utils.owasp_agent.node_facts import (
        NODE_FACTS_BY_CRE,
        NODE_FACTS_BY_FAMILY,
        merge_facts_into_metadata,
    )
    from sqlalchemy.orm.attributes import flag_modified

    updated_nodes = 0
    updated_cres = 0
    session = database.session

    for family, facts in NODE_FACTS_BY_FAMILY.items():
        names = _family_node_names().get(family, [family])
        seen_ids: Set[int] = set()
        for name in names:
            rows = session.query(db_mod.Node).filter(db_mod.Node.name == name).all()
            # Also match case-insensitive exact when no exact hits.
            if not rows:
                rows = (
                    session.query(db_mod.Node)
                    .filter(db_mod.Node.name.ilike(name))
                    .all()
                )
            for row in rows:
                if row.id in seen_ids:
                    continue
                seen_ids.add(row.id)
                meta = dict(row.metadata_json or {})
                new_meta = merge_facts_into_metadata(meta, facts)
                if new_meta == meta:
                    continue
                print(
                    f"  node id={row.id} name={row.name!r} "
                    f"facts_keys={list(facts.keys())}",
                    flush=True,
                )
                if not dry_run:
                    row.metadata_json = new_meta
                    flag_modified(row, "metadata_json")
                updated_nodes += 1

    for cre_id, facts in NODE_FACTS_BY_CRE.items():
        # CRE.external_id is often NNN-NNN without prefix.
        bare = cre_id.replace("CRE-", "")
        rows = (
            session.query(db_mod.CRE)
            .filter(
                (db_mod.CRE.external_id == cre_id) | (db_mod.CRE.external_id == bare)
            )
            .all()
        )
        for row in rows:
            meta = dict(row.metadata_json or {})
            new_meta = merge_facts_into_metadata(meta, facts)
            if new_meta == meta:
                continue
            print(
                f"  cre id={row.id} external_id={row.external_id!r} "
                f"facts_keys={list(facts.keys())}",
                flush=True,
            )
            if not dry_run:
                row.metadata_json = new_meta
                flag_modified(row, "metadata_json")
            updated_cres += 1

    if not dry_run:
        session.commit()
    return {"nodes": updated_nodes, "cres": updated_cres}


def _require_source_channel_column(database: Any) -> Optional[str]:
    """Return None if embeddings.source_channel exists; else an error message.

    Refuses ad-hoc ALTER — require an Alembic migration / existing column.
    """
    try:
        bind = database.session.get_bind()
        dialect = getattr(getattr(bind, "dialect", None), "name", "") or ""
        if dialect != "postgresql":
            return (
                f"dialect={dialect!r} (need postgresql + "
                "embeddings.source_channel / pgvector)"
            )
        from sqlalchemy import inspect

        cols = {c["name"] for c in inspect(bind).get_columns("embeddings")}
        if "source_channel" not in cols:
            return (
                "embeddings.source_channel is missing. "
                "Run Alembic migrations (make migrate-upgrade) — "
                "this script will not ALTER TABLE."
            )
    except Exception as exc:
        return f"cannot inspect bind ({exc})"
    return None


def _reembed_evidence(
    database: Any, *, dry_run: bool, skip_embed: bool
) -> Dict[str, int]:
    if skip_embed:
        return {"evidence": 0}
    err = _require_source_channel_column(database)
    if err:
        print(f"  skip embed: {err}", flush=True)
        return {"evidence": 0, "skipped_reason": err}

    from application.prompt_client import prompt_client
    from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT
    from application.utils.owasp_agent.meta_embeddings import (
        DOC_TYPE_EVIDENCE,
        evidence_documents,
        evidence_url,
        upsert_channel_embedding,
    )

    handler = prompt_client.PromptHandler(database, load_all_embeddings=False)

    def _embed(text: str):
        return handler.get_text_embeddings(text)

    evidence_n = 0
    for slug, embed_text, citations in evidence_documents():
        url = evidence_url(slug)
        body = embed_text
        if citations:
            body += "\n\nCitations: " + ", ".join(citations)
        print(f"  evidence {url}", flush=True)
        if not dry_run:
            vec = list(_embed(body))
            upsert_channel_embedding(
                database,
                source_channel=CHANNEL_AGENT,
                doc_type=DOC_TYPE_EVIDENCE,
                embeddings_url=url,
                embedding_text=body,
                embeddings=vec,
            )
        evidence_n += 1

    # Intentionally do not re-embed Nest project meta with facts appendix —
    # that boosts Nest similarity for structure asks (Nest-steal).
    return {"evidence": evidence_n}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing DB / embeddings",
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="Only merge metadata.facts; do not re-embed",
    )
    args = parser.parse_args(argv)

    os.environ.setdefault("FLASK_ENV", "development")
    from application import create_app
    from application.database import db as db_mod

    app = create_app(mode="production")
    with app.app_context():
        database = db_mod.Node_collection()
        print("Seeding node metadata.facts …", flush=True)
        counts = _seed_nodes(database, dry_run=args.dry_run)
        print(f"metadata updated: {counts}", flush=True)
        print("Re-embedding evidence for node_facts …", flush=True)
        emb = _reembed_evidence(
            database, dry_run=args.dry_run, skip_embed=args.skip_embed
        )
        print(f"embeddings upserted: {emb}", flush=True)
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
