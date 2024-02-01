from io import StringIO
import csv
import urllib
from pprint import pprint
import logging
import os
from typing import Dict, Any
from application.database import db
from application.defs import cre_defs as defs
import re
from application.utils import spreadsheet as sheet_utils
from application.prompt_client import prompt_client as prompt_client
import requests

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def parse(
    cache: db.Node_collection,
):
    prompt = prompt_client.PromptHandler(cache)
    resp = requests.get(
        "https://raw.githubusercontent.com/cloud-native-security-controls/controls-catalog/main/controls/controls_catalog.csv"
    )

    if resp.status_code != 200:
        logger.fatal(
            f"could not retrieve cnsclenges yaml, status code {resp.status_code}"
        )
        return
    entries = csv.DictReader(StringIO(resp.text), delimiter=",")
    for entry in entries:
        cnsc = defs.Standard(
            description=entry.get("Control Implementation"),
            name="Cloud Native Security Controls",
            section=entry.get("Section"),
            sectionID=entry.get("ID"),
            subsection=entry.get("Control Title"),
            hyperlink="https://github.com/cloud-native-security-controls/controls-catalog/blob/main/controls/controls_catalog.csv#L"
            + str(int(entry.get("ID")) + 1),
            version=entry.get("Originating Document"),
        )
        existing = cache.get_nodes(
            name=cnsc.name, section=cnsc.section, sectionID=cnsc.sectionID
        )
        if existing:
            embeddings = cache.get_embeddings_for_doc(existing[0])
            if embeddings:
                logger.info(
                    f"Node {cnsc.todict()} already exists and has embeddings, skipping"
                )
                continue
        cnsc_embeddings = prompt.get_text_embeddings(cnsc.subsection)
        cre_id = prompt.get_id_of_most_similar_cre(cnsc_embeddings)
        if not cre_id:
            logger.info(
                f"could not find an appropriate CRE for Clound Native Security Control {cnsc.section}, findings similarities with standards instead"
            )
            standard_id = prompt.get_id_of_most_similar_node(cnsc_embeddings)
            dbstandard = cache.get_node_by_db_id(standard_id)
            logger.info(
                f"found an appropriate standard for Cloud Native Security Control {cnsc.section}:{cnsc.subsection}, it is: {dbstandard.name}:{dbstandard.section}"
            )
            cres = cache.find_cres_of_node(dbstandard)
            if cres:
                cre_id = cres[0].id
        cre = cache.get_cre_by_db_id(cre_id)
        cnsc_copy = cnsc.shallow_copy()
        cnsc_copy.description = ""
        dbnode = cache.add_node(cnsc_copy)
        if not dbnode:
            logger.error(f"could not store database node {cnsc_copy.__repr__()}")
            continue
        cache.add_embedding(
            dbnode, cnsc_copy.doctype, cnsc_embeddings, cnsc_copy.__repr__()
        )
        if cre:
            cache.add_link(db.dbCREfromCRE(cre), dbnode)
            logger.info(f"successfully stored {cnsc_copy.__repr__()}")
        else:
            logger.info(
                f"stored {cnsc_copy.__repr__()} but could not link it to any CRE reliably"
            )
