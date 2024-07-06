import logging
from typing import Dict, Any
from application.database import db
from application.defs import cre_defs as defs

import re

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)
from application.prompt_client import prompt_client as prompt_client
from application.utils import spreadsheet as sheet_utils


class CloudControlsMatrix(ParserInterface):
    name = "Cloud Controls Matrix"

    # def make_nist_map(self, cache: db.Node_collection):
    #     nist_map = {}
    #     re_id = re.compile("(?P<id>\w+-\d+)")

    #     nist = cache.get_nodes(name="NIST 800-53 v5")
    #     if not nist:
    #         logger.fatal("This CRE DB does not contain NIST, this is fatal")
    #         return

    #     for nst in nist:
    #         ri = re_id.search(nst.section)
    #         if ri:
    #             nist_map[ri.group("id")] = nst
    #     return nist_map

    # def get_ccm_file(self) -> Dict[str, Any]:
    #     return sheet_utils.read_spreadsheet(
    #         alias="",
    #         url="https://docs.google.com/spreadsheets/d/1QDzQy0wt1blGjehyXS3uaHh7k5OOR12AWgAA1DeACyc",
    #     )

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        return {self.name: []}  # disabled
        # ccmFile: Dict[str, Any] = self.get_ccm_file()
        # nist_map = self.make_nist_map(cache)
        # re_nist = re.compile("(\w+-\d+)")
        # standard_entries = []
        # for ccm_mapping in ccmFile.get("0.ccmv4"):
        #     if "Control ID" not in ccm_mapping:
        #         logger.error(
        #             "string 'CCM V4.0 Control ID' was not found in mapping line"
        #         )
        #         continue

        #     ccm = defs.Standard(
        #         name=self.name,
        #         section=f'{ccm_mapping.get("Control ID")}:{ccm_mapping.pop("Control Title")}',
        #         subsection="",
        #         sectionID=ccm_mapping.pop("Control ID"),
        #         version="v4.0",
        #         hyperlink="",
        #     )

        #     if ccm_mapping.get("NIST 800-53 rev 5"):
        #         nist_links = ccm_mapping.pop("NIST 800-53 rev 5").split("\n")

        #         for nl in nist_links:
        #             actual = ""
        #             found = re_nist.search(nl.strip())
        #             if found:
        #                 actual = found.group(1)
        #             if actual not in nist_map.keys():
        #                 logger.error(
        #                     f"could not find NIST '{actual}' in the database, mapping was '{nl.strip()}'"
        #                 )
        #                 continue
        #             relevant_cres = [
        #                 el.document
        #                 for el in nist_map.get(actual).links
        #                 if el.document.doctype == defs.Credoctypes.CRE
        #             ]

        #             for c in relevant_cres:
        #                 ccm.add_link(
        #                     defs.Link(
        #                         document=c, ltype=defs.LinkTypes.AutomaticallyLinkedTo
        #                     )
        #                 )
        #                 logger.debug(
        #                     f"Added link between CRE {c.id} and CCM v4.0 {ccm.section}"
        #                 )
        #     logger.debug(f"Registered CCM with id {ccm.section}")
        #     standard_entries.append(ccm)
        # return {self.name: standard_entries}
