import logging
import os
import tempfile
import json
from pathlib import Path
import requests
from typing import Dict, List
from application.database import db
from application.defs import cre_defs as defs
import shutil
import xmltodict
from application.prompt_client import prompt_client
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class CWE(ParserInterface):
    name = "CWE"
    cwe_zip = "https://cwe.mitre.org/data/xml/cwec_latest.xml.zip"
    fallback_mapping_path = (
        Path(__file__).resolve().parent.parent / "data" / "cwe_fallback_mappings.json"
    )

    def __init__(self) -> None:
        self.fallback_cre_by_match = self.load_fallback_cre_mappings()

    def load_fallback_cre_mappings(self) -> List[tuple[tuple[str, ...], str]]:
        with self.fallback_mapping_path.open("r", encoding="utf-8") as mapping_file:
            raw_mappings = json.load(mapping_file)

        mappings = []
        for entry in raw_mappings:
            keywords = tuple(keyword.lower() for keyword in entry["keywords"])
            mappings.append((keywords, entry["cre_id"]))
        return mappings

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        response = requests.get(self.cwe_zip, stream=True)
        tmp_dir = tempfile.mkdtemp()
        handle, fname = tempfile.mkstemp(suffix=".zip", dir=tmp_dir)

        with open(handle, "wb") as zipfile:
            for chunk in response.iter_content(chunk_size=512):
                if chunk:  # filter out keep-alive new chunks
                    zipfile.write(chunk)

        shutil.unpack_archive(fname, tmp_dir)
        for _, _, files in os.walk(tmp_dir, topdown=False):
            for file in files:
                if file.startswith("cwe") and file.endswith(".xml"):
                    docs = self.register_cwe(
                        xml_file=os.path.join(tmp_dir, file), cache=cache
                    )
                    results = {self.name: docs}
                    base_parser_defs.validate_classification_tags(results)
                    return ParseResult(
                        results=results,
                        calculate_gap_analysis=False,
                    )
        raise RuntimeError("there is no file named cwe.xml in the target zip")

    def make_hyperlink(self, cwe_id: int):
        return f"https://cwe.mitre.org/data/definitions/{cwe_id}.html"

    def link_cwe_to_capec_cre(
        self, cwe: defs.Standard, cache: db.Node_collection, capec_id: str
    ) -> defs.Standard:
        capecs = cache.get_nodes(name="CAPEC", sectionID=capec_id)
        if capecs:
            for cre in [
                c.document
                for c in capecs[0].links
                if c.document.doctype == defs.Credoctypes.CRE
            ]:
                logger.debug(
                    f"linked CWE with id {cwe.sectionID} to CRE with ID {cre.id}"
                )
                cwe.add_link(
                    defs.Link(document=cre, ltype=defs.LinkTypes.AutomaticallyLinkedTo)
                )
        return cwe

    def link_to_related_cwe(
        self, cwe: defs.Standard, cache: db.Node_collection, related_id: str
    ) -> defs.Standard:
        related_cwes = cache.get_nodes(name="CWE", sectionID=related_id)
        if related_cwes:
            return self.link_to_related_cwe_entry(cwe, related_cwes[0])
        return cwe

    def link_to_related_cwe_entry(
        self, cwe: defs.Standard, related_cwe: defs.Standard
    ) -> defs.Standard:
        for cre in [
            link.document
            for link in related_cwe.links
            if link.document.doctype == defs.Credoctypes.CRE
        ]:
            logger.debug(f"linked CWE with id {cwe.sectionID} to CRE with ID {cre.id}")
            autolink = defs.Link(
                document=cre, ltype=defs.LinkTypes.AutomaticallyLinkedTo
            )
            if not cwe.has_link(autolink):
                cwe.add_link(autolink)
        return cwe

    def collect_related_weakness_ids(self, weakness: Dict) -> List[str]:
        related_ids = []
        related_weaknesses = weakness.get("Related_Weaknesses")
        if not related_weaknesses:
            return related_ids

        containers = (
            related_weaknesses
            if isinstance(related_weaknesses, list)
            else [related_weaknesses]
        )
        for container in containers:
            if not isinstance(container, Dict):
                continue
            related_entries = container.get("Related_Weakness")
            if not related_entries:
                continue
            related_entries = (
                related_entries
                if isinstance(related_entries, list)
                else [related_entries]
            )
            for entry in related_entries:
                if isinstance(entry, Dict) and entry.get("@CWE_ID"):
                    related_ids.append(str(entry["@CWE_ID"]))
        return related_ids

    def apply_fallback_cre_mapping(
        self, cwe: defs.Standard, cache: db.Node_collection
    ) -> defs.Standard:
        if any(link.document.doctype == defs.Credoctypes.CRE for link in cwe.links):
            return cwe

        section_text = (cwe.section or "").lower()
        for keywords, cre_id in self.fallback_cre_by_match:
            if not any(keyword in section_text for keyword in keywords):
                continue

            matching_cres = cache.get_CREs(external_id=cre_id)
            if not matching_cres:
                continue

            fallback_link = defs.Link(
                document=matching_cres[0], ltype=defs.LinkTypes.AutomaticallyLinkedTo
            )
            if not cwe.has_link(fallback_link):
                cwe.add_link(fallback_link)
            return cwe

        return cwe

    # cwe is a special case because it already partially exists in our spreadsheet
    # register should, instead of linking Just find the existing CWEs, update them with relevant info and update the relationships between CRE and CWE
    # let's make CAPEC optional and by default off for now
    def register_cwe(self, cache: db.Node_collection, xml_file: str):
        statuses = {}
        entries = []
        entries_by_id = {}
        related_ids_by_cwe = {}
        with open(xml_file, "r") as xml:
            weakness_catalog = xmltodict.parse(xml.read()).get("Weakness_Catalog")
        for _, weaknesses in weakness_catalog.get("Weaknesses").items():
            for weakness in weaknesses:
                statuses[weakness["@Status"]] = 1
                cwe = None
                if weakness["@Status"] in [
                    "Stable",
                    "Incomplete",
                    "Draft",
                    "PROHIBITED",
                ]:
                    cwes = cache.get_nodes(self.name, sectionID=weakness["@ID"])
                    if cwes:  # update the CWE in the database
                        cwe = cwes[0]
                        cwe.section = weakness["@Name"]
                        cwe.hyperlink = self.make_hyperlink(weakness["@ID"])
                        cache.add_node(
                            cwe,
                            comparison_skip_attributes=[
                                "link",
                                "section",
                                "version",
                                "subsection",
                                "tags",
                                "description",
                            ],
                        )
                    else:  # we found something new
                        cwe = defs.Standard(
                            name="CWE",
                            sectionID=weakness["@ID"],
                            section=weakness["@Name"],
                            hyperlink=self.make_hyperlink(weakness["@ID"]),
                            tags=base_parser_defs.build_tags(
                                family=base_parser_defs.Family.TAXONOMY,
                                subtype=base_parser_defs.Subtype.RISK_LIST,
                                audience=base_parser_defs.Audience.DEVELOPER,
                                maturity=base_parser_defs.Maturity.STABLE,
                                source="cwe",
                                extra=[],
                            ),
                        )
                    logger.debug(f"Registered CWE with id {cwe.sectionID}")

                    if weakness.get("Related_Attack_Patterns") and os.environ.get(
                        "CRE_LINK_CWE_THROUGH_CAPEC"
                    ):
                        for lst in weakness["Related_Attack_Patterns"].values():
                            for capec_entry in lst:
                                if isinstance(capec_entry, Dict):
                                    for _, capec_id in capec_entry.items():
                                        cwe = self.link_cwe_to_capec_cre(
                                            cwe=cwe, cache=cache, capec_id=capec_id
                                        )
                                else:
                                    id = lst["@CAPEC_ID"]
                                    cwe = self.link_cwe_to_capec_cre(
                                        cwe=cwe, cache=cache, capec_id=id
                                    )
                    else:
                        logger.info(
                            f"CWE '{cwe.sectionID}-{cwe.section}' does not have any related CAPEC attack patterns, skipping automated linking"
                        )
                    entries.append(cwe)
                    entries_by_id[cwe.sectionID] = cwe
                    related_ids_by_cwe[cwe.sectionID] = (
                        self.collect_related_weakness_ids(weakness)
                    )

        changed = True
        while changed:
            changed = False
            for cwe_id, related_ids in related_ids_by_cwe.items():
                cwe = entries_by_id[cwe_id]
                before_count = len(cwe.links)
                for related_id in related_ids:
                    related_cwe = entries_by_id.get(related_id)
                    if related_cwe:
                        cwe = self.link_to_related_cwe_entry(cwe, related_cwe)
                    else:
                        cwe = self.link_to_related_cwe(
                            cwe=cwe, cache=cache, related_id=related_id
                        )
                entries_by_id[cwe_id] = cwe
                if len(cwe.links) != before_count:
                    changed = True

        for cwe_id, cwe in entries_by_id.items():
            entries_by_id[cwe_id] = self.apply_fallback_cre_mapping(cwe, cache)

        return entries
