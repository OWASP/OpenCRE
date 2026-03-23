#!/usr/bin/env python3
"""
Temporary utility:
1) Imports all external projects into a fresh sqlite DB, but with NO embeddings generation
   and NO gap-analysis scheduling.
2) Copies that sqlite DB to a backup file.
3) Runs the upstream sync (downloads the CRE graph from upstream into the same sqlite DB).
4) Compares the two sqlite DBs and prints:
   - Structural changes: added/removed CREs, nodes, and links (graph edges).
   - Content changes: CRE/node field diffs and embedding diffs.

This script is intentionally "small and blunt" and may need tweaks depending on your
environment variables (Google creds, upstream connectivity, etc.).
"""

from __future__ import annotations

import argparse
import json
import os
import importlib
import pkgutil
import shutil
import sqlite3
import sys
import tempfile
import urllib.parse
import re
import uuid
from collections import defaultdict
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    # Optional: the diff utility should still work in minimal environments.
    from dotenv import load_dotenv  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    def load_dotenv(*args: Any, **kwargs: Any) -> None:  # type: ignore
        return None


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _json_canonical(v: Any) -> Any:
    """
    Convert JSON-ish values to a canonical string so diffs are stable.
    Returns None for null-like values.
    """

    if v is None:
        return None
    if isinstance(v, str):
        if not v:
            return ""
        try:
            parsed = json.loads(v)
        except Exception:
            return v
        return json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    # sqlite sometimes returns bytes for JSON columns
    if isinstance(v, (bytes, bytearray)):
        try:
            return _json_canonical(v.decode("utf-8"))
        except Exception:
            return str(v)
    return v


def _normalize_tags(v: Any) -> Any:
    """
    Database `tags` are stored as a comma-separated string.
    For diff stability we normalize into a sorted list of trimmed tags.
    """
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        parts = [str(x).strip() for x in v if str(x).strip()]
        return sorted(parts)
    if isinstance(v, (bytes, bytearray)):
        try:
            v = v.decode("utf-8")
        except Exception:
            return [str(v)]
    if not isinstance(v, str):
        return [str(v)]
    if not v:
        return []
    parts = [p.strip() for p in v.split(",")]
    return sorted([p for p in parts if p])


def _normalize_dsomm_activity_description_url(url: str) -> str:
    """
    DSOMM has historically used either:
      - activity-description?uuid=<id>
      - activity-description?action=<id>
    To reduce diff noise, normalize both to the canonical ?uuid=<id> form.
    """
    if "dsomm.owasp.org/activity-description" not in url:
        return url
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname != "dsomm.owasp.org" or parsed.path != "/activity-description":
            return url
        qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if "action" in qs:
            action_vals = qs.get("action") or []
            qs.pop("action", None)
            # Only map if uuid isn't present already.
            if "uuid" not in qs and action_vals:
                qs["uuid"] = action_vals
        if "action" in qs:
            qs.pop("action", None)
        # parse_qs returns lists; urlencode with doseq preserves that.
        new_query = urllib.parse.urlencode(qs, doseq=True)
        normalized = urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
        )
        return normalized
    except Exception:
        return url


def _normalize_link(v: Any) -> Any:
    if isinstance(v, str):
        return _normalize_dsomm_activity_description_url(v)
    return v


def _strip_embeddings_from_document(document: Any) -> None:
    """
    Removes embeddings from CRE/Standard/Code/Tool docs produced by parsers.
    This is important because register_standard/register_node may persist embeddings
    into the sqlite `embeddings` table if the doc already contains embeddings.
    """

    # defs.Document dataclass has: embeddings, embeddings_text, links
    if document is None:
        return
    if hasattr(document, "embeddings"):
        document.embeddings = []
    if hasattr(document, "embeddings_text"):
        document.embeddings_text = ""
    if hasattr(document, "links") and document.links:
        for l in document.links:
            if hasattr(l, "document"):
                _strip_embeddings_from_document(l.document)


def _strip_embeddings_from_documents(documents: Iterable[Any]) -> None:
    for doc in documents:
        _strip_embeddings_from_document(doc)


def _connect_sqlite(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_all(conn: sqlite3.Connection, query: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
    cur = conn.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def _embedding_semantic_doc_ref(r: sqlite3.Row) -> Tuple[str, ...]:
    """
    Build a stable document reference for embeddings validation that does not depend
    on local DB UUIDs. Prefer CRE external_id / node identifying fields; fall back
    to raw ids only when no joined document exists.
    """
    if r["cre_external_id"]:
        return (
            "cre",
            str(r["cre_external_id"] or ""),
            str(r["cre_name"] or ""),
        )
    if r["node_name"] or r["node_section_id"] or r["node_section"]:
        return (
            "node",
            str(r["node_ntype"] or ""),
            str(r["node_name"] or ""),
            str(r["node_section_id"] or ""),
            str(r["node_section"] or ""),
            str(r["node_subsection"] or ""),
            str(r["node_version"] or ""),
            str(r["node_link"] or ""),
        )
    return (
        "orphan",
        str(r["doc_type"] or ""),
        str(r["cre_id"] or ""),
        str(r["node_id"] or ""),
    )


def _embedding_semantic_key(r: sqlite3.Row) -> Tuple[str, ...]:
    # Use a stable identity key for verification:
    # - doc_type + document reference + URL
    # Excluding embeddings_content avoids false negatives caused by crawler/content
    # formatting differences (escaped newlines, whitespace, upstream page drift).
    return (
        str(r["doc_type"] or ""),
        *_embedding_semantic_doc_ref(r),
        str(r["embeddings_url"] or ""),
    )


def _load_embedding_rows(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return _fetch_all(
        conn,
        """
        SELECT
          e.rowid AS row_id,
          e.doc_type,
          e.cre_id,
          e.node_id,
          e.embeddings,
          e.embeddings_url,
          e.embeddings_content,
          n.name AS node_name,
          n.section_id AS node_section_id,
          n.section AS node_section,
          n.subsection AS node_subsection,
          n.version AS node_version,
          n.ntype AS node_ntype,
          n.link AS node_link,
          c.external_id AS cre_external_id,
          c.name AS cre_name
        FROM embeddings e
        LEFT JOIN node n ON e.node_id = n.id
        LEFT JOIN cre c ON e.cre_id = c.id
        ORDER BY e.doc_type, e.embeddings_url, e.embeddings_content, e.cre_id, e.node_id
        """,
    )


def _snapshot_embeddings(
    conn: sqlite3.Connection,
) -> Dict[Tuple[str, ...], Set[str]]:
    rows = _load_embedding_rows(conn)
    out: Dict[Tuple[str, ...], Set[str]] = defaultdict(set)
    for r in rows:
        out[_embedding_semantic_key(r)].add(str(r["embeddings"] or ""))
    return out


def _snapshot_gap_analysis(conn: sqlite3.Connection) -> Dict[str, str]:
    rows = _fetch_all(
        conn,
        """
        SELECT cache_key, ga_object
        FROM gap_analysis_results
        ORDER BY cache_key
        """,
    )
    return {str(r["cache_key"]): str(r["ga_object"]) for r in rows}


def _delete_every_n_embeddings(
    conn: sqlite3.Connection,
    *,
    every_n: int,
    doc_types_to_delete: Optional[Set[str]] = None,
) -> Set[Tuple[str, ...]]:
    if every_n <= 0:
        raise ValueError("--delete-every-n must be > 0")
    rows = _load_embedding_rows(conn)
    deleted: Set[Tuple[str, ...]] = set()
    eligible_idx = 0
    for r in rows:
        doc_type = str(r["doc_type"] or "")
        if doc_types_to_delete is not None and doc_type not in doc_types_to_delete:
            continue
        eligible_idx += 1
        if eligible_idx % every_n != 0:
            continue
        conn.execute("DELETE FROM embeddings WHERE rowid = ?", (r["row_id"],))
        deleted.add(_embedding_semantic_key(r))
    conn.commit()
    return deleted


def _delete_every_n_gap_analysis(conn: sqlite3.Connection, *, every_n: int) -> Set[str]:
    if every_n <= 0:
        raise ValueError("--delete-every-n must be > 0")
    rows = _fetch_all(
        conn,
        """
        SELECT cache_key
        FROM gap_analysis_results
        ORDER BY cache_key
        """,
    )
    deleted: Set[str] = set()
    for idx, r in enumerate(rows, start=1):
        if idx % every_n != 0:
            continue
        cache_key = str(r["cache_key"])
        conn.execute("DELETE FROM gap_analysis_results WHERE cache_key = ?", (cache_key,))
        deleted.add(cache_key)
    conn.commit()
    return deleted


def verify_checkpoint_2_incremental(
    *,
    db_path: str,
    delete_every_n: int,
    verify_gap_analysis: bool,
) -> None:
    """
    Checkpoint 2 verification:
    - delete every Nth embeddings row
    - regenerate embeddings
    - assert only missing keys are recreated and untouched rows stay byte-equal
    - optionally do the same delete/refill verification for gap_analysis_results
    """
    from application.cmd import cre_main
    from application.defs import cre_defs
    from application.prompt_client import prompt_client as prompt_client
    from application import sqla
    from application.database.db import gap_analysis as db_gap_analysis
    from neomodel import db as neo4j_db
    from application.prompt_client.prompt_client import normalize_embeddings_content

    # Do not force-disable graph backends here.
    # If callers want a no-Neo4j run they can set NO_LOAD_GRAPH_DB/CRE_NO_NEO4J
    # explicitly. For GA verification runs, we must allow neo_db to initialize.
    # Keep embedding generation enabled in this verification mode.
    os.environ.pop("CRE_NO_GEN_EMBEDDINGS", None)

    collection = cre_main.db_connect(path=db_path)
    sqla.create_all()
    prompt_handler = prompt_client.PromptHandler(database=collection)

    with _connect_sqlite(db_path) as conn:
        emb_before = _snapshot_embeddings(conn)
        ga_before = _snapshot_gap_analysis(conn) if verify_gap_analysis else {}

    if not emb_before:
        raise RuntimeError(
            "No embeddings rows found. Import/fill embeddings first, then re-run with --verify-checkpoint-2-incremental."
        )

    with _connect_sqlite(db_path) as conn:
        # This verification mode should focus on incremental embeddings for
        # Standard nodes. CRE embeddings should not be regenerated here because
        # they are stable across these import checkpoints.
        emb_deleted = _delete_every_n_embeddings(
            conn,
            every_n=delete_every_n,
            doc_types_to_delete={cre_defs.Credoctypes.Standard.value},
        )
        ga_deleted: Set[str] = set()
        if verify_gap_analysis:
            ga_deleted = _delete_every_n_gap_analysis(conn, every_n=delete_every_n)

    print(
        f"Checkpoint 2 setup complete: deleted {len(emb_deleted)} embedding rows "
        f"(every {delete_every_n}th)."
    )
    if verify_gap_analysis:
        print(
            f"Checkpoint 2 setup complete: deleted {len(ga_deleted)} gap-analysis cache rows "
            f"(every {delete_every_n}th)."
        )

    # Refill embeddings via normal prompt handler flow (Standard nodes only).
    for standard_name in collection.standards():
        prompt_handler.generate_embeddings_for(standard_name)

    # Optional GA refill. This path is intentionally direct (non-RQ) for determinism in checkpoint runs.
    ga_refill_performed = False
    if verify_gap_analysis and ga_deleted:
        database_with_graph = collection.with_graph()
        ga_engine = getattr(database_with_graph, "neo_db", None)
        if ga_engine is None:
            # In local verification runs we often set NO_LOAD_GRAPH_DB=1, which means
            # no neo_db is available for GA recomputation. Skip GA refill gracefully.
            print(
                "WARNING: skipping GA refill verification because no neo_db engine is available "
                "(NO_LOAD_GRAPH_DB/CRE_NO_NEO4J may be enabled)."
            )
        else:
            ga_refill_performed = True
            # Ensure deterministic GA verification against the current sqlite DB.
            # Neo4j can contain stale/orphan nodes from previous runs; rebuild from scratch.
            neo4j_db.cypher_query("MATCH (n) DETACH DELETE n")
            cre_main.populate_neo4j_db(db_path)
            parsed_pairs: Set[Tuple[str, str]] = set()
            for cache_key in ga_deleted:
                if " >> " not in cache_key:
                    continue
                parts = cache_key.split(" >> ")
                if len(parts) != 2:
                    continue
                parsed_pairs.add((parts[0], parts[1]))
            for standard_a, standard_b in sorted(parsed_pairs):
                db_gap_analysis(
                    neo_db=ga_engine,
                    node_names=[standard_a, standard_b],
                    cache_key=f"{standard_a} >> {standard_b}",
                )

    with _connect_sqlite(db_path) as conn:
        emb_after = _snapshot_embeddings(conn)
        ga_after = _snapshot_gap_analysis(conn) if verify_gap_analysis else {}

    missing_after = sorted(set(emb_before.keys()) - set(emb_after.keys()))
    if missing_after:
        raise AssertionError(f"Missing embedding keys after refill: {missing_after[:10]}")

    unexpected_after = sorted(set(emb_after.keys()) - set(emb_before.keys()))
    if unexpected_after:
        # Pre-existing missing embeddings (e.g. from Heroku import skips) get backfilled
        # during refill. We enforce exact restoration of deleted keys, not global parity.
        print(
            "NOTE: refill generated additional embeddings (pre-existing gaps): "
            f"{len(unexpected_after)} extra keys"
        )

    restored_embeddings = len(set(emb_deleted) & set(emb_after.keys()))
    if restored_embeddings != len(emb_deleted):
        raise AssertionError(
            "Embeddings refill count mismatch: "
            f"deleted={len(emb_deleted)} restored={restored_embeddings}"
        )

    untouched = set(emb_before.keys()) - emb_deleted
    # Skip mutation check for URL-backed embeddings: upstream page content can change
    # between export and refill, so recomputation is expected.
    def _is_url_backed(key: Tuple[str, ...]) -> bool:
        url = key[-1] if key else ""
        return isinstance(url, str) and url.startswith("http")
    mutated_untouched = [
        k for k in sorted(untouched)
        if not _is_url_backed(k) and emb_before[k] != emb_after.get(k)
    ]
    if mutated_untouched:
        raise AssertionError(
            "Unchanged embeddings were mutated; incremental skip likely regressed. "
            f"Examples: {mutated_untouched[:10]}"
        )

    if verify_gap_analysis and ga_before and ga_refill_performed:
        missing_ga_after = sorted(set(ga_before.keys()) - set(ga_after.keys()))
        if missing_ga_after:
            raise AssertionError(f"Missing GA cache keys after refill: {missing_ga_after[:10]}")

        unexpected_ga_after = sorted(set(ga_after.keys()) - set(ga_before.keys()))
        if unexpected_ga_after:
            raise AssertionError(f"Unexpected new GA cache keys after refill: {unexpected_ga_after[:10]}")

        untouched_ga = set(ga_before.keys()) - ga_deleted
        mutated_ga_untouched = [k for k in sorted(untouched_ga) if ga_before[k] != ga_after.get(k)]
        if mutated_ga_untouched:
            raise AssertionError(
                "Untouched GA cache rows were mutated; incremental skip likely regressed. "
                f"Examples: {mutated_ga_untouched[:10]}"
            )

        restored_ga = len(set(ga_deleted) & set(ga_after.keys()))
        if restored_ga != len(ga_deleted):
            raise AssertionError(
                "GA refill count mismatch: "
                f"deleted={len(ga_deleted)} restored={restored_ga}"
            )

        # Refilled GA must match upstream exactly (deterministic recomputation).
        mismatched_ga = [
            k for k in sorted(ga_deleted)
            if ga_after.get(k) != ga_before.get(k)
        ]
        if mismatched_ga:
            raise AssertionError(
                "Refilled GA results differ from upstream; recomputation not deterministic. "
                f"Examples: {mismatched_ga[:10]}"
            )

    # Verify embedding recalculation for a controlled content change.
    with _connect_sqlite(db_path) as conn:
        candidate = _fetch_all(
            conn,
            """
            SELECT e.node_id, n.name, n.section, e.embeddings_content, e.embeddings
            FROM embeddings e
            JOIN node n ON n.id = e.node_id
            WHERE e.doc_type = ?
              AND COALESCE(n.link, '') = ''
            LIMIT 1
            """,
            (cre_defs.Credoctypes.Standard.value,),
        )
        if candidate:
            row = candidate[0]
            node_id = str(row["node_id"])
            standard_name = str(row["name"])
            old_embeddings_content = str(row["embeddings_content"] or "")
            old_embeddings_value = str(row["embeddings"] or "")
            old_section = str(row["section"] or "")
            marker = "__checkpoint2_content_change__"
            conn.execute(
                "UPDATE node SET section = ? WHERE id = ?",
                (f"{old_section} {marker}".strip(), node_id),
            )
            conn.commit()
            print(
                f"Checkpoint 2 content-change probe: updated node {node_id} "
                f"for standard '{standard_name}'"
            )
            # Recompute only the changed node id.
            prompt_handler.embeddings_instance.generate_embeddings(collection, [node_id])
            refreshed = _fetch_all(
                conn,
                "SELECT embeddings, embeddings_content FROM embeddings WHERE node_id = ?",
                (node_id,),
            )
            if not refreshed:
                raise AssertionError(
                    f"Content-change probe failed: no embedding row found for node {node_id}"
                )
            new_embeddings_value = str(refreshed[0]["embeddings"] or "")
            new_embeddings_content = str(refreshed[0]["embeddings_content"] or "")
            if normalize_embeddings_content(old_embeddings_content) == normalize_embeddings_content(
                new_embeddings_content
            ):
                raise AssertionError(
                    "Content-change probe failed: embeddings_content did not change after node content update"
                )
            if old_embeddings_value == new_embeddings_value:
                raise AssertionError(
                    "Content-change probe failed: embedding vector did not change after node content update"
                )
        else:
            print(
                "WARNING: no standard embedding candidate with empty link found; "
                "skipping content-change recalculation probe."
            )

    # Verify GA recalculation for a controlled graph-structure change.
    if verify_gap_analysis and ga_refill_performed and ga_after:
        pair_key = next((k for k in sorted(ga_after.keys()) if " >> " in k), None)
        if pair_key:
            a, b = pair_key.split(" >> ", 1)
            with _connect_sqlite(db_path) as conn:
                before_probe_rows = _fetch_all(
                    conn,
                    "SELECT ga_object FROM gap_analysis_results WHERE cache_key = ?",
                    (pair_key,),
                )
                if before_probe_rows:
                    before_probe = str(before_probe_rows[0]["ga_object"] or "")
                    # Force recomputation on the target key.
                    conn.execute("DELETE FROM gap_analysis_results WHERE cache_key = ?", (pair_key,))
                    conn.commit()
                    tmp_doc_id = f"checkpoint2-{uuid.uuid4()}"
                    tmp_external = "999-999"
                    neo4j_db.cypher_query(
                        """
                        MATCH (s1:NeoStandard {name: $s1}), (s2:NeoStandard {name: $s2})
                        CREATE (tmp:NeoCRE {
                          name: $tmp_name,
                          doctype: 'CRE',
                          document_id: $tmp_doc_id,
                          external_id: $tmp_external,
                          description: 'checkpoint2 temporary structure probe',
                          tags: []
                        })
                        MERGE (tmp)-[:LINKED_TO]->(s1)
                        MERGE (tmp)-[:LINKED_TO]->(s2)
                        """,
                        {
                            "s1": a,
                            "s2": b,
                            "tmp_name": "__checkpoint2_tmp_cre__",
                            "tmp_doc_id": tmp_doc_id,
                            "tmp_external": tmp_external,
                        },
                    )
                    try:
                        db_gap_analysis(neo_db=ga_engine, node_names=[a, b], cache_key=pair_key)
                        after_probe_rows = _fetch_all(
                            conn,
                            "SELECT ga_object FROM gap_analysis_results WHERE cache_key = ?",
                            (pair_key,),
                        )
                        if not after_probe_rows:
                            raise AssertionError(
                                f"GA structure-change probe failed: key {pair_key} was not regenerated"
                            )
                        after_probe = str(after_probe_rows[0]["ga_object"] or "")
                        if before_probe == after_probe:
                            raise AssertionError(
                                "GA structure-change probe failed: GA result did not change "
                                "after a controlled graph-structure mutation"
                            )
                    finally:
                        neo4j_db.cypher_query(
                            "MATCH (n:NeoCRE {document_id: $doc_id}) DETACH DELETE n",
                            {"doc_id": tmp_doc_id},
                        )

    print("Checkpoint 2 incremental verification passed.")
    print(f"  Embeddings before: {len(emb_before)}")
    print(f"  Embeddings deleted: {len(emb_deleted)}")
    print(f"  Embeddings after: {len(emb_after)}")
    if verify_gap_analysis and ga_refill_performed:
        print(f"  GA cache before: {len(ga_before)}")
        print(f"  GA cache deleted: {len(ga_deleted)}")
        print(f"  GA cache after: {len(ga_after)}")
def compare_databases(backup_db: str, new_db: str, max_items: int) -> None:
    backup = _connect_sqlite(backup_db)
    new = _connect_sqlite(new_db)

    # ---- Load CREs ----
    def load_cres(db: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
        """
        Key by stable CRE id. This avoids false "added/removed" diffs when
        only human-readable fields (name/external_id) change.
        """
        content_by_id: Dict[str, Dict[str, Any]] = {}
        rows = _fetch_all(
            db,
            "SELECT id, name, external_id, description, tags, document_metadata FROM cre",
        )
        for r in rows:
            content_by_id[r["id"]] = {
                "id": r["id"],
                "name": r["name"],
                "external_id": r["external_id"],
                "description": r["description"],
                "tags": _normalize_tags(r["tags"]),
                "document_metadata": _json_canonical(r["document_metadata"]),
            }
        return content_by_id

    b_cre_content = load_cres(backup)
    n_cre_content = load_cres(new)

    b_cre_ids: Set[str] = set(b_cre_content.keys())
    n_cre_ids: Set[str] = set(n_cre_content.keys())

    added_cre = sorted(n_cre_ids - b_cre_ids)
    removed_cre = sorted(b_cre_ids - n_cre_ids)

    changed_cre: List[Tuple[str, Dict[str, Any]]] = []
    for cre_id in sorted(b_cre_ids & n_cre_ids):
        b = b_cre_content[cre_id]
        n = n_cre_content[cre_id]
        diffs: Dict[str, Any] = {}
        for field in ["name", "external_id", "description", "tags", "document_metadata"]:
            if _json_canonical(b.get(field)) != _json_canonical(n.get(field)):
                diffs[field] = {"before": b.get(field), "after": n.get(field)}
        if diffs:
            changed_cre.append((cre_id, diffs))

    # ---- Load Nodes ----
    def load_nodes(db: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
        """
        Key by stable node id. This avoids false "added/removed" diffs when
        only human-readable fields change.
        """
        content_by_id: Dict[str, Dict[str, Any]] = {}
        rows = _fetch_all(
            db,
            """
            SELECT
              id, name, section, subsection, version, section_id,
              description, tags, ntype, link, document_metadata
            FROM node
            """,
        )
        for r in rows:
            content_by_id[r["id"]] = {
                "id": r["id"],
                "name": r["name"],
                "section": r["section"],
                "subsection": r["subsection"],
                "version": r["version"],
                "section_id": r["section_id"],
                "description": r["description"],
                "tags": _normalize_tags(r["tags"]),
                "ntype": r["ntype"],
                "link": r["link"],
                "document_metadata": _json_canonical(r["document_metadata"]),
            }
        return content_by_id

    b_node_content = load_nodes(backup)
    n_node_content = load_nodes(new)

    b_node_ids: Set[str] = set(b_node_content.keys())
    n_node_ids: Set[str] = set(n_node_content.keys())

    added_nodes = sorted(n_node_ids - b_node_ids)
    removed_nodes = sorted(b_node_ids - n_node_ids)

    changed_nodes: List[Tuple[str, Dict[str, Any]]] = []
    for node_id in sorted(b_node_ids & n_node_ids):
        b = b_node_content[node_id]
        n = n_node_content[node_id]
        diffs: Dict[str, Any] = {}
        for field in [
            "name",
            "section",
            "subsection",
            "version",
            "section_id",
            "description",
            "tags",
            "ntype",
            "link",
            "document_metadata",
        ]:
            b_val = b.get(field)
            n_val = n.get(field)
            if field == "link":
                b_val = _normalize_link(b_val)
                n_val = _normalize_link(n_val)
            if _json_canonical(b_val) != _json_canonical(n_val):
                diffs[field] = {"before": b.get(field), "after": n.get(field)}
        if diffs:
            changed_nodes.append((node_id, diffs))

    # ---- Load links (structural) ----
    def load_internal_edges(db: sqlite3.Connection) -> Set[Tuple[str, str, str]]:
        rows = _fetch_all(db, "SELECT type, \"group\" as group_id, cre as cre_id FROM cre_links")
        out: Set[Tuple[str, str, str]] = set()
        for r in rows:
            out.add((
                r["type"],
                str(r["group_id"]),
                str(r["cre_id"]),
            ))
        return out

    def load_external_edges(
        db: sqlite3.Connection,
    ) -> Set[Tuple[str, str, str]]:
        rows = _fetch_all(db, "SELECT type, cre as cre_id, node as node_id FROM cre_node_links")
        out: Set[Tuple[str, str, str]] = set()
        for r in rows:
            out.add((
                r["type"],
                str(r["cre_id"]),
                str(r["node_id"]),
            ))
        return out

    b_internal = load_internal_edges(backup)
    n_internal = load_internal_edges(new)

    added_internal_edges = sorted(n_internal - b_internal)
    removed_internal_edges = sorted(b_internal - n_internal)

    b_external = load_external_edges(backup)
    n_external = load_external_edges(new)

    added_external_edges = sorted(n_external - b_external)
    removed_external_edges = sorted(b_external - n_external)

    # ---- Embeddings diff (content changes) ----
    def load_embeddings(
        db: sqlite3.Connection,
    ) -> Dict[Tuple[str, Optional[str], Optional[str]], Set[Tuple[str, str, str]]]:
        """
        Returns:
          embeddings_by_doc_key[(doc_type, cre_key?, node_key?)] -> set of (embeddings, embeddings_url, embeddings_content)
        """

        rows = _fetch_all(
            db,
            """
            SELECT embeddings, doc_type, cre_id, node_id, embeddings_url, embeddings_content
            FROM embeddings
            """,
        )
        out: Dict[Tuple[str, Optional[str], Optional[str]], Set[Tuple[str, str, str]]] = defaultdict(set)
        for r in rows:
            cre_id = r["cre_id"]
            node_id = r["node_id"]
            doc_key = (
                r["doc_type"],
                None if not cre_id else str(cre_id),
                None if not node_id else str(node_id),
            )
            out[doc_key].add((r["embeddings"], r["embeddings_url"], r["embeddings_content"]))
        return out

    b_emb = load_embeddings(backup)
    n_emb = load_embeddings(new)

    b_emb_keys = set(b_emb.keys())
    n_emb_keys = set(n_emb.keys())
    added_emb_keys = sorted(n_emb_keys - b_emb_keys)
    removed_emb_keys = sorted(b_emb_keys - n_emb_keys)

    changed_emb: List[Tuple[str, Dict[str, Any]]] = []
    for k in sorted(b_emb_keys & n_emb_keys):
        if b_emb[k] != n_emb[k]:
            before = b_emb[k]
            after = n_emb[k]
            added = after - before
            removed = before - after

            def _tuple_summary(t: Tuple[str, str, str]) -> Dict[str, Any]:
                emb, url, content = t
                return {
                    "embeddings_url": url,
                    "embeddings_content": (content[:200] if isinstance(content, str) else str(content)),
                    "embeddings_prefix": (emb[:50] if isinstance(emb, str) else str(emb)),
                }

            changed_emb.append(
                (
                    str(k),
                    {
                        "before_count": len(before),
                        "after_count": len(after),
                        "added_count": len(added),
                        "removed_count": len(removed),
                        "added_examples": [_tuple_summary(x) for x in sorted(added)[: min(3, max_items)]],
                        "removed_examples": [_tuple_summary(x) for x in sorted(removed)[: min(3, max_items)]],
                    },
                )
            )

    def _print_limited(title: str, items: List[Any], indent: str = "  ") -> None:
        print(title)
        if not items:
            print(indent + "(none)")
            return
        for x in items[:max_items]:
            print(indent + str(x))
        if len(items) > max_items:
            print(indent + f"... ({len(items) - max_items} more)")

    # ---- Print report ----
    print("=== Structural Changes ===")
    _print_limited("CRE added:", added_cre)
    _print_limited("CRE removed:", removed_cre)
    _print_limited("Node added:", added_nodes)
    _print_limited("Node removed:", removed_nodes)

    _print_limited(
        "Internal edges added: (type, higher_group_cre, lower_cre)",
        [str(x) for x in added_internal_edges],
    )
    _print_limited(
        "Internal edges removed: (type, higher_group_cre, lower_cre)",
        [str(x) for x in removed_internal_edges],
    )
    _print_limited(
        "External edges added: (type, cre, node)",
        [str(x) for x in added_external_edges],
    )
    _print_limited(
        "External edges removed: (type, cre, node)",
        [str(x) for x in removed_external_edges],
    )

    print("\n=== Content Changes ===")
    _print_limited(
        "CRE changed fields: (cre_key -> diffs)",
        [f"{k}: {d}" for k, d in changed_cre],
    )
    _print_limited(
        "Node changed fields: (node_key -> diffs)",
        [f"{k}: {d}" for k, d in changed_nodes],
    )
    _print_limited("Embeddings keys added:", added_emb_keys)
    _print_limited("Embeddings keys removed:", removed_emb_keys)
    _print_limited("Embeddings keys changed:", [str(x) for x in changed_emb])

    backup.close()
    new.close()


def run_import_only(db_path: str, *, overwrite: bool) -> None:
    """
    Runs importers sequentially (no rq workers) and forces:
      - calculate_gap_analysis=False
      - generate_embeddings=False
    Then strips any pre-attached embeddings in parsed docs before persisting.
    """

    # Important: avoid neo4j connections (memory graph only).
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    os.environ.setdefault("CRE_NO_NEO4J", "1")

    # Force no embeddings generation / no gap-analysis scheduling in register_standard.
    os.environ.setdefault("CRE_NO_GEN_EMBEDDINGS", "1")
    os.environ.setdefault("CRE_NO_CALCULATE_GAP_ANALYSIS", "1")

    # Create a fresh DB schema.
    from application import sqla
    from application.cmd import cre_main
    from application.database import db as db_models
    from application.prompt_client import prompt_client as prompt_client
    from application.utils.external_project_parsers import base_parser_defs
    from application.utils.external_project_parsers import parsers as parsers_pkg  # type: ignore

    if os.path.exists(db_path) and overwrite:
        os.remove(db_path)
    if os.path.exists(db_path) and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing sqlite db at {db_path}. "
            f"Pass --overwrite to allow it."
        )

    collection = cre_main.db_connect(path=db_path)
    sqla.create_all()

    prompt_handler = prompt_client.PromptHandler(database=collection)

    # Optional: import the core (main OpenCRE) spreadsheet first, so standards
    # already have CRE links before external parsers try to resolve/link them.
    #
    # This mimics `python cre.py --add --from_spreadsheet <url>` but avoids the RQ
    # worker dependency by importing sequentially from the spreadsheet parser.
    if os.environ.get("OPENCRE_IMPORT_CORE", "").lower() in {"1", "true", "yes"}:
        run_import_core_sequential(
            db_path=db_path,
            core_spreadsheet_url=os.environ.get(
                "OPENCRE_CORE_SPREADSHEET_URL",
                "https://docs.google.com/spreadsheets/d/1eZOEYgts7d_-Dr-1oAbogPfzBLh6511b58pX3b59kvg",
            ),
        )

        # AI-dependent parsers (Cloud Native Security Controls / PCI DSS / Juice Shop)
        # need CRE embeddings already present in the DB so they can map text->CRE
        # using cosine similarity. We generate embeddings for CRE only.
        try:
            from application.defs import cre_defs as cre_defs

            with _connect_sqlite(db_path) as c:
                cre_emb_count = int(
                    c.execute(
                        "SELECT COUNT(*) FROM embeddings WHERE doc_type = ?",
                        (cre_defs.Credoctypes.CRE.value,),
                    ).fetchone()[0]
                )
            if cre_emb_count == 0:
                print("Generating CRE embeddings (needed for AI-based linking)...")
                prompt_handler.generate_embeddings_for(cre_defs.Credoctypes.CRE.value)
        except Exception as e:
            raise RuntimeError(
                f"Failed to prepare CRE embeddings required by AI-based parsers: {e}"
            )

    # Import all parser modules so `ParserInterface.__subclasses__()` is populated.
    # The project parsers live under `application.utils.external_project_parsers.parsers.*`.
    for mod in pkgutil.iter_modules(parsers_pkg.__path__):  # type: ignore[attr-defined]
        importlib.import_module(f"{parsers_pkg.__name__}.{mod.name}")

    # Import everything by reflection.
    importers = list(base_parser_defs.ParserInterface.__subclasses__())
    if not importers:
        raise RuntimeError("No external parsers found (ParserInterface subclasses empty).")

    # Enforce basic dependency order:
    # - CAPEC links to CWE nodes, so import CWE first.
    priority_by_name = {
        "CWE": 0,
        "CAPEC": 1,
    }

    def _priority(cls: Any) -> int:
        nm = getattr(cls, "name", None)
        if nm in priority_by_name:
            return priority_by_name[nm]
        return 10

    importers.sort(key=_priority)

    for importer_cls in importers:
        # This parser is present in the tree but intentionally not wired to a concrete source.
        if getattr(importer_cls, "__name__", "") == "MasterSpreadsheetParser":
            continue

        importer = importer_cls()
        print(f"Importing: {getattr(importer, 'name', importer_cls.__name__)}")
        result = importer.parse(collection, prompt_handler)

        # Force both knobs off regardless of parser defaults.
        for _, documents in (result.results or {}).items():
            # Strip any pre-attached embeddings from parsed docs.
            _strip_embeddings_from_documents(documents)
            cre_main.register_standard(
                standard_entries=documents,
                db_connection_str=db_path,
                calculate_gap_analysis=False,
                generate_embeddings=False,
                collection=collection,
            )


def run_upstream_sync(db_path: str) -> None:
    # Avoid neo4j connections; upstream sync uses memory graph.
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")
    os.environ.setdefault("CRE_NO_NEO4J", "1")
    from application.cmd import cre_main

    print(f"Running upstream sync into: {db_path}")
    cre_main.download_graph_from_upstream(db_path)


def run_import_core_sequential(*, db_path: str, core_spreadsheet_url: str) -> None:
    """
    Sequentially imports the main (core) OpenCRE spreadsheet into `db_path`.

    Why sequential:
    `cre_main.add_from_spreadsheet()` uses RQ to enqueue `register_standard()`,
    which requires external workers. For this diff utility, we want to be
    self-contained.
    """
    from application.utils import spreadsheet as sheet_utils
    from application.utils.external_project_parsers.parsers import (
        master_spreadsheet_parser,
    )
    from application.defs import cre_defs
    from application.cmd import cre_main

    print(f"Importing core spreadsheet: {core_spreadsheet_url}")

    # Default to Service Account auth for gspread to avoid OAuth refresh
    # errors like: `google.auth.exceptions.RefreshError: invalid_grant`.
    # (Your `make import-all` workflow exports `OpenCRE_gspread_Auth=service_account`.)
    os.environ.setdefault("OpenCRE_gspread_Auth", "service_account")

    # Read the spreadsheet via existing gspread integration.
    # (This needs whatever env/service-account creds your normal import uses.)
    spreadsheet = sheet_utils.read_spreadsheet(
        url=core_spreadsheet_url,
        alias="core spreadsheet",
        validate=False,
    )

    core_rows: Optional[List[Dict[str, Any]]] = None
    for _, contents in spreadsheet.items():
        if contents and isinstance(contents, list) and contents[0]:
            # parse_standards_from_spreadsheeet() uses this exact predicate.
            if any(str(key).startswith("CRE hierarchy") for key in contents[0].keys()):
                core_rows = contents  # type: ignore[assignment]
                break

    if not core_rows:
        raise RuntimeError(
            "Could not find a worksheet in the spreadsheet with 'CRE hierarchy' columns."
        )

    documents = master_spreadsheet_parser.parse_hierarchical_export_format(core_rows)

    # Ensure schema exists (run_import_only may have already created it).
    collection = cre_main.db_connect(path=db_path)
    from application import sqla

    sqla.create_all()

    # CREs first (so when standard nodes get registered, CRE links can resolve).
    for cre in documents.get(cre_defs.Credoctypes.CRE.value, []):
        cre_main.register_cre(cre=cre, collection=collection)

    # Then register each standard bucket.
    for standard_name, standard_entries in documents.items():
        if standard_name == cre_defs.Credoctypes.CRE.value:
            continue
        if not standard_entries:
            continue
        cre_main.register_standard(
            standard_entries=standard_entries,
            db_connection_str=db_path,
            calculate_gap_analysis=False,
            generate_embeddings=False,
            collection=collection,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Import->backup->upstream sync->diff.")
    parser.add_argument(
        "--db",
        default=None,
        help="Path for the *work* sqlite database. If omitted, uses a fresh temp sqlite file.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting --db if it already exists (only applies when --db is provided).",
    )
    parser.add_argument(
        "--skip-core",
        action="store_true",
        help="Skip importing the main OpenCRE spreadsheet hierarchy before external parsers.",
    )
    parser.add_argument(
        "--core-spreadsheet-url",
        default="https://docs.google.com/spreadsheets/d/1eZOEYgts7d_-Dr-1oAbogPfzBLh6511b58pX3b59kvg",
        help="URL of the main OpenCRE spreadsheet to import (unless --skip-core is set).",
    )
    parser.add_argument(
        "--backup",
        default=None,
        help="Path for the backup sqlite file after import. Defaults to <db>.imported_backup.sqlite",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=50,
        help="Max number of items to print per section (prevents massive console output).",
    )
    parser.add_argument(
        "--verify-checkpoint-2-incremental",
        action="store_true",
        help="Run checkpoint-2 incremental cache verification on --db (delete every Nth cache row and verify refill/skip behavior).",
    )
    parser.add_argument(
        "--delete-every-n",
        type=int,
        default=10,
        help="When using --verify-checkpoint-2-incremental, delete every Nth cache row.",
    )
    parser.add_argument(
        "--skip-gap-analysis-verification",
        action="store_true",
        help="When using --verify-checkpoint-2-incremental, only verify embeddings and skip GA cache refill checks.",
    )
    args = parser.parse_args()

    # Load local environment (.env) if present so API keys/config are picked up.
    # This is especially useful for GEMINI/OpenAI auth used by PromptHandler.
    load_dotenv(os.path.join(_repo_root(), ".env"), override=False)

    # Ensure repo root is importable.
    sys.path.insert(0, _repo_root())

    tmpdir: Optional[str] = None
    if args.db:
        work_db = os.path.abspath(args.db)
    else:
        # Remove leftovers from previous runs.
        for old in sorted(
            [p for p in __import__("glob").glob("/tmp/opencre_upstream_diff_*") if os.path.isdir(p)]
        ):
            try:
                shutil.rmtree(old)
                print(f"Removed previous temp dir: {old}")
            except Exception as e:
                print(f"WARNING: could not remove temp dir {old}: {e}")

        tmpdir = tempfile.mkdtemp(prefix="opencre_upstream_diff_")
        work_db = os.path.join(tmpdir, "standards_cache.sqlite")

    backup_db = (
        os.path.abspath(args.backup)
        if args.backup
        else os.path.abspath(work_db + ".imported_backup.sqlite")
    )

    work_db_dir = os.path.dirname(work_db)
    os.makedirs(work_db_dir, exist_ok=True)

    print(f"Work DB: {work_db}")
    print(f"Backup DB: {backup_db}")

    if args.verify_checkpoint_2_incremental:
        if not args.db:
            raise ValueError("--verify-checkpoint-2-incremental requires --db")
        verify_checkpoint_2_incremental(
            db_path=work_db,
            delete_every_n=args.delete_every_n,
            verify_gap_analysis=not args.skip_gap_analysis_verification,
        )
        return

    if not args.skip_core:
        os.environ["OPENCRE_IMPORT_CORE"] = "1"
        os.environ["OPENCRE_CORE_SPREADSHEET_URL"] = args.core_spreadsheet_url

    run_import_only(work_db, overwrite=bool(args.overwrite))

    print("Copying work DB to backup...")
    shutil.copy2(work_db, backup_db)

    run_upstream_sync(work_db)

    print("Comparing backup vs upstream-updated DB...")
    compare_databases(backup_db=backup_db, new_db=work_db, max_items=args.max_items)

    if tmpdir:
        print(f"Temp dir preserved at: {tmpdir}")


if __name__ == "__main__":
    main()

