import yaml
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
        "https://raw.githubusercontent.com/juice-shop/juice-shop/master/data/static/challenges.yml"
    )

    if resp.status_code != 200:
        logger.fatal(
            f"could not retrieve challenges yaml, status code {resp.status_code}"
        )
        return
    challenges = yaml.safe_load(resp.text)
    for challenge in challenges:
        chal = defs.Tool(
            description=challenge["description"],
            name="OWASP Juice Shop",
            section=challenge["name"],
            sectionID=challenge["key"],
            hyperlink="https://demo.owasp-juice.shop//#/score-board?challenge="
            + urllib.parse.quote(challenge["name"]),
            tooltype=defs.ToolTypes.Training,
            tags=[challenge["category"]],
        )

        existing = cache.get_nodes(
            name=chal.name, section=chal.section, sectionID=chal.sectionID
        )
        if existing:
            embeddings = cache.get_embeddings_for_doc(existing[0])
            if embeddings:
                logger.info(
                    f"Node {chal.todict()} already exists and has embeddings, skipping"
                )
                continue
        challenge_embeddings = prompt.get_text_embeddings(",".join(chal.tags))
        cre_id = prompt.get_id_of_most_similar_cre(challenge_embeddings)
        if not cre_id:
            logger.info(
                f"could not find an appropriate CRE for Juiceshop challenge {chal.section}, findings similarities with standards instead"
            )
            standard_id = prompt.get_id_of_most_similar_node(challenge_embeddings)
            dbstandard = cache.get_node_by_db_id(standard_id)
            logger.info(
                f"found an appropriate standard for Juiceshop challenge {chal.section}, it is: {dbstandard.section}"
            )
            cres = cache.find_cres_of_node(dbstandard)
            if cres:
                cre_id = cres[0].id

        cre = cache.get_cre_by_db_id(cre_id)
        chal_copy = chal.shallow_copy()
        chal_copy.description = ""
        dbnode = cache.add_node(chal_copy)
        if not dbnode:
            logger.error(f"could not store database node {chal_copy.__repr__()}")
            continue
        cache.add_embedding(
            dbnode, chal_copy.doctype, challenge_embeddings, chal_copy.__repr__()
        )
        if cre:
            cache.add_link(db.dbCREfromCRE(cre), dbnode)
            logger.info(f"successfully stored {chal_copy.__repr__()}")
        else:
            logger.info(
                f"stored {chal_copy.__repr__()} but could not link it to any CRE reliably"
            )
