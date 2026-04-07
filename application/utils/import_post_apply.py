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
        if os.environ.get("CRE_NO_NEO4J") != "1":
            try:
                cre_main.populate_neo4j_db(db_connection_str)
            except Exception as ex:
                logger.warning("post-apply neo4j populate: %s", ex)
        for name in names:
            try:
                cre_main.schedule_gap_analysis_importing_vs_peers(
                    collection=coll,
                    importing_name=name,
                    db_connection_str=db_connection_str,
                    skip_neo_populate=True,
                )
            except Exception as ex:
                logger.warning("post-apply GA scheduling for %s: %s", name, ex)
