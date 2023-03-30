# script to parse secure headers md files find the links to opencre.org and add the page to CRE
from pprint import pprint
from typing import List
from application.database import db
from application.utils import git
from application.defs import cre_defs as defs
import os
import re
from urllib.parse import urlparse, parse_qs

# GENERIC Markdown file parser for self-contained links! when we have more projects using this setup add them in the list


def entry(name: str, section: str, hyperlink: str, tags: List[str]) -> defs.Standard:
    return defs.Standard(
        name=name,
        section=section,
        tags=tags,
        hyperlink=hyperlink,
    )


def parse(cache: db.Node_collection):
    sh_repo = "https://github.com/owasp/www-project-secure-headers.git"
    file_path = "./"
    repo = git.clone(sh_repo)
    register_headers(repo=repo, cache=cache, file_path=file_path, repo_path=sh_repo)


def register_headers(cache: db.Node_collection, repo, file_path, repo_path):
    cre_link = r"\[([\w\s\d]+)\]\((?P<url>((?:\/|https:\/\/)(www\.)?opencre\.org/cre/(?P<creID>\d+-\d+)\?[\w\d\.\/\=\#\+\&\%\-]+))\)"
    files = os.listdir(os.path.join(repo.working_dir, file_path))
    for mdfile in files:
        pth = os.path.join(repo.working_dir, file_path, mdfile)
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
                    for dbcre in cres:
                        cs = entry(
                            name=name[0] if name else "",
                            section=section[0] if section else "",
                            hyperlink=link[0] if link else "",
                            tags=[],
                        )
                        dbnode = cache.add_node(cs)
                        if dbnode:
                            cache.add_link(
                                cre=db.dbCREfromCRE(dbcre),
                                node=dbnode,
                                type=defs.LinkTypes.LinkedTo,
                            )
                        else:
                            print(f"could not register link to {name}, {section}")
