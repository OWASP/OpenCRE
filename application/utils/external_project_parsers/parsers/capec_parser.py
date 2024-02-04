import logging
import os
import tempfile
import requests
from typing import Dict
from application.database import db
from application.defs import cre_defs as defs

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from application.utils.external_project_parsers.base_parser import ParserInterface
from application.prompt_client import prompt_client as prompt_client
from application.utils import spreadsheet as sheet_utils


class Capec(ParserInterface):
    name = "CAPEC"

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        capec_xml = "https://capec.mitre.org/data/xml/capec_latest.xml"
        xml = requests.get(capec_xml)
        if xml.status_code == 200:
            handle, fname = tempfile.mkstemp(suffix=".xml")
            with os.fdopen(handle, "w") as xmlfile:
                xmlfile.write(xml.text)

                return self.register_capec(xml_file=fname, cache=cache)
        else:
            logger.fatal(f"Could not get CAPEC's XML data, error was {xml.text}")

    def make_hyperlink(self, capec_id: int):
        return f"https://capec.mitre.org/data/definitions/{capec_id}.html"

    def link_capec_to_cwe_cre(
        self, cache: db.Node_collection, capec: defs.Standard, cwe_id: str
    ) -> defs.Standard:
        cwes = cache.get_nodes(name="CWE", sectionID=cwe_id)
        if cwes:
            for cre in [
                c.document
                for c in cwes[0].links
                if c.document.doctype == defs.Credoctypes.CRE
            ]:
                logger.debug(
                    f"linked CAPEC with id {capec.section} to CRE with ID {cre.id}"
                )
                capec = capec.add_link(
                    defs.Link(document=cre, ltype=defs.LinkTypes.LinkedTo)
                )
        return capec

    def register_capec(self, cache: db.Node_collection, xml_file: str):
        attack_pattern_catalogue = {}
        import xmltodict

        with open(xml_file) as xml:
            attack_pattern_catalogue = xmltodict.parse(xml.read()).get(
                "Attack_Pattern_Catalog"
            )
            version = attack_pattern_catalogue["@Version"]
        standard_entries = []
        for _, attack_pattern in attack_pattern_catalogue.get(
            "Attack_Patterns"
        ).items():
            for pattern in attack_pattern:  # attack_pattern is an array with 1 element
                if pattern["@Status"] in ["Stable", "Usable", "Draft"]:
                    capec = defs.Standard(
                        name="CAPEC",
                        sectionID=pattern["@ID"],
                        section=pattern["@Name"],
                        hyperlink=self.make_hyperlink(pattern["@ID"]),
                        version=version,
                    )
                    logger.debug(f"Registered CAPEC with id {capec.section}")
                    if pattern.get("Related_Weaknesses"):
                        for lst in pattern["Related_Weaknesses"].values():
                            for cwe_entry in lst:
                                if isinstance(cwe_entry, Dict):
                                    for _, cwe_id in cwe_entry.items():
                                        capec = self.link_capec_to_cwe_cre(
                                            capec=capec, cache=cache, cwe_id=cwe_id
                                        )
                                else:
                                    id = lst["@CWE_ID"]
                                    capec = self.link_capec_to_cwe_cre(
                                        capec=capec, cache=cache, cwe_id=id
                                    )
                    else:
                        logger.error(
                            f"CAPEC {capec.section} does not have any related CWE weaknesses, skipping automated linking"
                        )
                    standard_entries.append(capec)
        return standard_entries
