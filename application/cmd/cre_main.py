import re
import time
import argparse
import json
import logging
import os
import shutil
import tempfile
import requests

from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple
import hashlib
import json as _json
from rq import Queue, job, exceptions
from sqlalchemy import not_

from application.utils.external_project_parsers.base_parser import BaseParser
from application.utils.external_project_parsers.parsers import master_spreadsheet_parser
from application import create_app  # type: ignore
from application.config import CMDConfig
from application.database import db
from application.defs import cre_defs as defs
from application.defs import cre_exceptions
from application.defs import osib_defs as odefs
from application.utils import spreadsheet as sheet_utils
from application.utils import redis
from application.utils import db_backend
from alive_progress import alive_bar
from application.prompt_client import prompt_client as prompt_client
from application.utils import gap_analysis
from application.utils import cres_csv_export

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = None


def register_node(node: defs.Node, collection: db.Node_collection) -> db.Node:
    """
    for each link find if either the root node or the link have a CRE,
    then map the one who doesn't to the CRE
    if both don't map to anything, just add them in the db as unlinked nodes
    """
    if not node or not issubclass(node.__class__, defs.Node):
        raise ValueError(f"node is None or not of type Node, node: {node}")

    linked_node = collection.add_node(node)
    if node.embeddings:
        collection.add_embedding(
            linked_node,
            doctype=node.doctype,
            embeddings=node.embeddings,
            embedding_text=node.embeddings_text,
        )
    cre_less_nodes: List[defs.Node] = []

    # we need to know the cres added in case we encounter a higher level CRE,
    # in which case we get the higher level CRE to link to these cres
    cres_added = []

    for link in node.links:
        if type(link.document).__name__ in [
            defs.Standard.__name__,
            defs.Code.__name__,
            defs.Tool.__name__,
        ]:
            # if a node links another node it is likely that a writer wants to reference something
            # in that case, find which of the two nodes has at least one CRE attached to it and link both to the parent CRE
            cres = collection.find_cres_of_node(link.document)
            db_link = collection.add_node(link.document)
            if cres:
                for cre in cres:
                    collection.add_link(cre=cre, node=linked_node, ltype=link.ltype)
                    for unlinked_standard in cre_less_nodes:  # if anything in this
                        collection.add_link(
                            cre=cre,
                            node=db.dbNodeFromNode(unlinked_standard),
                            ltype=link.ltype,
                        )
            else:
                cres = collection.find_cres_of_node(linked_node)
                if cres:
                    for cre in cres:
                        collection.add_link(cre=cre, node=db_link, ltype=link.ltype)
                        for unlinked_node in cre_less_nodes:
                            collection.add_link(
                                cre=cre,
                                node=db.dbNodeFromNode(unlinked_node),
                                ltype=link.ltype,
                            )
                else:  # if neither the root nor a linked node has a CRE, add both as unlinked nodes
                    cre_less_nodes.append(link.document)

            if link.document.links and len(link.document.links) > 0:
                register_node(node=link.document, collection=collection)

        elif type(link.document).__name__ == defs.CRE.__name__:
            # dbcre,_ = register_cre(link.document, collection) # CREs are idempotent
            c = collection.get_CREs(name=link.document.name)[0]
            dbcre = db.dbCREfromCRE(c)
            collection.add_link(dbcre, linked_node, ltype=link.ltype)
            cres_added.append(dbcre)
            for unlinked_standard in cre_less_nodes:  # if anything in this
                collection.add_link(
                    cre=dbcre,
                    node=db.dbNodeFromNode(unlinked_standard),
                    ltype=link.ltype,
                )
            cre_less_nodes = []

    return linked_node


def register_cre(cre: defs.CRE, collection: db.Node_collection) -> Tuple[db.CRE, bool]:
    if not cre.id or not re.match(r"\d\d\d-\d\d\d", cre.id):
        raise cre_exceptions.InvalidCREIDException(cre)
    collection = collection.with_graph()
    existing = False
    if collection.get_CREs(external_id=cre.id):
        existing = True

    dbcre: db.CRE = collection.add_cre(cre)
    for link in cre.links:
        if type(link.document) == defs.CRE:
            other_cre, _ = register_cre(link.document, collection)

            # the following flips the PartOf relationship so that we only have contains relationship in the database
            if link.ltype == defs.LinkTypes.Contains:
                collection.add_internal_link(
                    higher=dbcre,
                    lower=other_cre,
                    ltype=defs.LinkTypes.Contains,
                )
            elif link.ltype == defs.LinkTypes.PartOf:
                collection.add_internal_link(
                    higher=other_cre,
                    lower=dbcre,
                    ltype=defs.LinkTypes.Contains,
                )
            elif link.ltype == defs.LinkTypes.Related:
                collection.add_internal_link(
                    higher=other_cre,
                    lower=dbcre,
                    ltype=defs.LinkTypes.Related,
                )
            else:
                raise ValueError(f"Unknown link type {link.ltype}")
        else:
            collection.add_link(
                cre=dbcre,
                node=register_node(node=link.document, collection=collection),
                ltype=link.ltype,
            )
    return dbcre, existing


def resolve_ga_peer_standard_names(
    collection: db.Node_collection, importing_name: str
) -> List[str]:
    """Increment Step 10: GA peer list — CRE-sharing standards, else all others."""
    shared = []
    if shared:
        return shared
    return [s for s in collection.standards() if s != importing_name]


def _document_doctype_value(doc: defs.Document) -> str:
    doctype = getattr(doc, "doctype", None)
    if hasattr(doctype, "value"):
        return doctype.value
    return str(doctype)


def _has_ga_eligible_tags(tags: List[str]) -> bool:
    """
    GA eligibility tag matrix.

    - Requirements standards remain eligible (family:standard + subtype:requirements_standard)
    - Taxonomy/risk-list standards are also eligible (e.g. CAPEC)
    """
    tag_set = set(tags)
    return {"family:standard", "subtype:requirements_standard"}.issubset(tag_set) or {
        "family:taxonomy",
        "subtype:risk_list",
    }.issubset(tag_set)


def document_is_ga_eligible(doc: defs.Document, *, log_skips: bool = True) -> bool:
    """
    Whether a resource group should participate in gap analysis.

    Must stay in sync with register_standard: Tools/Code are excluded; other
    documents require classification tags (family:standard +
    subtype:requirements_standard).
    """
    doctype = _document_doctype_value(doc)
    if doctype in (defs.Credoctypes.Tool.value, defs.Credoctypes.Code.value):
        return False

    raw_tags = getattr(doc, "tags", None)
    if isinstance(raw_tags, (list, tuple, set)):
        tags = list(raw_tags)
    else:
        tags = []
    if not _has_ga_eligible_tags(tags):
        if log_skips:
            logger.info(
                "Skipping gap analysis for %s because tags are not GA-eligible",
                getattr(doc, "name", "<unknown>"),
            )
        return False

    return True


def resource_name_ga_eligible_in_db(
    collection: db.Node_collection, resource_name: str
) -> bool:
    """
    Post-import GA eligibility using SQL node rows (for post_apply paths that
    only have resource names, not defs.Document lists).
    """
    from sqlalchemy import func

    row = (
        collection.session.query(db.Node)
        .filter(func.lower(db.Node.name) == resource_name.lower())
        .first()
    )
    if not row:
        return False
    if row.ntype in (defs.Credoctypes.Tool.value, defs.Credoctypes.Code.value):
        return False
    if row.ntype != defs.Credoctypes.Standard.value:
        return False
    raw_tags = row.tags or ""
    tag_set = {t.strip() for t in str(raw_tags).split(",") if t.strip()}
    return _has_ga_eligible_tags(list(tag_set))


def schedule_gap_analysis_importing_vs_peers(
    *,
    collection: db.Node_collection,
    importing_name: str,
    db_connection_str: str,
    peer_names: Optional[List[str]] = None,
    skip_neo_populate: bool = False,
) -> None:
    """Perform forward/back GA jobs between importing_name and each peer synchronously."""
    if os.environ.get("CRE_NO_CALCULATE_GAP_ANALYSIS") == "1":
        return
    if peer_names is None:
        peer_names = resolve_ga_peer_standard_names(collection, importing_name)
    if not skip_neo_populate:
        populate_neo4j_db(db_connection_str)

    for standard_name in peer_names:
        if standard_name == importing_name:
            continue

        gap_analysis.perform(
            standards=[importing_name, standard_name], database=collection
        )

        gap_analysis.perform(
            standards=[standard_name, importing_name], database=collection
        )


def run_gap_pair_job(importing_name: str, peer_name: str, db_connection_str: str):
    """RQ job wrapper for one directed GA pair."""
    caps = db_backend.detect_backend(db_connection_str)
    if not caps.is_postgres:
        raise RuntimeError(
            f"Pair GA scheduling requires Postgres backend, got {caps.backend}"
        )
    collection = db_connect(path=db_connection_str)
    return gap_analysis.run_gap_pair(
        importing_name=importing_name,
        peer_name=peer_name,
        database=collection,
        # Backend is validated from explicit connection string above.
        require_postgres=False,
    )


def schedule_gap_analysis_pairs_with_rq(
    *,
    collection: db.Node_collection,
    importing_name: str,
    db_connection_str: str,
    peer_names: Optional[List[str]] = None,
    skip_neo_populate: bool = False,
):
    """
    Rung 1 primitive: enqueue directed GA pair jobs in RQ.

    This function only schedules work. It does NOT wait for completion.
    """
    if os.environ.get("CRE_NO_CALCULATE_GAP_ANALYSIS") == "1":
        return []
    if peer_names is None:
        peer_names = resolve_ga_peer_standard_names(collection, importing_name)
    if not skip_neo_populate:
        populate_neo4j_db(db_connection_str)

    caps = db_backend.detect_backend(db_connection_str)
    if not caps.is_postgres:
        raise RuntimeError(
            f"Pair GA scheduling requires Postgres backend, got {caps.backend}"
        )

    conn = redis.connect()
    ga_queue_name = os.environ.get("CRE_GA_QUEUE_NAME", "ga")
    q = Queue(name=ga_queue_name, connection=conn)
    jobs = []
    max_pairs = int(os.environ.get("CRE_GA_MAX_ENQUEUED_PAIRS", "0"))
    enqueued = 0
    for standard_name in peer_names:
        if standard_name == importing_name:
            continue
        for a, b in ((importing_name, standard_name), (standard_name, importing_name)):
            if max_pairs > 0 and enqueued >= max_pairs:
                logger.info(
                    "Reached CRE_GA_MAX_ENQUEUED_PAIRS=%s for %s; deferring remaining pairs",
                    max_pairs,
                    importing_name,
                )
                return jobs
            jobs.append(
                q.enqueue_call(
                    description=f"{a}->{b}",
                    func=run_gap_pair_job,
                    kwargs={
                        "importing_name": a,
                        "peer_name": b,
                        "db_connection_str": db_connection_str,
                    },
                    timeout=gap_analysis.GAP_ANALYSIS_TIMEOUT,
                )
            )
            enqueued += 1
    return jobs


def register_standard(
    standard_entries: List[defs.Standard],
    collection: db.Node_collection = None,
    generate_embeddings=True,
    calculate_gap_analysis=True,
    db_connection_str: str = "",
):
    if os.environ.get("CRE_NO_GEN_EMBEDDINGS") == "1":
        generate_embeddings = False

    if not standard_entries:
        logger.warning("register_standard() called with no standard_entries")
        return

    if collection is None:
        collection = db_connect(path=db_connection_str)

    def _standard_structure_fingerprint(resource_name: str) -> str:
        """
        Fingerprint the structure of a resource in the DB.

        Used for Step 10 incremental GA: if structure is unchanged after reimport,
        skip GA scheduling entirely for that resource.
        """
        rows: List[tuple] = []
        try:
            nodes = collection.get_nodes(name=resource_name) or []
        except Exception:
            nodes = []
        for n in nodes:
            # Include identity-like fields and a stable view of CRE links.
            links = []
            for l in getattr(n, "links", []) or []:
                doc = getattr(l, "document", None)
                if not doc:
                    continue
                # Focus on CRE links for GA topology. Ignore embedding-only fields.
                doctype = getattr(doc, "doctype", None)
                doctype_val = (
                    doctype.value if hasattr(doctype, "value") else str(doctype)
                )
                links.append(
                    (
                        (
                            getattr(l, "ltype", None).value
                            if hasattr(getattr(l, "ltype", None), "value")
                            else str(getattr(l, "ltype", ""))
                        ),
                        doctype_val,
                        getattr(doc, "id", "") or "",
                        getattr(doc, "name", "") or "",
                    )
                )
            rows.append(
                (
                    getattr(n, "name", "") or "",
                    getattr(n, "sectionID", "") or "",
                    getattr(n, "section", "") or "",
                    getattr(n, "subsection", "") or "",
                    getattr(n, "version", "") or "",
                    tuple(sorted(links)),
                )
            )
        payload = _json.dumps(
            sorted(rows), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    conn = redis.connect()
    ph = prompt_client.PromptHandler(database=collection)
    importing_name = standard_entries[0].name
    effective_calculate_gap_analysis = (
        calculate_gap_analysis and document_is_ga_eligible(standard_entries[0])
    )
    if calculate_gap_analysis and not effective_calculate_gap_analysis:
        # document_is_ga_eligible already logs the precise reason when log_skips default applies.
        logger.info(
            "Skipping gap analysis for %s because resource is not GA-eligible",
            importing_name,
        )
    standard_hash = gap_analysis.make_resources_key([importing_name])
    if effective_calculate_gap_analysis and conn.get(standard_hash):
        logger.info(
            f"Standard importing job with info-hash {standard_hash} has already returned, skipping"
        )
        return

    before_fp: Optional[str] = None
    if (
        effective_calculate_gap_analysis
        and os.environ.get("CRE_NO_CALCULATE_GAP_ANALYSIS") != "1"
    ):
        before_fp = _standard_structure_fingerprint(importing_name)
    logger.info(
        f"Registering resource {importing_name} of length {len(standard_entries)}"
    )
    import_phase_t0 = time.perf_counter()
    for node in standard_entries:
        if not node:
            logger.info(
                f"encountered empty node while importing {standard_entries[0].name}"
            )
            continue
        register_node(node, collection)
        if node.embeddings:
            logger.debug(
                f"node has embeddings populated, skipping generation for resource {importing_name}"
            )
            generate_embeddings = False
    if generate_embeddings and importing_name:
        ph.generate_embeddings_for(importing_name)
    import_phase_elapsed = time.perf_counter() - import_phase_t0
    logger.info(
        "CP0 timing for %s: import_phase_s=%.2f",
        importing_name,
        import_phase_elapsed,
    )

    if (
        effective_calculate_gap_analysis
        and os.environ.get("CRE_NO_CALCULATE_GAP_ANALYSIS") != "1"
    ):
        # GA orchestration is centralized in import_pipeline (pair-level model).
        # register_standard only performs writes/import-phase work.
        after_fp = _standard_structure_fingerprint(importing_name)
        if before_fp is not None and before_fp == after_fp:
            logger.info(
                "Skipping GA intent for %s because structure fingerprint unchanged",
                importing_name,
            )
            conn.set(standard_hash, value="")
            return
        logger.info(
            "Deferring GA scheduling for %s to import pipeline pair coordinator",
            importing_name,
        )


def parse_standards_from_spreadsheeet(
    cre_file: List[Dict[str, Any]],
    cache_location: str,
    prompt_handler: prompt_client.PromptHandler,
) -> None:
    """given a csv with standards, build a list of standards in the db"""
    if not cre_file:
        logger.fatal("empty spreadsheet")
        return None

    import_source_label = "master_spreadsheet"
    from application.utils.external_project_parsers.parsers.ai_exchange import (
        IMPORT_SOURCE_CSV,
        is_ai_exchange_spreadsheet,
        normalize_rows_for_master_import,
    )

    if is_ai_exchange_spreadsheet(cre_file[0]):
        cre_file = normalize_rows_for_master_import(cre_file)
        import_source_label = IMPORT_SOURCE_CSV

    if any(key.startswith("CRE hierarchy") for key in cre_file[0].keys()):
        try:
            run = db.create_import_run(source=import_source_label, version=None)
        except Exception as e:
            logger.debug("Import run tracking skipped: %s", e)
            run = None
        from application.utils import import_pipeline

        collection = db_connect(cache_location)
        parse_result = master_spreadsheet_parser.MasterSpreadsheetParser.parse_rows(
            cre_file
        )
        import_pipeline.apply_parse_result_with_rq(
            parse_result=parse_result,
            cache_location=cache_location,
            collection=collection,
            prompt_handler=prompt_handler,
            import_run_id=run.id if run else None,
            import_source=run.source if run else None,
        )
        return parse_result.results.keys()
    else:
        logger.fatal(f"could not find any useful keys { cre_file[0].keys()}")


def add_from_ai_exchange_csv(csv_path: str, cache_loc: str) -> None:
    """Import CRE graph + MITRE ATLAS + OWASP AI Exchange links from a local CSV export."""
    import csv

    database = db_connect(path=cache_loc)
    prompt_handler = ai_client_init(database=database)
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    parse_standards_from_spreadsheeet(rows, cache_loc, prompt_handler)
    logger.info(
        "Updated database at %s from AI exchange CSV %s",
        cache_loc,
        csv_path,
    )


def add_from_spreadsheet(spreadsheet_url: str, cache_loc: str) -> None:
    """--add --from_spreadsheet <url>
    use the cre db in this repo
    import new mappings from <url>
    export db to ../../cres/
    """
    database = db_connect(path=cache_loc)
    prompt_handler = ai_client_init(database=database)
    spreadsheet = sheet_utils.read_spreadsheet(
        url=spreadsheet_url, alias="new spreadsheet", validate=False
    )
    for _, contents in spreadsheet.items():
        parse_standards_from_spreadsheeet(contents, cache_loc, prompt_handler)

    logger.info("Db located at %s got updated", cache_loc)


def review_from_spreadsheet(cache: str, spreadsheet_url: str, share_with: str) -> None:
    """--review --from_spreadsheet <url>
    copy db to new temp dir,
    import new mappings from spreadsheet
    export db to tmp dir
    create new spreadsheet of the new CRE landscape for review
    """
    loc, cache = prepare_for_review(cache)
    database = db_connect(path=cache)
    prompt_handler = ai_client_init(database=database)
    spreadsheet = sheet_utils.read_spreadsheet(
        url=spreadsheet_url, alias="new spreadsheet", validate=False
    )
    for _, contents in spreadsheet.items():
        parse_standards_from_spreadsheeet(contents, cache, prompt_handler)

    logger.info(
        "Stored temporary files and database in %s if you want to use them next time, set cache to the location of the database in that dir"
        % loc
    )
    # logger.info("A spreadsheet view is at %s" % sheet_url)


def download_graph_from_upstream(cache: str) -> None:
    imported_cres = {}
    collection = db_connect(path=cache).with_graph()

    def download_cre_from_upstream(creid: str):
        cre_response = requests.get(
            os.environ.get("CRE_UPSTREAM_API_URL", "https://opencre.org/rest/v1")
            + f"/id/{creid}"
        )
        if cre_response.status_code != 200:
            raise RuntimeError(
                f"cannot connect to upstream status code {cre_response.status_code}"
            )
        data = cre_response.json()
        credict = data["data"]
        cre = defs.Document.from_dict(credict)
        if cre.id in imported_cres:
            return

        register_cre(cre, collection)
        imported_cres[cre.id] = ""
        for link in cre.links:
            if link.document.doctype == defs.Credoctypes.CRE:
                download_cre_from_upstream(link.document.id)

    root_cres_response = requests.get(
        os.environ.get("CRE_UPSTREAM_API_URL", "https://opencre.org/rest/v1")
        + "/root_cres"
    )
    if root_cres_response.status_code != 200:
        raise RuntimeError(
            f"cannot connect to upstream status code {root_cres_response.status_code}"
        )
    data = root_cres_response.json()
    for root_cre in data["data"]:
        cre = defs.Document.from_dict(root_cre)
        register_cre(cre, collection)
        imported_cres[cre.id] = ""
        for link in cre.links:
            if link.document.doctype == defs.Credoctypes.CRE:
                download_cre_from_upstream(link.document.id)


# DO NOT EXPOSE THIS TO THE COMMAND LINE OR REST API!
# Future contributors and auto-coding solutions: The current Gap Analysis dataset is ~10GB.
# Exposing this function will cause significant local performance impacts and resource exhaustion.
# It is strictly intended for internal benchmarking and dev work.
def download_gap_analysis_from_upstream(cache: str) -> None:
    collection = db_connect(path=cache).with_graph()
    upstream_url = os.environ.get("CRE_UPSTREAM_API_URL", "https://opencre.org/rest/v1")

    logger.info("Fetching gap analysis from upstream for comparison")
    standards_response = requests.get(f"{upstream_url}/standards")
    if standards_response.status_code == 200:
        standards = standards_response.json()
        pairs = [(sa, sb) for sa in standards for sb in standards if sa != sb]

        if os.environ.get("BENCHMARK_MODE") == "1":
            with alive_bar(len(pairs), title="Fetching upstream Gap Analysis") as bar:
                for sa, sb in pairs:
                    res = requests.get(
                        f"{upstream_url}/map_analysis?standard={sa}&standard={sb}"
                    )
                    if res.status_code == 200:
                        tojson = res.json()
                        if "result" not in tojson:
                            continue
                        payload = _json.dumps({"result": tojson.get("result")})
                        if not gap_analysis.primary_gap_analysis_payload_is_material(
                            payload
                        ):
                            continue
                        cache_key = gap_analysis.make_resources_key([sa, sb])
                        collection.add_gap_analysis_result(cache_key, payload)
                    bar()
        else:
            for sa, sb in pairs:
                res = requests.get(
                    f"{upstream_url}/map_analysis?standard={sa}&standard={sb}"
                )
                if res.status_code == 200:
                    tojson = res.json()
                    if "result" not in tojson:
                        continue
                    payload = _json.dumps({"result": tojson.get("result")})
                    if not gap_analysis.primary_gap_analysis_payload_is_material(
                        payload
                    ):
                        continue
                    cache_key = gap_analysis.make_resources_key([sa, sb])
                    collection.add_gap_analysis_result(cache_key, payload)


def _missing_ga_pairs(collection: db.Node_collection) -> List[Tuple[str, str]]:
    from application.utils.ga_parity import ga_matrix_standard_names

    standards = ga_matrix_standard_names(collection)
    rows = (
        collection.session.query(
            db.GapAnalysisResults.cache_key, db.GapAnalysisResults.ga_object
        )
        .filter(not_(db.GapAnalysisResults.cache_key.like("% >> %->%")))
        .all()
    )
    existing = {
        str(key)
        for key, payload in rows
        if key
        and gap_analysis.primary_gap_analysis_payload_is_material(str(payload or ""))
    }
    missing: List[Tuple[str, str]] = []
    for sa in standards:
        for sb in standards:
            if sa == sb:
                continue
            key = gap_analysis.make_resources_key([sa, sb])
            if key not in existing:
                missing.append((sa, sb))
    return missing


def _compute_pair_direct(collection: db.Node_collection, sa: str, sb: str) -> None:
    cache_key = gap_analysis.make_resources_key([sa, sb])
    if collection.gap_analysis_exists(cache_key):
        return
    db.gap_analysis(neo_db=collection.neo_db, node_names=[sa, sb], cache_key=cache_key)


def backfill_gap_analysis_only(
    db_connection_str: str,
    *,
    batch_size: int = 200,
    poll_seconds: int = 5,
    max_pairs: int = 0,
    no_queue: bool = False,
) -> None:
    """
    Backfill only missing directed GA pairs from DB truth.
    This avoids HTTP polling loops and reports progress from SQL state.
    """
    collection = db_connect(path=db_connection_str)
    if os.environ.get("CRE_NO_NEO4J") != "1":
        populate_neo4j_db(db_connection_str)

    missing = _missing_ga_pairs(collection)
    if max_pairs > 0:
        missing = missing[:max_pairs]
    total = len(missing)
    if total == 0:
        logger.info("GA backfill: no missing pairs")
        return

    logger.info(
        "GA backfill: missing_pairs=%s batch_size=%s mode=%s",
        total,
        batch_size,
        "sync" if no_queue else "queue",
    )
    batch_size = max(1, int(batch_size))
    poll_seconds = max(1, int(poll_seconds))

    use_queue = not no_queue
    conn = None
    ga_q = None
    if use_queue:
        try:
            conn = redis.connect()
            ga_q = Queue(
                name=os.environ.get("CRE_GA_QUEUE_NAME", "ga"), connection=conn
            )
        except Exception as exc:
            logger.warning(
                "GA backfill queue unavailable, falling back to sync mode: %s", exc
            )
            use_queue = False

    done = 0
    for i in range(0, total, batch_size):
        batch = missing[i : i + batch_size]
        if use_queue and ga_q is not None and conn is not None:
            jobs = []
            for sa, sb in batch:
                cache_key = gap_analysis.make_resources_key([sa, sb])
                if collection.gap_analysis_exists(cache_key):
                    continue
                inflight_key = f"ga:inflight:{cache_key}"
                inflight_job_id_raw = conn.get(inflight_key)
                inflight_job_id = (
                    inflight_job_id_raw.decode("utf-8")
                    if isinstance(inflight_job_id_raw, bytes)
                    else str(inflight_job_id_raw) if inflight_job_id_raw else ""
                )
                if inflight_job_id:
                    try:
                        inflight_job = job.Job.fetch(
                            id=inflight_job_id, connection=conn
                        )
                        if inflight_job.get_status() in (
                            job.JobStatus.QUEUED,
                            job.JobStatus.STARTED,
                        ):
                            continue
                    except exceptions.NoSuchJobError:
                        conn.delete(inflight_key)

                j = ga_q.enqueue_call(
                    description=f"{sa}->{sb}",
                    func=run_gap_pair_job,
                    kwargs={
                        "importing_name": sa,
                        "peer_name": sb,
                        "db_connection_str": db_connection_str,
                    },
                    timeout=gap_analysis.GAP_ANALYSIS_TIMEOUT,
                )
                conn.set(inflight_key, str(j.id))
                conn.expire(inflight_key, 129600)
                jobs.append(j)

            if jobs:
                with alive_bar(
                    len(jobs), title=f"GA batch {i // batch_size + 1}"
                ) as bar:
                    redis.wait_for_jobs(jobs, bar)
        else:
            with alive_bar(len(batch), title=f"GA batch {i // batch_size + 1}") as bar:
                for sa, sb in batch:
                    _compute_pair_direct(collection, sa, sb)
                    bar()

        done = min(total, i + len(batch))
        remaining = len(_missing_ga_pairs(collection))
        logger.info(
            "GA backfill progress: processed=%s/%s remaining=%s",
            done,
            total,
            remaining,
        )
        time.sleep(poll_seconds)

    final_missing = len(_missing_ga_pairs(collection))
    logger.info("GA backfill complete: final_missing_pairs=%s", final_missing)


def run(args: argparse.Namespace) -> None:  # pragma: no cover
    script_path = os.path.dirname(os.path.realpath(__file__))
    os.path.join(script_path, "../cres")

    if getattr(args, "export", False):
        csv_out = getattr(args, "csv", "").strip()
        if not csv_out:
            raise ValueError("--export requires --csv <path>")
        rows = cres_csv_export.export_cres_and_standards_csv(output_path=csv_out)
        logger.info("Exported %s rows to %s", rows, csv_out)
        return

    if args.add and getattr(args, "from_ai_exchange_csv", None):
        add_from_ai_exchange_csv(
            csv_path=args.from_ai_exchange_csv,
            cache_loc=args.cache_file,
        )
    elif args.add and args.from_spreadsheet:
        add_from_spreadsheet(
            spreadsheet_url=args.from_spreadsheet,
            cache_loc=args.cache_file,
        )

    if args.delete_map_analysis_for:
        cache = db_connect(args.cache_file)
        cache.delete_gapanalysis_results_for(args.delete_map_analysis_for)
    if args.delete_resource:
        cache = db_connect(args.cache_file)
        cache.delete_nodes(args.delete_resource)

    # individual resource importing
    if args.zap_in:
        from application.utils.external_project_parsers.parsers import zap_alerts_parser

        BaseParser().register_resource(
            zap_alerts_parser.ZAP, db_connection_str=args.cache_file
        )
    if args.cheatsheets_in:
        from application.utils.external_project_parsers.parsers import (
            cheatsheets_parser,
        )

        BaseParser().register_resource(
            cheatsheets_parser.Cheatsheets, db_connection_str=args.cache_file
        )
    if args.github_tools_in:
        from application.utils.external_project_parsers.parsers import misc_tools_parser

        BaseParser().register_resource(
            misc_tools_parser.MiscTools, db_connection_str=args.cache_file
        )
    if args.capec_in:
        from application.utils.external_project_parsers.parsers import capec_parser

        BaseParser().register_resource(
            capec_parser.Capec, db_connection_str=args.cache_file
        )
    if args.cwe_in:
        from application.utils.external_project_parsers.parsers import cwe

        BaseParser().register_resource(cwe.CWE, db_connection_str=args.cache_file)
    if args.csa_ccm_v4_in:
        from application.utils.external_project_parsers.parsers import ccmv4

        BaseParser().register_resource(
            ccmv4.CloudControlsMatrix, db_connection_str=args.cache_file
        )
    if args.iso_27001_in:
        from application.utils.external_project_parsers.parsers import iso27001

        BaseParser().register_resource(
            iso27001.ISO27001, db_connection_str=args.cache_file
        )
    if args.owasp_secure_headers_in:
        from application.utils.external_project_parsers.parsers import secure_headers

        BaseParser().register_resource(
            secure_headers.SecureHeaders, db_connection_str=args.cache_file
        )
    if args.pci_dss_4_in:
        from application.utils.external_project_parsers.parsers import pci_dss

        BaseParser().register_resource(
            pci_dss.PciDss, db_connection_str=args.cache_file
        )
    if args.juiceshop_in:
        from application.utils.external_project_parsers.parsers import juiceshop

        BaseParser().register_resource(
            juiceshop.JuiceShop, db_connection_str=args.cache_file
        )
    if args.dsomm_in:
        from application.utils.external_project_parsers.parsers import dsomm

        BaseParser().register_resource(dsomm.DSOMM, db_connection_str=args.cache_file)
    if args.cloud_native_security_controls_in:
        from application.utils.external_project_parsers.parsers import (
            cloud_native_security_controls,
        )

        BaseParser().register_resource(
            cloud_native_security_controls.CloudNativeSecurityControls,
            db_connection_str=args.cache_file,
        )
    # /end individual resource importing

    if args.import_external_projects:
        BaseParser().call_importers(db_connection_str=args.cache_file)

    if getattr(args, "regenerate_embeddings", False):
        regenerate_embeddings(args.cache_file)
    elif args.generate_embeddings:
        generate_embeddings(args.cache_file)
    if args.populate_neo4j_db:
        populate_neo4j_db(args.cache_file)
    if args.start_worker:
        from application.worker import start_worker

        start_worker()

    if args.preload_map_analysis_target_url:
        gap_analysis.preload(target_url=args.preload_map_analysis_target_url)
    if getattr(args, "ga_backfill_missing", False):
        backfill_gap_analysis_only(
            args.cache_file,
            batch_size=getattr(args, "ga_backfill_batch_size", 200),
            poll_seconds=getattr(args, "ga_backfill_poll_seconds", 5),
            max_pairs=getattr(args, "ga_backfill_max_pairs", 0),
            no_queue=getattr(args, "ga_backfill_no_queue", False),
        )
    if args.upstream_sync:
        download_graph_from_upstream(args.cache_file)


def ai_client_init(database: db.Node_collection):
    return prompt_client.PromptHandler(database=database)


def db_connect(path: str):
    global app
    conf = CMDConfig(db_uri=path)
    app = create_app(conf=conf)
    collection = db.Node_collection()
    app_context = app.app_context()
    app_context.push()
    logger.info(f"successfully connected to the database at {path}")
    return collection


def create_spreadsheet(
    collection: db.Node_collection,
    exported_documents: List[Any],
    title: str,
    share_with: List[str],
) -> Any:
    """Reads cre docs exported from a standards_collection.export()
    dumps each doc into a workbook"""
    flat_dicts = sheet_utils.prepare_spreadsheet(docs=exported_documents)
    return sheet_utils.write_spreadsheet(
        title=title, docs=flat_dicts, emails=share_with
    )


def prepare_for_review(cache: str) -> Tuple[str, str]:
    loc = tempfile.mkdtemp()
    cache_filename = os.path.basename(cache)
    if os.path.isfile(cache):
        shutil.copy(cache, loc)
    else:
        logger.fatal("Could not copy database %s this seems like a bug" % cache)
    return loc, os.path.join(loc, cache_filename)


def generate_embeddings(db_url: str) -> None:
    database = db_connect(path=db_url)
    prompt_client.PromptHandler(database, load_all_embeddings=True)


def regenerate_embeddings(db_url: str) -> None:
    """Wipe all embedding rows, then rebuild (CRE + every node type) like ``--generate_embeddings``."""
    database = db_connect(path=db_url)
    removed = database.delete_all_embeddings()
    logger.info("Removed %s embedding rows; rebuilding embeddings", removed)
    prompt_client.PromptHandler(database, load_all_embeddings=True)


def populate_neo4j_db(cache: str):
    if (
        os.environ.get("NO_LOAD_GRAPH_DB") == "1"
        or os.environ.get("CRE_NO_NEO4J") == "1"
    ):
        logger.info("Skipping Neo4j population as per environment variables")
        return
    logger.info(f"Populating neo4j DB: Connecting to SQL DB")
    database = db_connect(path=cache)
    if database.neo_db:
        logger.info(f"Populating neo4j DB: Populating")
        database.neo_db.populate_DB(database.session)
        logger.info(f"Populating neo4j DB: Complete")
    else:
        logger.warning(
            f"Populating neo4j DB: database.neo_db is None, skipping population"
        )
