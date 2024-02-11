import yaml
import urllib
from pprint import pprint
import logging
import os
from typing import Dict, Any
from application.database import db
from application.defs import cre_defs as defs
import re
from application.prompt_client import prompt_client as prompt_client
from application.utils.external_project_parsers.base_parser import ParserInterface
import requests

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class JuiceShop(ParserInterface):
    name = "OWASP Juice Shop"
    url = "https://raw.githubusercontent.com/juice-shop/juice-shop/master/data/static/challenges.yml"

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        resp = requests.get(self.url)

        if resp.status_code != 200:
            logger.fatal(
                f"could not retrieve challenges yaml, status code {resp.status_code}"
            )
            return
        challenges = yaml.safe_load(resp.text)
        chals = []
        for challenge in challenges:
            chal = defs.Tool(
                description=challenge["description"],
                name=self.name,
                section=challenge["name"],
                sectionID=challenge["key"],
                hyperlink="https://demo.owasp-juice.shop//#/score-board?searchQuery="
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
            challenge_embeddings = ph.get_text_embeddings(",".join(chal.tags))
            chal.embeddings = challenge_embeddings
            chal.embeddings_text = ",".join(chal.tags)

            cre_id = ph.get_id_of_most_similar_cre(challenge_embeddings)
            if not cre_id:
                logger.info(
                    f"could not find an appropriate CRE for Juiceshop challenge {chal.section}, findings similarities with standards instead"
                )
                standard_id = ph.get_id_of_most_similar_node(challenge_embeddings)
                dbstandard = cache.get_node_by_db_id(standard_id)
                logger.info(
                    f"found an appropriate standard for Juiceshop challenge {chal.section}, it is: {dbstandard.section}"
                )
                cres = cache.find_cres_of_node(dbstandard)
                if cres:
                    cre_id = cres[0].id

            cre = cache.get_cre_by_db_id(cre_id)
            if cre:
                chal.add_link(defs.Link(document=cre, ltype=defs.LinkTypes.LinkedTo))
                logger.info(f"successfully stored {chal.__repr__()}")
            else:
                logger.info(
                    f"stored {chal.__repr__()} but could not link it to any CRE reliably"
                )
            chals.append(chal)
        return chals
