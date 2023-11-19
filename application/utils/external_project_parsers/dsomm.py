import re
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
    "Not explicitly covered by ISO 27001",
    "May be part of project management",
    "May be part of risk assessment",
    "Mutual review of source code is not explicitly required in ISO 27001 may be",
    "Mutual security testing is not explicitly required in ISO 27001 may be",
    "War games are not explicitly required in ISO 27001 may be",
    "Security champions are missing in ISO 27001 most likely",
    "Security champions are missing in ISO 27001",
    "ISO 27001:2022 mapping is missing",
    "Security consulting is missing in ISO 27001 may be",
    "Peer review - four eyes principle is not explicitly required by ISO 27001",
    "Hardening is not explicitly covered by ISO 27001 - too specific",
    "Virtual environments are not explicitly covered by ISO 27001 - too specific",
    "{'TODO': \"Incorporate advanced WAF input validation processes into the organization's ISMS.\"}",
    "{'TODO': \"Incorporate advanced WAF input validation processes into the organization's ISMS.\"}",
    "{'TODO': 'Integrate WAF deployment with ISO 27001 controls for system hardening.'}",
    "{'TODO': 'Integrate WAF deployment with ISO 27001 controls for system hardening.'}",
    "{'TODO': 'Identify and implement SAMM security practices relevant to WAF configuration.'}",
    "System hardening is not explicitly covered by ISO 27001 - too specific",
    "vcs usage is not explicitly covered by ISO 27001 - too specific",
    "System hardening, virtual environments are not explicitly covered by ISO 27001 - too specific",
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
                            f"Node {standard.section} already exists and has embeddings, skipping"
                        )
                        continue
                    else:
                        standard_embeddings = prompt.get_text_embeddings(
                            standard.__repr__()
                        )
                        cache.add_embedding(
                            db_object=existing[0],
                            doctype=standard.doctype,
                            embeddings=standard_embeddings,
                            embedding_text=standard.__repr__(),
                        )

                dbstandard = cache.add_node(standard)
                # use SAMM as Glue
                if activity.get("references").get("samm2"):
                    for sectionID in activity.get("references").get("samm2"):
                        if sectionID in means_none:
                            continue
                        samms = cache.get_nodes(name="SAMM", sectionID=f"{sectionID}")
                        if not len(samms):
                            sectionID = re.sub("-\d", "", f"{sectionID}")
                            samms = cache.get_nodes(
                                name="SAMM", sectionID=f"{sectionID}"
                            )
                            if not len(samms):
                                logger.error(
                                    f"could not find samm with sectionID '{sectionID}' in the db"
                                )
                        for samm in samms:
                            for c_link in samm.links:
                                cache.add_link(
                                    cre=db.dbCREfromCRE(c_link.document),
                                    node=dbstandard,
                                    type=defs.LinkTypes.LinkedTo,
                                )
                else:
                    logger.error(f"Activity {aname} does not link to SAMM, using ISO")
                    # use iso as glue
                    if not activity.get("references").get("iso27001-2022"):
                        logger.error(f"Activity {aname} does not link to ISO")
                        return
                    for sectionID in activity.get("references").get("iso27001-2022"):
                        if sectionID in means_none:
                            continue
                        isos = cache.get_nodes(
                            name="ISO 27001", sectionID=f"{sectionID}"
                        )
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
