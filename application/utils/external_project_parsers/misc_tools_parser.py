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

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


tool_urls = [
    "https://github.com/commjoen/wrongsecrets.git",
    # "https://github.com/northdpole/wrongsecrets.git",
]


def project(
    name: str,
    hyperlink: str,
    tags: List[str],
    ttype: str,
    description: str,
    ruleID: str,
    section: str,
) -> defs.Tool:
    return defs.Tool(
        name=name,
        tooltype=defs.ToolTypes.from_str(ttype),
        tags=tags,
        hyperlink=hyperlink,
        description=description,
        ruleID=ruleID,
        section=section,
    )


# TODO (spyros): need to decouple git ops from parsing in order to make this testable
# although i could just mock the git ops :$
def parse_tool(tool_repo: str, cache: db.Node_collection, dry_run: boolean = False):
    if not dry_run:
        repo = git.clone(tool_repo)
    readme = os.path.join(repo.working_dir, "README.md")
    title_regexp = r"# (?P<title>(\w+ )+)"
    cre_link = (
        r".*\[.*\]\((?P<url>(https\:\/\/www\.)?opencre\.org\/cre\/(?P<cre>\d+-\d+).*)"
    )

    with open(readme) as rdf:
        mdtext = rdf.read()

        if "opencre.org" not in mdtext:
            logging.error("didn't find a link, bye")
            return
        title = re.search(title_regexp, mdtext)
        cre = re.search(cre_link, mdtext, flags=re.IGNORECASE)

        if cre and title:
            parsed = urllib.parse.urlparse(cre.group("url"))
            values = urllib.parse.parse_qs(parsed.query)

            name = title.group("title").strip()
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
                for dbcre in cres:
                    cs = project(
                        name=name,
                        hyperlink=hyperlink,
                        tags=tags or [],
                        ttype=tool_type,
                        description=description,
                        ruleID="",  # we don't support ruleID and section when linking to a whole tool
                        section="",
                    )
                    dbnode = cache.add_node(node=cs)
                    cache.add_link(
                        cre=db.dbCREfromCRE(dbcre),
                        node=dbnode,
                        type=defs.LinkTypes.LinkedTo,
                    )
                    print(
                        f"Registered new Document of type:Tool, toolType: {tool_type}, name:{name} and hyperlink:{hyperlink},"
                        f"linked to cre:{dbcre.id}"
                    )
