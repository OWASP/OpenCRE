# script to parse cheatsheet md files find the links to opencre.org and add the cheatsheets to CRE
from typing import List
from application.database import db
from application.utils import git
from application.defs import cre_defs as defs
import os
import re


def cheatsheet(section: str, hyperlink: str, tags: List[str]) -> defs.Standard:
    return defs.Standard(
        name=f"OWASP Cheat Sheets",
        section=section,
        tags=tags,
        hyperlink=hyperlink,
    )


def parse_cheatsheets(cache: db.Node_collection):
    c_repo = "https://github.com/OWASP/CheatSheetSeries.git"
    cheatsheets_path = "cheatsheets/"
    repo = git.clone(c_repo)
    register_cheatsheets(
        repo=repo, cache=cache, cheatsheets_path=cheatsheets_path, repo_path=c_repo
    )


def register_cheatsheets(cache: db.Node_collection, repo, cheatsheets_path, repo_path):
    title_regexp = r"# (?P<title>.+)"
    cre_link = r"(https://www\.)?opencre.org/cre/(?P<cre>\d+-\d+)"
    files = os.listdir(os.path.join(repo.working_dir, cheatsheets_path))
    for mdfile in files:
        pth = os.path.join(repo.working_dir, cheatsheets_path, mdfile)
        name = None
        tag = None
        section = None

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
                for dbcre in cres:
                    cs = cheatsheet(
                        section=name,
                        hyperlink=hyperlink,
                        tags=[],
                    )
                    dbnode = cache.add_node(cs)
                    cache.add_link(
                        cre=db.dbCREfromCRE(dbcre),
                        node=dbnode,
                        type=defs.LinkTypes.LinkedTo,
                    )
