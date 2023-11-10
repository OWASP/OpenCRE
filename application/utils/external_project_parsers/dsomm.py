import yaml
import urllib
from pprint import pprint
import logging
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client as prompt_client
import requests

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

means_none = [
    "Not explicitly covered by ISO 27001 - too specific",
    "May be part of project management",
    "May be part of risk assessment",
]


def parse(
    cache: db.Node_collection,
):
    prompt = prompt_client.PromptHandler(cache)
    resp = requests.get(
        "https://raw.githubusercontent.com/devsecopsmaturitymodel/DevSecOps-MaturityModel-data/main/src/assets/YAML/generated/generated.yaml"
    )

    if resp.status_code != 200:
        logger.fatal(f"could not retrieve dsomm yaml, status code {resp.status_code}")
        return
    dsomm = yaml.safe_load(resp.text)
    for _, dimension in dsomm.items():
        for sname, subdimension in dimension.items():
            for aname, activity in subdimension.items():
                standard = None
                if activity.get("uuid"):
                    standard = defs.Standard(
                        name="DevSecOps Maturity Model (DSOMM)",
                        section=sname,
                        subsection=aname,
                        sectionID=activity.get("uuid"),
                        hyperlink=f"https://dsomm.owasp.org/activity-description?action={activity.get('uuid')}",
                        description=f"Description:{activity.get('description')}\n Risk:{activity.get('risk')}\n Measure:{activity.get('measure')}",
                    )
                else:
                    logger.error(f"Activity {aname} does not have uuid")
                    return

                existing = cache.get_nodes(
                    name=standard.name,
                    section=standard.section,
                    sectionID=f"{standard.sectionID}",
                )
                if existing:
                    embeddings = cache.get_embeddings_for_doc(existing[0])
                    if embeddings:
                        logger.info(
                            f"Node {standard.todict()} already exists and has embeddings, skipping"
                        )
                        continue
                    else:
                        standard_embeddings = prompt.get_text_embeddings(
                            standard.__repr__
                        )
                        cache.add_embedding(
                            doctype=standard.doctype,
                            embeddings=standard_embeddings,
                            embedding_text=standard.__repr__,
                        )

                dbstandard = cache.add_node(standard)
                # use iso as glue
                if not activity.get("references").get("iso27001-2022"):
                    logger.error(f"Activity {aname} does not link to iso")
                    return
                for sectionID in activity.get("references").get("iso27001-2022"):
                    if sectionID in means_none:
                        continue
                    isos = cache.get_nodes(name="ISO 27001", sectionID=f"{sectionID}")
                    if not len(isos):
                        logger.error(
                            f"could not find iso with sectionID '{sectionID}' in the db"
                        )
                        return
                    for iso in isos:
                        for c_link in iso.links:
                            cache.add_link(
                                cre=db.dbCREfromCRE(c_link.document),
                                node=dbstandard,
                                type=defs.LinkTypes.LinkedTo,
                            )
