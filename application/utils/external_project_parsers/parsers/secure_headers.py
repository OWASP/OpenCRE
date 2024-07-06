# script to parse secure headers md files find the links to opencre.org and add the page to CRE
from pprint import pprint
from typing import List
from application.database import db
from application.utils import git
from application.defs import cre_defs as defs
import os
import re
from urllib.parse import urlparse, parse_qs
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)
from application.prompt_client import prompt_client as prompt_client

# GENERIC Markdown file parser for self-contained links! when we have more projects using this setup add them in the list


class SecureHeaders(ParserInterface):
    name = "Secure Headers"

    def entry(self, section: str, hyperlink: str, tags: List[str]) -> defs.Standard:
        return defs.Standard(
            name=self.name,
            section=section,
            tags=tags,
            hyperlink=hyperlink,
        )

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        sh_repo = "https://github.com/owasp/www-project-secure-headers.git"
        file_path = "./"
        repo = git.clone(sh_repo)
        entries = self.register_headers(
            repo=repo, cache=cache, file_path=file_path, repo_path=sh_repo
        )
        return ParseResult(results={self.name: entries})

    def register_headers(self, cache: db.Node_collection, repo, file_path, repo_path):
        cre_link = r"\[([\w\s\d]+)\]\((?P<url>((?:\/|https:\/\/)(www\.)?opencre\.org/cre/(?P<creID>\d+-\d+)\?[\w\d\.\/\=\#\+\&\%\-]+))\)"
        entries = []
        for path, _, files in os.walk(repo.working_dir):
            for mdfile in files:
                pth = os.path.join(path, mdfile)

                if not os.path.isfile(pth):
                    continue
                with open(pth) as mdf:
                    mdtext = mdf.read()

                    if "opencre.org" not in mdtext:
                        continue
                    links = re.finditer(cre_link, mdtext, re.MULTILINE)
                    for cre in links:
                        if cre:
                            parsed = urlparse(cre.group("url"))
                            creID = cre.group("creID")
                            queries = parse_qs(parsed.query)
                            name = queries.get("name")
                            section = queries.get("section")
                            link = queries.get("link")
                            cres = cache.get_CREs(external_id=creID)
                            cs = self.entry(
                                section=section[0] if section else "",
                                hyperlink=link[0] if link else "",
                                tags=[],
                            )
                            for dbcre in cres:
                                cs.add_link(
                                    defs.Link(
                                        document=dbcre,
                                        ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                                    )
                                )
                    entries.append(cs)
        return entries
