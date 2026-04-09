"""
Phase 3 (v3) — incremental embeddings + GA after a successful apply.
"""

from __future__ import annotations

import logging
import os
from typing import List

from application.cmd import cre_main
from application.database import db
from application.prompt_client import prompt_client as prompt_client
from application.utils import db_backend, gap_analysis, redis

logger = logging.getLogger(__name__)


def run_post_apply(
    *,
    collection: db.Node_collection | None = None,
    db_connection_str: str,
    touched_standard_names: List[str],
) -> None:
    if not touched_standard_names:
        return
    coll = collection or db.Node_collection()
    if os.environ.get("CRE_NO_NEO4J") == "1" and not db_connection_str:
        pass
    else:
        try:
            coll = coll.with_graph()
        except Exception as ex:
            logger.debug("with_graph skipped: %s", ex)

    names = sorted(set(touched_standard_names))
    ph = prompt_client.PromptHandler(database=coll)
    if os.environ.get("CRE_NO_GEN_EMBEDDINGS") != "1":
        for name in names:
            try:
                ph.generate_embeddings_for(name)
            except Exception as ex:
                logger.warning("post-apply embeddings for %s: %s", name, ex)

    if db_connection_str and os.environ.get("CRE_NO_CALCULATE_GAP_ANALYSIS") != "1":
        caps = db_backend.detect_backend(db_connection_str)
        if not caps.is_postgres:
            logger.warning(
                "Skipping post-apply GA scheduling because backend is unsupported: %s",
                caps.backend,
            )
            return
        if os.environ.get("CRE_NO_NEO4J") != "1":
            try:
                cre_main.populate_neo4j_db(db_connection_str)
            except Exception as ex:
                logger.warning("post-apply neo4j populate: %s", ex)
        ga_jobs = []
        for importing_name in names:
            try:
                peers = cre_main.resolve_ga_peer_standard_names(coll, importing_name)
            except Exception as ex:
                logger.warning("post-apply GA peers for %s: %s", importing_name, ex)
                peers = []
            ga_jobs.extend(
                cre_main.schedule_gap_analysis_pairs_with_rq(
                    collection=coll,
                    importing_name=importing_name,
                    db_connection_str=db_connection_str,
                    peer_names=peers,
                    skip_neo_populate=True,
                )
            )
        if ga_jobs:
            redis.wait_for_jobs(ga_jobs)
