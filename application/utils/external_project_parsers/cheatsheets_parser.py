# script to parse zaproxy website md files describing alerts find the CWE ids
#  and add the alerts to CRE
from typing import List
from application.database import db
from application.utils import git
from application.defs import cre_defs as defs
import os
import re


def cheatsheet(
    section: str, hyperlink:str) -> defs.Standard:
    return defs.Standard(
        name=f"Cheat_sheets",
        section=section,
        tags=tags,
        hyperlink=hyperlink,
    )


def parse_cheatsheets(cache: db.Node_collection):
    c_repo = "https://github.com/OWASP/CheatSheetSeries.git"
    cheasheets_path = "cheatsheets/"
    title_regexp = r"# (?P<title>.+)"
    cre_link = r"opencre.org/cre/(?P<cre>.+)$"
    repo = git.clone(c_repo)
    for mdfile in os.listdir(os.path.join(repo.working_dir, cheasheets_path)):
        pth = os.path.join(repo.working_dir, cheasheets_path, mdfile)
        name = None
        tag = None
        section = None
        with open(pth) as mdf:
            mdtext = mdf.read()
            if "opencre.org" not in mdtext:
                continue
            title = re.search(title_regexp, mdtext)
            if title:
                name = title.group("title")
            cre = re.search(cre_link, mdtext)
            if cre:
                cre_id = cre.group("cre")
                cres = cache.get_CREs(external_id=cre_id)
                hyperlink = c_repo.replace(".git","")+"/"+cheasheets_path+"/"+mdfile
                for dbcre in cres:
                    cs = cheatsheet(
                       section=title,
                       hyperlink=hyperlink
                    )
                    dbnode = cache.add_node(cs)
                    cache.add_link(cre=dbcre, node=dbnode)
