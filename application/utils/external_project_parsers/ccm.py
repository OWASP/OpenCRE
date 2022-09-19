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
        return

    for nst in nist:
        ri = re_id.search(nst.section)
        if ri:
            nist_map[ri.group("id")] = nst
    return nist_map


#  This has a bug on the received file, it's not a list of dicts with header mapping to a value but somehow a list of str
def parse_ccm(file:  Dict[str, Any], cache: db.Node_collection):
    nist_map = make_nist_map(cache)
    
    for ccm_mapping in file.get('0. ccmv3'):
        # cre: defs.CRE
        # linked_standard: defs.Standard
        pprint(ccm_mapping)
        input()
        if "CCM V3.0 Control ID" not in ccm_mapping:
            continue
    
        ccm = defs.Standard(
            name="Cloud Controls Matrix",
            section=ccm_mapping.pop("CCM V3.0 Control ID"),
            subsection="",
            version="v3",
            hyperlink="",
        )
        dbccm = cache.add_node(ccm)
        logger.debug(f"Registered CCM with id {ccm.section}")

        if ccm_mapping.get("NIST SP800-53 R3"):
            nist_links = ccm_mapping.pop("NIST SP800-53 R3").split("\n")
            pprint(nist_links)
            input()

            for nl in nist_links:
                if nl not in nist_map:
                    logger.error(f"could not find NIST {nl} in the database")
                    continue
                relevant_cres = [
                    el
                    for el in nist_map.get(nl)
                    if el.document.doctype == defs.Credoctypes.CRE
                ]
                pprint(relevant_cres)
                input()
                
                for c in relevant_cres:
                    cache.add_link(cre=dbCREfromCRE(cre=c), node=dbccm)
                    logger.debug(
                        f"Added link between CRE {c.id} and CCM v3.0 {dbccm.section}"
                    )
