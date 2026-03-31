from io import StringIO
import csv
import logging
from typing import Optional
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client as prompt_client
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)
import requests

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class CloudNativeSecurityControls(ParserInterface):
    name = "Cloud Native Security Controls"

    def parse(
        self,
        cache: db.Node_collection,
        ph: Optional[prompt_client.PromptHandler],
    ) -> ParseResult:
        resp = requests.get(
            "https://raw.githubusercontent.com/cloud-native-security-controls/controls-catalog/main/controls/controls_catalog.csv"
        )

        if resp.status_code != 200:
            err_str = (
                f"could not retrieve cnsclenges yaml, status code {resp.status_code}"
            )
            logger.fatal(err_str)
            raise RuntimeError(err_str)
        if not ph:
            raise RuntimeError("PromprtHandler instance is uninitialized")
        standard_entries = []
        entries = csv.DictReader(StringIO(resp.text), delimiter=",")
        for entry in entries:
            raw_id = entry.get("ID")
            if raw_id is None:
                continue
            cnsc = defs.Standard(
                description=entry.get("Control Implementation") or "",
                name=self.name,
                section=entry.get("Section") or "",
                sectionID=raw_id,
                subsection=entry.get("Control Title") or "",
                hyperlink="https://github.com/cloud-native-security-controls/controls-catalog/blob/main/controls/controls_catalog.csv#L"
                + str(int(raw_id) + 1),
                version=entry.get("Originating Document") or "",
            )
            existing = cache.get_nodes(
                name=cnsc.name, section=cnsc.section, sectionID=cnsc.sectionID
            )
            if existing:
                existing_node = existing[0]
                if isinstance(existing_node, (defs.Node, defs.CRE)):
                    embeddings = cache.get_embeddings_for_doc(existing_node)
                    if embeddings:
                        logger.info(
                            f"Node {cnsc.todict()} already exists and has embeddings, skipping"
                        )
                        continue
            cnsc_embeddings = ph.get_text_embeddings(cnsc.subsection)
            cnsc.embeddings = cnsc_embeddings
            cnsc.embeddings_text = cnsc.subsection or ""
            cre_id: Optional[str] = ph.get_id_of_most_similar_cre(cnsc_embeddings)
            if not cre_id:
                logger.info(
                    f"could not find an appropriate CRE for Clound Native Security Control {cnsc.section}, findings similarities with standards instead"
                )
                standard_id = ph.get_id_of_most_similar_node(cnsc_embeddings)
                if standard_id:
                    standards = cache.get_nodes(db_id=standard_id)
                    if standards:
                        dbstandard = standards[0]
                        if isinstance(dbstandard, defs.Node):
                            logger.info(
                                f"found an appropriate standard for Cloud Native Security Control {cnsc.section}:{cnsc.subsection}, it is: {dbstandard.name}:{dbstandard.section}"
                            )
                            cres = cache.find_cres_of_node(dbstandard)
                            if cres and cres[0].id:
                                cre_id = cres[0].id
            cre = cache.get_cre_by_db_id(cre_id) if cre_id else None
            if cre:
                cnsc.add_link(
                    defs.Link(document=cre, ltype=defs.LinkTypes.AutomaticallyLinkedTo)
                )
                logger.info(f"successfully stored {cnsc.__repr__()}")
            else:
                logger.info(
                    f"stored {cnsc.__repr__()} but could not link it to any CRE reliably"
                )
            standard_entries.append(cnsc)
        return ParseResult(results={self.name: standard_entries})
