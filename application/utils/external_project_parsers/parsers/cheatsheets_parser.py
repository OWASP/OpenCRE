# script to parse cheatsheet md files find the links to opencre.org and add the cheatsheets to CRE
from typing import List
import subprocess
from application.database import db
from application.utils import git
from application.defs import cre_defs as defs
import os
import re
from application.utils.external_project_parsers import base_parser_defs
import json
from pathlib import Path
import logging
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)
from application.prompt_client import prompt_client as prompt_client


class Cheatsheets(ParserInterface):
    name = "OWASP Cheat Sheets"
    cheatsheetseries_base_url = "https://cheatsheetseries.owasp.org/cheatsheets"
    supplement_data_file = (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "owasp_mappings"
        / "owasp_cheatsheets_supplement.json"
    )
    logger = logging.getLogger(__name__)

    def cheatsheet(
        self, section: str, hyperlink: str, tags: List[str]
    ) -> defs.Standard:
        return defs.Standard(
            name=self.name,
            section=section,
            tags=base_parser_defs.build_tags(
                family=base_parser_defs.Family.GUIDANCE,
                subtype=base_parser_defs.Subtype.CHEATSHEET,
                audience=base_parser_defs.Audience.DEVELOPER,
                maturity=base_parser_defs.Maturity.STABLE,
                source="owasp_cheatsheets",
                extra=tags,
            ),
            hyperlink=hyperlink,
        )

    def official_cheatsheet_url(self, markdown_filename: str) -> str:
        html_name = os.path.splitext(markdown_filename)[0] + ".html"
        return f"{self.cheatsheetseries_base_url}/{html_name}"

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        c_repo = "https://github.com/OWASP/CheatSheetSeries.git"
        cheatsheets_path = "cheatsheets/"
        cheatsheets = []
        repo = None
        try:
            repo = git.clone(c_repo, sparse_paths=["cheatsheets"], sparse_cone=True)
        except (subprocess.SubprocessError, OSError) as exc:
            self.logger.warning(
                "Unable to clone OWASP CheatSheetSeries, continuing with supplemental cheat sheets only: %s",
                exc,
            )
        if repo:
            cheatsheets = self.register_cheatsheets(
                repo=repo,
                cache=cache,
                cheatsheets_path=cheatsheets_path,
                repo_path=c_repo,
            )
        cheatsheets.extend(self.register_supplemental_cheatsheets(cache=cache))
        cheatsheets = self.deduplicate_entries(cheatsheets)
        results = {self.name: cheatsheets}
        base_parser_defs.validate_classification_tags(results)
        return ParseResult(results=results)

    def register_cheatsheets(
        self, cache: db.Node_collection, repo, cheatsheets_path, repo_path
    ):
        title_regexp = r"# (?P<title>.+)"
        cre_link = r"(https://www\.)?opencre.org/cre/(?P<cre>\d+-\d+)"
        files = os.listdir(os.path.join(repo.working_dir, cheatsheets_path))
        standard_entries = []
        for mdfile in files:
            pth = os.path.join(repo.working_dir, cheatsheets_path, mdfile)
            name = None

            with open(pth) as mdf:
                mdtext = mdf.read()
                if "opencre.org" not in mdtext:
                    continue
                title = re.search(title_regexp, mdtext)
                cre = re.search(cre_link, mdtext)
                if cre and title:
                    name = title.group("title")
                    cre_id = cre.group("cre")
                    cres = cache.get_CREs(external_id=cre_id)
                    hyperlink = self.official_cheatsheet_url(mdfile)
                    cs = self.cheatsheet(section=name, hyperlink=hyperlink, tags=[])
                    for cre in cres:
                        cs.add_link(
                            defs.Link(
                                document=cre, ltype=defs.LinkTypes.AutomaticallyLinkedTo
                            )
                        )
                    standard_entries.append(cs)
        return standard_entries

    def register_supplemental_cheatsheets(self, cache: db.Node_collection):
        # Check if file exists
        if not self.supplement_data_file.exists():
            self.logger.warning(
                "Supplemental cheatsheet file not found at %s – skipping.",
                self.supplement_data_file,
            )
            return []

        # Try to load and parse JSON
        try:
            with self.supplement_data_file.open("r", encoding="utf-8") as handle:
                supplement_entries = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            self.logger.error(
                "Failed to load supplemental cheatsheet file %s: %s – skipping.",
                self.supplement_data_file,
                exc,
            )
            return []

        standard_entries = []
        for entry in supplement_entries:
            # Validate required keys
            if not all(k in entry for k in ("section", "hyperlink")):
                self.logger.warning(
                    "Skipping malformed supplemental entry (missing 'section' or 'hyperlink'): %s",
                    entry,
                )
                continue

            cs = self.cheatsheet(
                section=entry["section"],
                hyperlink=entry["hyperlink"],
                tags=[],
            )
            add_link_failures = False
            for cre_id in entry.get("cre_ids", []):
                cres = cache.get_CREs(external_id=cre_id)
                for cre in cres:
                    link = defs.Link(
                        document=cre.shallow_copy(),
                        ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                    )
                    try:
                        cs.add_link(link)
                    except ValueError as exc:
                        self.logger.warning(
                            "Failed to add link for cre_id %s to cheatsheet %s: %s",
                            cre_id,
                            entry.get("section", "<unknown>"),
                            exc,
                        )
                        add_link_failures = True
            if cs.links and not add_link_failures:
                standard_entries.append(cs)
        return standard_entries

    def deduplicate_entries(self, entries: List[defs.Standard]) -> List[defs.Standard]:
        deduped = {}
        for entry in entries:
            key = (entry.section, entry.hyperlink)
            if key in deduped:
                # Merge duplicates: union links into existing entry
                existing_entry = deduped[key]
                existing_link_ids = {link.document.id for link in existing_entry.links}
                for link in entry.links:
                    if link.document.id not in existing_link_ids:
                        existing_entry.add_link(link)
                        existing_link_ids.add(link.document.id)
            else:
                # First occurrence: store the entry
                deduped[key] = entry
        return list(deduped.values())
