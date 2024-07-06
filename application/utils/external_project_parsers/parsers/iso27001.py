import logging
import os
from pprint import pprint
from typing import Dict, Any
from application.database import db
from application.defs import cre_defs as defs
import urllib
import re
import tempfile
from application.prompt_client import prompt_client as prompt_client
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)
from typing import List

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

nist_id_re = re.compile("(?P<nist_id>\w\w\-\d+)")


class ISO27001(ParserInterface):
    """
    Parses ISO using NIST's 800-53 to ISO mappings sheet and NIST 800-53 as a glue
    """

    name = "ISO 27001"
    url = "https://csrc.nist.rip/CSRC/media/Publications/sp/800-53/rev-5/final/documents/sp800-53r5-to-iso-27001-mapping.docx"

    # def download_iso_doc(self, url: str, location: str, filename):
    #     urllib.request.urlretrieve(url, f"{location}/{filename}")

    # def extract_iso_table(self, nist_docx_filename: str):
    #     # read in a document
    #     my_doc = docx.Document(nist_docx_filename)

    #     # coerce to JSON us                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               ing the standard options
    #     my_doc_as_json = simplify(my_doc)
    #     table = ""
    #     for el in my_doc_as_json.get("VALUE"):
    #         if el.get("TYPE") == "body":
    #             for body_el in el.get("VALUE"):
    #                 if (
    #                     body_el.get("TYPE") == "table"
    #                     and body_el["VALUE"][0]["VALUE"][0]["VALUE"][0]["VALUE"][0][
    #                         "VALUE"
    #                     ]
    #                     == "NIST SP 800-53 CONTROLS"
    #                 ):
    #                     table = body_el
    #     return table

    # def iso_table_to_nist_dict(self, table, nist_nodes):
    #     nist_table = {}
    #     for el in nist_nodes:
    #         id_match = re.search(nist_id_re, el.section)
    #         if not id_match:
    #             continue
    #         nist_table[id_match.group("nist_id")] = []

    #     # skip the first row with only 2 cells
    #     table["VALUE"].pop(0)
    #     for row in table["VALUE"]:
    #         cell0_text = row["VALUE"][0]["VALUE"][0]["VALUE"][0]["VALUE"]
    #         cell2_text = row["VALUE"][2]["VALUE"][0]["VALUE"][0]["VALUE"]
    #         if cell2_text == "None" or cell2_text == "---":
    #             continue
    #         matched = re.search(nist_id_re, cell0_text)
    #         if matched:
    #             isos = [x.replace("*", "").strip() for x in cell2_text.split(",")]
    #             nist_table[matched.group("nist_id")].extend(isos)
    #             logger.debug(
    #                 f"Found ISOs {cell2_text} linked to NIST "
    #                 + matched.group("nist_id")
    #             )
    #     return nist_table

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        return ParseResult(
            results={self.name: []}
        )  # the doc above does not have names we get the names from the spreadsheet for now, disable
        # url = self.url
        # documents: List[defs.Standard] = []
        # nist_nodes = cache.get_nodes(name="NIST 800-53 v5")

        # tmpdir = tempfile.mkdtemp()
        # self.download_iso_doc(url, tmpdir, "iso.docx")
        # table = self.extract_iso_table(f"{tmpdir}/iso.docx")
        # nist_dict = self.iso_table_to_nist_dict(table, nist_nodes)
        # nist_id_to_node_map = {}
        # for node in nist_nodes:
        #     id_match = re.search(nist_id_re, node.section)
        #     if not id_match:
        #         continue
        #     nist_id_to_node_map[id_match.group("nist_id")] = node
        # for nist, isos in nist_dict.items():
        #     if not isos:
        #         continue
        #     node = nist_id_to_node_map.get(nist)
        #     for iso in isos:
        #         if not iso:
        #             continue
        #         stand = defs.Standard(name=self.name, section=iso)
        #         [stand.add_link(link) for link in node.links]
        #         documents.append(stand)
        # return {self.name: documents}
