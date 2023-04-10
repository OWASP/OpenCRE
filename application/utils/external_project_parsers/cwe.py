import logging
import os
from pprint import pprint
import tempfile
import requests
from typing import Dict
from application.database import db
from application.defs import cre_defs as defs
from typing import Any, Dict, List, Optional, Tuple, cast
import shutil
import xmltodict

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def parse_cwe(cache: db.Node_collection):
    cwe_zip = "https://cwe.mitre.org/data/xml/cwec_latest.xml.zip"
    response = requests.get(cwe_zip, stream=True)
    tmp_dir = tempfile.mkdtemp(suffix=".zip")
    handle, fname = tempfile.mkstemp(suffix=".zip", dir=tmp_dir)

    with open(handle, "wb") as zipfile:
        for chunk in response.iter_content(chunk_size=512):
            if chunk:  # filter out keep-alive new chunks
                zipfile.write(chunk)

    shutil.unpack_archive(fname, tmp_dir)
    for root, dirs, files in os.walk(tmp_dir, topdown=False):
        for file in files:
            if file.startswith("cwe") and file.endswith(".xml"):
                register_cwe(xml_file=os.path.join(tmp_dir, file), cache=cache)


def make_hyperlink(cwe_id: int):
    return f"https://cwe.mitre.org/data/definitions/{cwe_id}.html"


def link_cwe_to_capec_cre(
    cwe: db.Node, cache: db.Node_collection, capec_id: str
) -> bool:
    capecs = cache.get_nodes(name="CAPEC", sectionID=capec_id)
    linked = False
    if capecs:
        for cre in [
            c.document
            for c in capecs[0].links
            if c.document.doctype == defs.Credoctypes.CRE
        ]:
            logger.debug(f"linked CWE with id {cwe.section_id} to CRE with ID {cre.id}")
            cache.add_link(cre=db.dbCREfromCRE(cre), node=cwe)
            linked = True
    return linked


def link_to_related_weaknesses(
    cwe: db.Node, cache: db.Node_collection, related_id: str
) -> bool:
    related_cwes = cache.get_nodes(name="CWE", sectionID=related_id)
    linked = False
    if related_cwes:
        for cre in [
            c.document
            for c in related_cwes[0].links
            if c.document.doctype == defs.Credoctypes.CRE
        ]:
            logger.debug(f"linked CWE with id {cwe.section_id} to CRE with ID {cre.id}")
            cache.add_link(cre=db.dbCREfromCRE(cre), node=cwe)
            linked = True
    return linked


def register_cwe(cache: db.Node_collection, xml_file: str):
    statuses = {}

    with open(xml_file, "r") as xml:
        weakness_catalog = xmltodict.parse(xml.read()).get("Weakness_Catalog")
        version = weakness_catalog["@Version"]
    for _, weaknesses in weakness_catalog.get("Weaknesses").items():
        for weakness in weaknesses:
            statuses[weakness["@Status"]] = 1
            if weakness["@Status"] in ["Stable", "Incomplete", "Draft"]:
                cwe = defs.Standard(
                    name="CWE",
                    sectionID=weakness["@ID"],
                    section=weakness["@Name"],
                    hyperlink=make_hyperlink(weakness["@ID"]),
                    version=version,
                )
                dbcwe = cache.add_node(
                    cwe, comparison_skip_attributes=["link", "section","version"]
                )
                logger.debug(f"Registered CWE with id {cwe.section}")
                link_found = False
                if weakness.get("Related_Attack_Patterns"):
                    for lst in weakness["Related_Attack_Patterns"].values():
                        for capec_entry in lst:
                            if isinstance(capec_entry, Dict):
                                for _, capec_id in capec_entry.items():
                                    link_found = link_cwe_to_capec_cre(
                                        cwe=dbcwe, cache=cache, capec_id=capec_id
                                    )
                            else:
                                id = lst["@CAPEC_ID"]
                                link_found = link_cwe_to_capec_cre(
                                    cwe=dbcwe, cache=cache, capec_id=id
                                )
                else:
                    logger.info(
                        f"CWE '{cwe.sectionID}-{cwe.section}' does not have any related CAPEC attack patterns, skipping automated linking"
                    )
                if not link_found and weakness.get("Related_Weaknesses"):
                    for lst in weakness["Related_Weaknesses"].values():
                        for cwe_entry in lst:
                            if isinstance(cwe_entry, Dict):
                                id = cwe_entry["@CWE_ID"]
                                link_found = link_to_related_weaknesses(
                                    cwe=dbcwe, cache=cache, related_id=id
                                )
