"""
Central import pipeline.

Step 9 contract (docs/importing-next-steps.md):
- Parsers return ParseResult (collect objects only).
- This module is the single place that performs DB registration/writes and
  triggers GA/embeddings based on ParseResult flags and environment switches.
"""

from __future__ import annotations

import logging
from typing import Optional

from application.database import db as db_mod
from application.prompt_client import prompt_client
from application.utils.external_project_parsers import base_parser_defs

logger = logging.getLogger(__name__)


def apply_parse_result(
    *,
    parse_result: base_parser_defs.ParseResult,
    collection: db_mod.Node_collection,
    prompt_handler: Optional[prompt_client.PromptHandler] = None,
    db_connection_str: str = "",
    import_run_id: Optional[str] = None,
    import_source: Optional[str] = None,
) -> None:
    """
    Apply a ParseResult to the DB.

    - CREs first (so standard links can resolve)
    - Then each resource group via cre_main.register_standard
    """
    from application.cmd import cre_main
    from application.defs import cre_defs as defs
    from application.database import db as db_api
    from application.utils import import_diff

    if not parse_result or not parse_result.results:
        return

    # Fail fast if classification tags are missing.
    base_parser_defs.validate_classification_tags(parse_result.results)

    # Phase 2 (Steps 1 & 2): persist snapshots + staged change set for this run.
    if import_run_id and import_source:
        change_ops: list[import_diff.ChangeSetOp] = []
        prev_run = db_api.get_previous_import_run(import_source, import_run_id)
        for standard_name, docs in parse_result.results.items():
            if standard_name == defs.Credoctypes.CRE.value:
                continue
            if not docs:
                continue
            first = docs[0]
            if getattr(getattr(first, "doctype", None), "value", None) != defs.Credoctypes.Standard.value:
                continue

            # Canonical snapshot JSON (stable ordering by id).
            snap_docs = sorted(docs, key=lambda d: getattr(d, "id", "") or "")
            snapshot_json = import_diff.stable_json([d.todict() for d in snap_docs])
            content_hash = import_diff.sha256_hex(snapshot_json)
            db_api.persist_standard_snapshot(
                run_id=import_run_id,
                standard_name=standard_name,
                snapshot_json=snapshot_json,
                content_hash=content_hash,
            )

            if prev_run:
                prev_snap = db_api.get_standard_snapshot(
                    run_id=prev_run.id, standard_name=standard_name
                )
                if prev_snap:
                    prev_docs = [
                        defs.Document.from_dict(d)
                        for d in import_diff.json_loads(prev_snap.snapshot_json)
                    ]
                    new_docs = [defs.Document.from_dict(d) for d in import_diff.json_loads(snapshot_json)]
                    diff = import_diff.diff_standards(
                        previous=prev_docs,  # type: ignore[arg-type]
                        new=new_docs,  # type: ignore[arg-type]
                    )
                    change_ops.extend(import_diff.diff_to_change_set(diff))

        db_api.persist_staged_change_set(
            run_id=import_run_id,
            changeset_json=import_diff.change_set_to_json(change_ops),
            has_conflicts=False,
            staging_status="pending_review",
        )

    if prompt_handler is None:
        prompt_handler = prompt_client.PromptHandler(database=collection)

    cre_key = defs.Credoctypes.CRE.value
    cres = parse_result.results.get(cre_key) or []
    if cres:
        for cre in cres:
            cre_main.register_cre(cre=cre, collection=collection)

    for resource_name, docs in parse_result.results.items():
        if resource_name == cre_key:
            continue
        if not docs:
            continue
        # register_standard handles Tool/Code/Standard entries alike.
        cre_main.register_standard(
            standard_entries=docs,  # type: ignore[arg-type]
            collection=collection,
            generate_embeddings=parse_result.calculate_embeddings,
            calculate_gap_analysis=parse_result.calculate_gap_analysis,
            db_connection_str=db_connection_str,
        )


def apply_parse_result_with_rq(
    *,
    parse_result: base_parser_defs.ParseResult,
    cache_location: str,
    collection: db_mod.Node_collection,
    prompt_handler: Optional[prompt_client.PromptHandler] = None,
    import_run_id: Optional[str] = None,
    import_source: Optional[str] = None,
) -> None:
    """
    Apply ParseResult using the legacy RQ-parallel standard registration pattern.

    - CREs are registered synchronously first
    - Standards/Tools/Code groups are enqueued as separate jobs (register_standard)
    - GA/embeddings behavior remains governed by register_standard and env flags
    """
    import json
    import os
    import time
    from alive_progress import alive_bar
    from rq import Queue

    from application.cmd import cre_main
    from application.defs import cre_defs as defs
    from application.utils import gap_analysis, redis
    from application.database import db as db_api
    from application.utils import import_diff

    if not parse_result or not parse_result.results:
        return

    base_parser_defs.validate_classification_tags(parse_result.results)

    # Phase 2 (Steps 1 & 2): persist snapshots + staged change set for this run.
    if import_run_id and import_source:
        change_ops: list[import_diff.ChangeSetOp] = []
        prev_run = db_api.get_previous_import_run(import_source, import_run_id)
        for standard_name, docs_for_std in parse_result.results.items():
            if standard_name == defs.Credoctypes.CRE.value:
                continue
            if not docs_for_std:
                continue
            first = docs_for_std[0]
            if getattr(getattr(first, "doctype", None), "value", None) != defs.Credoctypes.Standard.value:
                continue

            snap_docs = sorted(docs_for_std, key=lambda d: getattr(d, "id", "") or "")
            snapshot_json = import_diff.stable_json([d.todict() for d in snap_docs])
            content_hash = import_diff.sha256_hex(snapshot_json)
            db_api.persist_standard_snapshot(
                run_id=import_run_id,
                standard_name=standard_name,
                snapshot_json=snapshot_json,
                content_hash=content_hash,
            )

            if prev_run:
                prev_snap = db_api.get_standard_snapshot(
                    run_id=prev_run.id, standard_name=standard_name
                )
                if prev_snap:
                    prev_docs = [
                        defs.Document.from_dict(d)
                        for d in import_diff.json_loads(prev_snap.snapshot_json)
                    ]
                    new_docs = [
                        defs.Document.from_dict(d)
                        for d in import_diff.json_loads(snapshot_json)
                    ]
                    diff = import_diff.diff_standards(
                        previous=prev_docs,  # type: ignore[arg-type]
                        new=new_docs,  # type: ignore[arg-type]
                    )
                    change_ops.extend(import_diff.diff_to_change_set(diff))

        db_api.persist_staged_change_set(
            run_id=import_run_id,
            changeset_json=import_diff.change_set_to_json(change_ops),
            has_conflicts=False,
            staging_status="pending_review",
        )

    if prompt_handler is None:
        prompt_handler = prompt_client.PromptHandler(database=collection)

    conn = redis.connect()
    collection = collection.with_graph()
    redis.empty_queues(conn)
    q = Queue(connection=conn)

    docs = dict(parse_result.results)

    cre_key = defs.Credoctypes.CRE.value
    cres = docs.pop(cre_key, []) or []

    logger.info("Importing %s CREs", len(cres))
    with alive_bar(len(cres)) as bar:
        for cre in cres:
            cre_main.register_cre(cre=cre, collection=collection)
            bar()

    if not os.environ.get("CRE_NO_NEO4J"):
        cre_main.populate_neo4j_db(cache_location)
    if not os.environ.get("CRE_NO_GEN_EMBEDDINGS"):
        prompt_handler.generate_embeddings_for(defs.Credoctypes.CRE.value)

    import_only: list[str] = []
    if os.environ.get("CRE_ROOT_CSV_IMPORT_ONLY", None):
        import_list = os.environ.get("CRE_ROOT_CSV_IMPORT_ONLY")
        try:
            import_list_json = json.loads(import_list)
        except json.JSONDecodeError as jde:
            logger.error("CRE_ROOT_CSV_IMPORT_ONLY is not valid json: %s", import_list)
            raise jde
        if isinstance(import_list_json, list):
            import_only.extend(import_list_json)
        else:
            logger.warning(
                "CRE_ROOT_CSV_IMPORT_ONLY should be a list, received %s",
                type(import_list_json),
            )

    database = cre_main.db_connect(cache_location)
    jobs = []
    for standard_name, standard_entries in docs.items():
        if os.environ.get("CRE_NO_REIMPORT_IF_EXISTS") and database.get_nodes(
            name=standard_name
        ):
            logger.info(
                "Already know of %s and CRE_NO_REIMPORT_IF_EXISTS is set, skipping",
                standard_name,
            )
            continue
        if import_only and standard_name not in import_only:
            logger.info(
                "Skipping standard %s; not in %s",
                standard_name,
                import_only,
            )
            continue
        jobs.append(
            q.enqueue_call(
                description=standard_name,
                func=cre_main.register_standard,
                kwargs={
                    "standard_entries": standard_entries,
                    "collection": None,
                    "db_connection_str": cache_location,
                    "calculate_gap_analysis": parse_result.calculate_gap_analysis,
                    "generate_embeddings": parse_result.calculate_embeddings,
                },
                timeout=gap_analysis.GAP_ANALYSIS_TIMEOUT,
            )
        )

    t0 = time.perf_counter()
    total = len(jobs)
    logger.info("Importing %s resource groups via RQ", total)
    with alive_bar(theme="classic", total=total) as bar:
        redis.wait_for_jobs(jobs, bar)
    logger.info("Imported %s groups in %.2fs", total, time.perf_counter() - t0)

