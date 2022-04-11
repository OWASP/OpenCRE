# script to parse zaproxy website md files describing alerts find the CWE ids
#  and add the alerts to CRE
import logging
import os
import re
from typing import List

from application.database import db
from application.defs import cre_defs as defs
from application.utils import git

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def zap_alert(
    name: str, id: str, description: str, tags: List[str], code: str
) -> defs.Tool:
    tags.append(id)
    return defs.Tool(
        tooltype=defs.ToolTypes.Offensive,
        name=f"ZAP Rule: {name}",
        description=description,
        tags=tags,
        hyperlink=code,
    )


def setup(cache: db.Node_collection):
    zaproxy_website = "https://github.com/zaproxy/zaproxy-website.git"
    alerts_path = "site/content/docs/alerts/"
    repo = git.clone(zaproxy_website)
    parse_zap_alerts(repo=repo, cache=cache, alerts_path=alerts_path)


def parse_zap_alerts(cache: db.Node_collection, repo: git.git, alerts_path: str):
    zap_md_cwe_regexp = r"cwe: ?(?P<cweId>\d+)"
    zap_md_title_regexp = r"title: ?(?P<title>\".+\")"
    zap_md_alert_id_regexp = r"alertid: ?(?P<id>\d+)"
    zap_md_alert_type_regexp = r"alerttype: ?(?P<type>\".+\")"
    zap_md_solution_regexp = r"solution: ?(?P<solution>\".+\")"
    zap_md_code_regexp = r"code: ?(?P<code>.+)"
    zap_md_top10_regexp = r"OWASP_(?P<year>\d\d\d\d)_A(?P<num>\d\d?)"

    for mdfile in os.listdir(os.path.join(repo.working_dir, alerts_path)):
        pth = os.path.join(repo.working_dir, alerts_path, mdfile)
        name = None
        externalId = None
        tag = None
        description = None
        code = None
        with open(pth) as mdf:
            mdtext = mdf.read()
            title = re.search(zap_md_title_regexp, mdtext)
            if title:
                name = title.group("title")

            id = re.search(zap_md_alert_id_regexp, mdtext)
            if id:
                externalId = id.group("id")

            type_tag = re.search(zap_md_alert_type_regexp, mdtext)
            if type_tag:
                tag = type_tag.group("type")

            desc = re.search(zap_md_solution_regexp, mdtext)
            if desc:
                description = desc.group("solution")

            cd = re.search(zap_md_code_regexp, mdtext)
            if cd:
                code = cd.group("code")
            else:
                logger.error(
                    f"Alert id: {externalId} titled {name} could not be parsed, missing link to code"
                )
                continue
            top10 = re.search(zap_md_top10_regexp, mdtext)

            cwe = re.search(zap_md_cwe_regexp, mdtext)
            alert = zap_alert(
                name=name,
                id=externalId,
                description=description,
                tags=[tag],
                code=code,
            )
            dbnode = cache.add_node(alert)

            # if top10:
            #     for entry in top10: # TODO figure out how to iterate matches
            #         pass #TODO extract and reconstruct entry, search and link
            if cwe:
                cweId = cwe.group("cweId")
                cwe_nodes = cache.get_nodes(name="CWE", section=cweId)
                for node in cwe_nodes:
                    for link in node.links:
                        if link.document.doctype == defs.Credoctypes.CRE:

                            cache.add_link(
                                cre=db.dbCREfromCRE(link.document), node=dbnode
                            )
            else:
                logger.info(f"CWE id not found in alert {externalId}, skipping linking")
