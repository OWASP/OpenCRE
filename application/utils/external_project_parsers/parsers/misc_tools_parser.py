# script to parse CRE links from  README.md files of a given list of projects
import logging
import os
import re
import urllib
from typing import List, NamedTuple
from xmlrpc.client import boolean

from application.database import db
from application.defs import cre_defs as defs
from application.utils import git
from application.prompt_client import prompt_client as prompt_client
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)
import requests

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MiscTools(ParserInterface):
    name = "miscelaneous tools"
    tool_urls = [
        "https://github.com/commjoen/wrongsecrets.git",
    ]

    # TODO (spyros): need to decouple git ops from parsing in order to make this testable
    # although i could just mock the git ops :$
    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        tools = {}
        for url in self.tool_urls:
            tool_entries = self.parse_tool(cache=cache, tool_repo=url)
            tools[tool_entries[0].name] = tool_entries
        return ParseResult(results=tools)

    def parse_tool(
        self, tool_repo: str, cache: db.Node_collection, dry_run: boolean = False
    ):
        if not dry_run:
            repo = git.clone(tool_repo)
        readme = os.path.join(repo.working_dir, "README.md")
        title_regexp = r"# (?P<title>(\w+ ?)+)"
        cre_link = r".*\[.*\]\((?P<url>(https\:\/\/www\.)?opencre\.org\/cre\/(?P<cre>\d+-\d+).*)"
        tool_entries = []
        with open(readme) as rdf:
            mdtext = rdf.read()

            if "opencre.org" not in mdtext:
                logging.error("didn't find a link, bye")
                return []
            title = re.search(title_regexp, mdtext)
            cre = re.search(cre_link, mdtext, flags=re.IGNORECASE)

            if cre and title:
                parsed = urllib.parse.urlparse(cre.group("url"))
                values = urllib.parse.parse_qs(parsed.query)

                tool_name = title.group("title").strip()
                cre_id = cre.group("cre").strip()
                register = True if "register" in values else False
                type = (
                    values.get("type")[0] or "Tool"
                )  # this parser matches tools so this is really optional
                tool_type = values.get("tool_type")[0] or "Unknown"
                description = values.get("description")[0] or ""
                tags = values.get("tags")[0].split(",") if "tags" in values else []
                if cre_id and register:
                    cres = cache.get_CREs(external_id=cre_id)
                    hyperlink = f"{tool_repo.replace('.git','')}"
                    cs = defs.Tool(
                        name=tool_name,
                        tooltype=defs.ToolTypes.from_str(tool_type),
                        tags=tags,
                        hyperlink=hyperlink,
                        description=description,
                        sectionID="",  # we don't support sectionID and section when linking to a whole tool
                        section="",
                    )
                    for dbcre in cres:
                        cs.add_link(
                            defs.Link(
                                ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                                document=dbcre,
                            )
                        )
                        print(
                            f"Registered new Document of type:Tool, toolType: {tool_type}, name:{tool_name} and hyperlink:{hyperlink},"
                            f"linked to cre:{dbcre.id}"
                        )
                    tool_entries.append(cs)
        return tool_entries
