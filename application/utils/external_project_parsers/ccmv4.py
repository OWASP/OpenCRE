import logging
import os
from pprint import pprint
from typing import Dict, Any
from application.database import db
from application.defs import cre_defs as defs

from application.database.db import dbCREfromCRE
import re

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def make_nist_map(cache: db.Node_collection):
    nist_map = {}
    re_id = re.compile("(?P<id>\w+-\d+)")

    nist = cache.get_nodes(name="NIST 800-53 v5")
    if not nist:
        logger.fatal("This CRE DB does not contain NIST, this is fatal")
        return

    for nst in nist:
        ri = re_id.search(nst.section)
        if ri:
            nist_map[ri.group("id")] = nst
    return nist_map


def parse_ccm(ccmFile: Dict[str, Any], cache: db.Node_collection):
    nist_map = make_nist_map(cache)
    re_nist = re.compile("(\w+-\d+)")

    for ccm_mapping in ccmFile.get("0.ccmv4"):
        # cre: defs.CRE
        # linked_standard: defs.Standard
        if "Control ID" not in ccm_mapping:
            logger.error("string 'CCM V4.0 Control ID' was not found in mapping line")
            continue

        ccm = defs.Standard(
            name="Cloud Controls Matrix v4.0",
            section=ccm_mapping.pop("Control ID"),
            subsection="",
            version="v4.0",
            hyperlink="",
        )
        dbccm = cache.add_node(ccm)
        logger.debug(f"Registered CCM with id {ccm.section}")

        if ccm_mapping.get("NIST 800-53 rev 5"):
            nist_links = ccm_mapping.pop("NIST 800-53 rev 5").split("\n")

            for nl in nist_links:
                actual = ""
                found = re_nist.search(nl.strip())
                if found:
                    actual = found.group(1)
                if actual not in nist_map.keys():
                    logger.error(
                        f"could not find NIST '{actual}' in the database, mapping was '{nl.strip()}'"
                    )
                    continue
                relevant_cres = [
                    el.document
                    for el in nist_map.get(actual).links
                    if el.document.doctype == defs.Credoctypes.CRE
                ]

                for c in relevant_cres:
                    cache.add_link(cre=dbCREfromCRE(cre=c), node=dbccm)
                    logger.debug(
                        f"Added link between CRE {c.id} and CCM v4.0 {dbccm.section}"
                    )
