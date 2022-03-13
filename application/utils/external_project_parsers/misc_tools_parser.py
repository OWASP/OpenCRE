# script to parse CRE links from  README.md files of a given list of projects
import os
import re
import urllib
from pprint import pprint
from typing import List

from application.database import db
from application.defs import cre_defs as defs
from application.utils import git

tool_urls = [
    "https://github.com/commjoen/wrongsecrets.git",
    # "https://github.com/northdpole/wrongsecrets.git",

]
def Project(name: str, hyperlink: str, tags: List[str],ttype:str,description:str) -> defs.Tool:
    pprint(name)
    print(ttype)
    print(" ".join(tags))
    print(description)
    return defs.Tool(
        name=name,
        tooltype=defs.ToolTypes.from_str(ttype),
        tags=tags,
        hyperlink=hyperlink,
        description=description
    )


def parse_tool(tool_repo:str, cache: db.Node_collection):

    repo = git.clone(tool_repo)
    readme = os.path.join(repo.working_dir, "README.md")
    title_regexp = r"# (?P<title>(\w+ )+)"
    cre_link = r".*\[.*\]\((?P<url>(https\:\/\/www\.)?opencre\.org\/cre\/(?P<cre>\d+-\d+).*)"

    with open(readme) as rdf:
        mdtext = rdf.read()

        if "opencre.org" not in mdtext:
            pprint("didn't find a link, bye")
            return
        title = re.search(title_regexp, mdtext)
        cre = re.search(cre_link, mdtext,flags=re.IGNORECASE)

        if cre and title:
            parsed = urllib.parse.urlparse(cre.group("url"))
            values = urllib.parse.parse_qs(parsed.query)
            
            name = title.group("title").strip()
            cre_id = cre.group("cre").strip()
            register = True if 'register' in values else False
            type = values.get("type")[0] or "Tool" # this parser matches tools so this is really optional
            tool_type =  values.get("tool_type")[0] or "Unknown"
            description = values.get("description")[0] or ""
            tags = values.get("tags")[0].split(",") if "tags" in values else []
            if cre_id and register:
                cres = cache.get_CREs(external_id=cre_id)
                hyperlink = (
                        f"{tool_repo.replace('.git','')}"
                    )
                for dbcre in cres:
                    cs = Project(
                        name=name,
                        hyperlink=hyperlink,
                        tags=tags or [],
                        ttype=tool_type,
                        description=description,
                    )
                    pprint(cs)
                    pprint(cres)
                    # dbnode = cache.add_node(cs)
                    # cache.add_link(
                    #     cre=db.dbCREfromCRE(dbcre),
                    #     node=dbnode,
                    #     type=defs.LinkTypes.LinkedTo,
                    # )
