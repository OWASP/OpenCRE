import re
import yaml
import logging
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client as prompt_client
import requests
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DSOMM(ParserInterface):
    name = "DevSecOps Maturity Model (DSOMM)"
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
    manual_mappings = {
        "Usage of feature toggles": "344-611",
        "Usage of edge encryption at transit": "435-702",
    }

    def link_to_samm(self, activity, cache, standard):
        for sectionID in activity.get("references").get("samm2"):
            if sectionID in self.means_none:
                continue
            samms = cache.get_nodes(name="SAMM", sectionID=f"{sectionID}")
            if not len(samms):
                sectionID = re.sub("-\d", "", f"{sectionID}")
                samms = cache.get_nodes(name="SAMM", sectionID=f"{sectionID}")
                if not len(samms):
                    logger.error(
                        f"could not find samm with sectionID '{sectionID}' in the db"
                    )
            for samm in samms:
                for c_link in samm.links:
                    standard = standard.add_link(
                        defs.Link(
                            document=c_link.document,
                            ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                        )
                    )
        return standard

    def link_to_iso(self, aname, activity, cache, standard):
        if not activity.get("references").get("iso27001-2022"):
            logger.error(f"Activity {aname} does not link to ISO")
            return
        for sectionID in activity.get("references").get("iso27001-2022"):
            if sectionID in self.means_none:
                continue
            isos = cache.get_nodes(name="ISO 27001", sectionID=f"{sectionID}")
            if not len(isos):
                logger.error(
                    f"could not find iso with sectionID '{sectionID}' in the db"
                )
                return
            for iso in isos:
                for c_link in iso.links:
                    standard = standard.add_link(
                        defs.Link(
                            document=c_link.document,
                            ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                        )
                    )
        return standard

    def parse(
        self,
        cache: db.Node_collection,
        ph: prompt_client.PromptHandler,
    ):
        resp = requests.get(
            "https://raw.githubusercontent.com/devsecopsmaturitymodel/DevSecOps-MaturityModel-data/main/src/assets/YAML/generated/generated.yaml"
        )
        if resp.status_code != 200:
            err_str = f"could not retrieve dsomm yaml, status code {resp.status_code}"
            logger.fatal(err_str)
            raise RuntimeError(err_str)
        dsomm = yaml.safe_load(resp.text)
        standard_entries = []
        for _, dimension in dsomm.items():
            for sname, subdimension in dimension.items():
                for aname, activity in subdimension.items():
                    standard = None
                    if activity.get("uuid"):
                        standard = defs.Standard(
                            name=self.name,
                            section=sname,
                            subsection=aname,
                            sectionID=activity.get("uuid"),
                            hyperlink=f"https://dsomm.owasp.org/activity-description?action={activity.get('uuid')}",
                            description=f"Description:{activity.get('description')}\n Risk:{activity.get('risk')}\n Measure:{activity.get('measure')}",
                        )
                    else:
                        logger.error(f"Activity {aname} does not have uuid")
                        continue

                    existing = cache.get_nodes(
                        name=standard.name,
                        section=standard.section,
                        sectionID=f"{standard.sectionID}",
                    )
                    if existing:
                        logger.info(
                            f"Node {standard.section} already exists and has embeddings, skipping"
                        )
                        continue

                    if self.manual_mappings.get(aname):
                        cs = cache.get_CREs(self.manual_mappings.get(aname))
                        for c in cs:
                            standard.add_link(
                                defs.Link(
                                    document=c,
                                    ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                                )
                            )
                    # use SAMM as Glue
                    if activity.get("references").get("samm2"):
                        standard = self.link_to_samm(activity, cache, standard)
                        standard_entries.append(standard)
                    else:
                        logger.error(
                            f"Activity {aname} does not link to SAMM, using ISO"
                        )
                        # use iso as glue
                        standard = self.link_to_iso(aname, activity, cache, standard)
                        standard_entries.append(standard)
        return ParseResult(results={self.name: standard_entries})
