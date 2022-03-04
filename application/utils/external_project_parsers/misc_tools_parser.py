# script to parse CRE links from  README.md files of a given list of projects
import os
import re
from typing import List

from application.database import db
from application.defs import cre_defs as defs
from application.utils import git

tool_urls = [
    "https://github.com/commjoen/wrongsecrets"

]
def Project(name: str, hyperlink: str, tags: List[str],ttype:str,description:str) -> defs.Tool:
    return defs.Tool(
        name=name,
        tooltype=defs.ToolTypes.from_str(ttype),
        tags=tags,
        hyperlink=hyperlink,
        description=description
    )


def parse_tool(tool_repo:str, cache: db.Node_collection):
    # TODO: need to figure a way to provide all the necessary info in one hyperlink, perhaps osib can be leveraged for this
    
    repo = git.clone(tool_repo)
    readme = os.listdir(os.path.join(repo.working_dir, "README.md"))
    with open(readme) as rdf:
        mdtext = rdf.read()
        if "opencre.org" not in mdtext:
            return
        title = re.search(title_regexp, mdtext)
        cre = re.search(cre_link, mdtext)

        if cre and title:
            name = title.group("title")
            cre_id = cre.group("cre")
            cres = cache.get_CREs(external_id=cre_id)
            hyperlink = f"{tool_repo.replace('.git','')}/{readme}"
            for dbcre in cres:
                cs = Project(
                    name=name,
                    hyperlink=hyperlink,
                    tags=[],
                    ttype=ttype,
                    description=description,
                )
                dbnode = cache.add_node(cs)
                cache.add_link(
                    cre=db.dbCREfromCRE(dbcre),
                    node=dbnode,
                    type=defs.LinkTypes.LinkedTo,
                )
