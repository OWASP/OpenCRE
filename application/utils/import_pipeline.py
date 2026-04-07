"""
Central import pipeline.

Step 9 contract (docs/importing-next-steps.md):
- Parsers return ParseResult (collect objects only).
- This module is the single place that performs DB registration/writes and
  triggers GA/embeddings based on ParseResult flags and environment switches.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from application.database import db as db_mod
from application.prompt_client import prompt_client
from application.utils.external_project_parsers import base_parser_defs

logger = logging.getLogger(__name__)


def parse_result_from_yaml_document_forest(
    roots: List[Any],
    *,
    calculate_gap_analysis: bool = True,
    calculate_embeddings: bool = True,
) -> base_parser_defs.ParseResult:
    """
    Flatten linked YAML/export documents into a ParseResult (CRE group + per-name groups).
    Does not touch the database.
    """
    from application.defs import cre_defs as defs

    cre_key = defs.Credoctypes.CRE.value
    cres_by_id: dict = {}
    by_name: dict = {}
    seen: set = set()
    stack = list(roots)
    while stack:
        d = stack.pop()
        if id(d) in seen:
            continue
        seen.add(id(d))
        if isinstance(d, defs.CRE):
            if d.id:
                cres_by_id[d.id] = d
            for link in d.links or []:
                if link.document:
                    stack.append(link.document)
        elif isinstance(d, (defs.Standard, defs.Code, defs.Tool)):
            by_name.setdefault(d.name, []).append(d)
            for link in d.links or []:
                if link.document:
                    stack.append(link.document)
        else:
            for link in getattr(d, "links", None) or []:
                if link.document:
                    stack.append(link.document)
    results: dict = {cre_key: list(cres_by_id.values())}
    results.update(by_name)
    return base_parser_defs.ParseResult(
        results=results,
        calculate_gap_analysis=calculate_gap_analysis,
        calculate_embeddings=calculate_embeddings,
    )


def _phase2_snapshots_and_staging(
    collection: db_mod.Node_collection,
    parse_result: base_parser_defs.ParseResult,
    import_run_id: str,
    import_source: str,
) -> None:
    from application.defs import cre_defs as defs
    from application.database import db as db_api
    from application.utils import import_diff

    change_ops: list[import_diff.ChangeSetOp] = []
    prev_run = db_api.get_previous_import_run(import_source, import_run_id)
    manual_keys: set = set()
    cre_key = defs.Credoctypes.CRE.value

    for standard_name, docs in parse_result.results.items():
        if standard_name == cre_key:
            continue
        if not docs:
            continue
        first = docs[0]
        if getattr(getattr(first, "doctype", None), "value", None) != defs.Credoctypes.Standard.value:
            continue

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
                prev_standards = [d for d in prev_docs if isinstance(d, defs.Standard)]
                live = import_diff.live_standard_defs_for_resource(collection, standard_name)
                manual_keys |= import_diff.detect_manual_edit_keys(prev_standards, live)

    staging_has_conflicts = import_diff.has_conflicts(change_ops, manual_keys)
    db_api.persist_staged_change_set(
        run_id=import_run_id,
        changeset_json=import_diff.change_set_to_json(change_ops),
        has_conflicts=staging_has_conflicts,
        staging_status="pending_review",
    )


def apply_parse_result(
    *,
    parse_result: base_parser_defs.ParseResult,
    collection: db_mod.Node_collection,
    prompt_handler: Optional[prompt_client.PromptHandler] = None,
    db_connection_str: str = "",
    import_run_id: Optional[str] = None,
    import_source: Optional[str] = None,
    validate_classification_tags: bool = True,
) -> None:
    """
    Apply a ParseResult to the DB.

    - CREs first (so standard links can resolve)
    - Then each resource group via cre_main.register_standard
    """
    import time
    from application.cmd import cre_main
    from application.defs import cre_defs as defs
    from application.utils import telemetry

    start_time = time.time()
    status = "success"
    error_msg = None

    try:
        if not parse_result or not parse_result.results:
            return

        if validate_classification_tags:
            base_parser_defs.validate_classification_tags(parse_result.results)

        if import_run_id and import_source:
            _phase2_snapshots_and_staging(
                collection, parse_result, import_run_id, import_source
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
            cre_main.register_standard(
                standard_entries=docs,  # type: ignore[arg-type]
                collection=collection,
                generate_embeddings=parse_result.calculate_embeddings,
                calculate_gap_analysis=parse_result.calculate_gap_analysis,
                db_connection_str=db_connection_str,
            )
    except Exception as e:
        status = "failure"
        error_msg = str(e)
        raise e
    finally:
        if import_run_id and import_source:
            telemetry.emit_import_event(
                import_run_id=import_run_id,
                source=import_source,
                version=None,
                status=status,
                start_time=start_time,
                end_time=time.time(),
                error_message=error_msg
            )


def apply_parse_result_with_rq(
    *,
    parse_result: base_parser_defs.ParseResult,
    cache_location: str,
    collection: db_mod.Node_collection,
    prompt_handler: Optional[prompt_client.PromptHandler] = None,
    import_run_id: Optional[str] = None,
    import_source: Optional[str] = None,
    validate_classification_tags: bool = True,
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
    from application.utils import gap_analysis, redis, telemetry
    
    start_time = time.time()
    status = "success"
    error_msg = None

    try:
        if not parse_result or not parse_result.results:
            return

        if validate_classification_tags:
            base_parser_defs.validate_classification_tags(parse_result.results)

        if import_run_id and import_source:
            _phase2_snapshots_and_staging(
                collection, parse_result, import_run_id, import_source
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

        if os.environ.get("CRE_NO_NEO4J") != "1":
            cre_main.populate_neo4j_db(cache_location)
        if os.environ.get("CRE_NO_GEN_EMBEDDINGS") != "1":
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
            if os.environ.get("CRE_NO_REIMPORT_IF_EXISTS") == "1" and database.get_nodes(
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
    except Exception as e:
        status = "failure"
        error_msg = str(e)
        raise e
    finally:
        if import_run_id and import_source:
            telemetry.emit_import_event(
                import_run_id=import_run_id,
                source=import_source,
                version=None,
                status=status,
                start_time=start_time,
                end_time=time.time(),
                error_message=error_msg
            )
