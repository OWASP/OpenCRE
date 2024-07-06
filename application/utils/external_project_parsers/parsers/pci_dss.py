from pprint import pprint
import logging
import os
from typing import Dict, Any
from application.database import db
from application.defs import cre_defs as defs
import re
from application.utils import spreadsheet as sheet_utils
from application.prompt_client import prompt_client as prompt_client
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class PciDss(ParserInterface):
    name = "PCI DSS"

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        entries = self.parse_4(
            pci_file=sheet_utils.read_spreadsheet(
                alias="",
                url="https://docs.google.com/spreadsheets/d/18weo-qbik_C7SdYq7FSP2OMgUmsWdWWI1eaXcAfMz8I",
                parse_numbered_only=False,
            ),
            cache=cache,
        )
        return ParseResult(results={self.name: entries})

    def __parse(
        self,
        pci_file: Dict[str, Any],
        cache: db.Node_collection,
        version: str,
        pci_file_tab: str,
        standard_to_spreadsheet_mappings: Dict[str, str],
    ):
        prompt = prompt_client.PromptHandler(cache)
        standard_entries = []
        for row in pci_file.get(pci_file_tab):
            pci_control = defs.Standard(
                name=self.name,
                section=re.sub(
                    "([CUSTOMIZED APPROACH OBJECTIVE]:.*)",
                    "",
                    str(row.get(standard_to_spreadsheet_mappings["section"], "")),
                ).strip(),
                sectionID=str(
                    row.get(standard_to_spreadsheet_mappings["sectionID"], "")
                ).strip(),
                description=str(
                    row.get(standard_to_spreadsheet_mappings["description"], "")
                ).strip(),
                version=version,
            )
            existing = cache.get_nodes(
                name=pci_control.name,
                section=pci_control.section,
                sectionID=pci_control.sectionID,
            )
            if existing:
                embeddings = cache.get_embeddings_for_doc(existing[0])
                if embeddings:
                    logger.info(
                        f"Node {pci_control.todict()} already exists and has embeddings, skipping"
                    )

            control_embeddings = prompt.get_text_embeddings(pci_control.__repr__())
            pci_control.embeddings = control_embeddings
            pci_control.embeddings_text = pci_control.__repr__()
            # these embeddings are different to the ones generated from --generate embeddings, this is because we want these embedding to include the optional "description" field, it is not a big difference and cosine similarity works reasonably accurately without it but good to have
            cre_id = prompt.get_id_of_most_similar_cre(control_embeddings)
            if not cre_id:
                logger.info(
                    f"could not find an appropriate CRE for pci {pci_control.section}, findings similarities with standards instead"
                )
                standard_id = prompt.get_id_of_most_similar_node(control_embeddings)
                dbstandard = cache.get_node_by_db_id(standard_id)
                logger.info(
                    f"found an appropriate standard for pci {pci_control.section}, it is: {dbstandard.section}"
                )
                cres = cache.find_cres_of_node(dbstandard)
                if cres:
                    cre_id = cres[0].id
            if cre_id:
                cre = cache.get_cre_by_db_id(cre_id)
            ctrl_copy = pci_control.shallow_copy()
            pci_control.description = ""
            if cre:
                pci_control.add_link(
                    defs.Link(document=cre, ltype=defs.LinkTypes.AutomaticallyLinkedTo)
                )
                pci_control.add_link(
                    defs.Link(ltype=defs.LinkTypes.AutomaticallyLinkedTo, document=cre)
                )
                logger.info(f"successfully stored {pci_control.__repr__()}")
            else:
                logger.info(
                    f"stored pci control: {pci_control.__repr__()} but could not link it to any CRE reliably"
                )
            standard_entries.append(pci_control)
        return standard_entries

    def parse_3_2(self, pci_file: Dict[str, Any], cache: db.Node_collection):
        self.__parse(
            pci_file=pci_file,
            cache=cache,
            version="3.2",
            pci_file_tab="Table 1 (3)",
            standard_to_spreadsheet_mappings={
                "section": "Control Description",
                "sectionID": "CID",
                "description": "Requirement Description",
            },
        )

    def parse_4(self, pci_file: Dict[str, Any], cache: db.Node_collection):
        return self.__parse(
            pci_file=pci_file,
            cache=cache,
            version="4",
            pci_file_tab="Original Content",
            standard_to_spreadsheet_mappings={
                "section": "Defined Approach Requirements",
                "sectionID": "PCI DSS ID",
                "description": "Requirement Description",
            },
        )
