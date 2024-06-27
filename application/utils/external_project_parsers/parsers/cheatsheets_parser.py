# script to parse cheatsheet md files find the links to opencre.org and add the cheatsheets to CRE
from typing import List
from application.database import db
from application.utils import git
from application.defs import cre_defs as defs
import os
import re
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)
from application.prompt_client import prompt_client as prompt_client


class Cheatsheets(ParserInterface):
    name = "OWASP Cheat Sheets"

    def cheatsheet(
        self, section: str, hyperlink: str, tags: List[str]
    ) -> defs.Standard:
        return defs.Standard(
            name=self.name,
            section=section,
            tags=tags,
            hyperlink=hyperlink,
        )

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        c_repo = "https://github.com/OWASP/CheatSheetSeries.git"
        cheatsheets_path = "cheatsheets/"
        repo = git.clone(c_repo)
        cheatsheets = self.register_cheatsheets(
            repo=repo, cache=cache, cheatsheets_path=cheatsheets_path, repo_path=c_repo
        )
        return ParseResult(results={self.name: cheatsheets})

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
                    hyperlink = f"{repo_path.replace('.git','')}/tree/master/{cheatsheets_path}{mdfile}"
                    cs = self.cheatsheet(section=name, hyperlink=hyperlink, tags=[])
                    for cre in cres:
                        cs.add_link(
                            defs.Link(
                                document=cre, ltype=defs.LinkTypes.AutomaticallyLinkedTo
                            )
                        )
                    standard_entries.append(cs)
        return standard_entries
