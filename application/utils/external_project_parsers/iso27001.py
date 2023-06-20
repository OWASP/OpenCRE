import logging
import os
from pprint import pprint
from typing import Dict, Any
from application.database import db
from application.defs import cre_defs as defs
import urllib
from application.database.db import dbCREfromCRE
import re
from simplify_docx import simplify
import docx
import tempfile

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

nist_id_re = re.compile("(?P<nist_id>\w\w\-\d+)")


def download_iso_doc(url: str, location: str, filename):
    urllib.request.urlretrieve(url, f"{location}/{filename}")


def extract_iso_table(nist_docx_filename: str):
    # read in a document
    my_doc = docx.Document(nist_docx_filename)

    # coerce to JSON using the standard options
    my_doc_as_json = simplify(my_doc)
    table = ""
    for el in my_doc_as_json.get("VALUE"):
        if el.get("TYPE") == "body":
            for body_el in el.get("VALUE"):
                if (
                    body_el.get("TYPE") == "table"
                    and body_el["VALUE"][0]["VALUE"][0]["VALUE"][0]["VALUE"][0]["VALUE"]
                    == "NIST SP 800-53 CONTROLS"
                ):
                    table = body_el
    return table


def iso_table_to_nist_dict(table, nist_nodes):
    nist_table = {}
    for el in nist_nodes:
        id_match = re.search(nist_id_re, el.section)
        if not id_match:
            continue
        nist_table[id_match.group("nist_id")] = []

    # skip the first row with only 2 cells
    table["VALUE"].pop(0)
    for row in table["VALUE"]:
        cell0_text = row["VALUE"][0]["VALUE"][0]["VALUE"][0]["VALUE"]
        cell2_text = row["VALUE"][2]["VALUE"][0]["VALUE"][0]["VALUE"]
        if cell2_text == "None" or cell2_text == "---":
            continue
        matched = re.search(nist_id_re, cell0_text)
        if matched:
            isos = [x.replace("*", "").strip() for x in cell2_text.split(",")]
            nist_table[matched.group("nist_id")].extend(isos)
            logger.debug(
                f"Found ISOs {cell2_text} linked to NIST " + matched.group("nist_id")
            )
    return nist_table


def parse_iso(url: str, cache: db.Node_collection):
    nist_nodes = cache.get_nodes(name="NIST 800-53 v5")

    tmpdir = tempfile.mkdtemp()
    download_iso_doc(url, tmpdir, "iso.docx")
    table = extract_iso_table(f"{tmpdir}/iso.docx")
    nist_dict = iso_table_to_nist_dict(table, nist_nodes)

    nist_id_to_node_map = {}
    for node in nist_nodes:
        id_match = re.search(nist_id_re, node.section)
        if not id_match:
            continue
        nist_id_to_node_map[id_match.group("nist_id")] = node
    for nist, isos in nist_dict.items():
        if not isos:
            continue
        node = nist_id_to_node_map.get(nist)
        node_cres = [
            dbCREfromCRE(c.document)
            for c in node.links
            if c.document.doctype == defs.Credoctypes.CRE
        ]
        for iso in isos:
            if not iso:
                continue
            stand = cache.add_node(defs.Standard(name="ISO 27001", section=iso))
            for cre in node_cres:
                logger.debug(f"Added link between ISO {iso} and CRE {cre.external_id}")
                cache.add_link(
                    cre=cre,
                    node=stand,
                    type=defs.LinkTypes.LinkedTo,
                )

    # nist_map = make_nist_map(cache)
    # re_nist = re.compile("(\w+-\d+)")

    # for ccm_mapping in ccmFile.get("0.ccmv4"):
    #     # cre: defs.CRE
    #     # linked_standard: defs.Standard
    #     if "Control ID" not in ccm_mapping:
    #         logger.error("string 'CCM V4.0 Control ID' was not found in mapping line")
    #         continue

    #     ccm = defs.Standard(
    #         name="Cloud Controls Matrix v4.0",
    #         section=f'{ccm_mapping.pop("Control ID")}:{ccm_mapping.pop("Control Title")}',
    #         subsection="",
    #         version="v4.0",
    #         hyperlink="",
    #     )
    #     dbccm = cache.add_node(ccm)
    #     logger.debug(f"Registered CCM with id {ccm.section}")

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
    #                 cache.add_link(cre=dbCREfromCRE(cre=c), node=dbccm)
    #                 logger.debug(
    #                     f"Added link between CRE {c.id} and CCM v4.0 {dbccm.section}"
    #                 )
