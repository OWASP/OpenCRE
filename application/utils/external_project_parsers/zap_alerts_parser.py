# script to parse zaproxy website md files describing alerts find the CWE ids
#  and add the alerts to CRE
from typing import List
from application.database import db
from application.utils import git
from application.defs import cre_defs as defs
import os
import re
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def zap_alert(
    name: str, id: str, description: str, tags: List[str], code: str
) -> defs.Tool:
    return defs.Tool(
        tooltype=defs.ToolTypes.Offensive,
        name=f"ZAP Alert: {name}",
        id=id,
        description=description,
        tags=tags,
        hyperlink=code,
    )


def parse_zap_alerts(cache: db.Node_collection):
    zaproxy_website = "https://github.com/zaproxy/zaproxy-website.git"
    alerts_path = "site/content/docs/alerts/"
    zap_md_cwe_regexp = r"cwe: ?(?P<cweId>\d+)"
    zap_md_title_regexp = r"title: ?(?P<title>\".+\")"
    zap_md_alert_id_regexp = r"alertid: ?(?P<id>\d+)"
    zap_md_alert_type_regexp = r"alerttype: ?(?P<type>\".+\")"
    zap_md_solution_regexp = r"solution: ?(?P<solution>\".+\")"
    zap_md_code_regexp = r"code: ?(?P<code>.+)"

    repo = git.clone(zaproxy_website)
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
            cwe = re.search(zap_md_cwe_regexp, mdtext)
            if cwe:
                cweId = cwe.group("cweId")
                cwe_nodes = cache.get_nodes(name="CWE", section=cweId)
                for node in cwe_nodes:
                    for link in node.links:
                        if link.document.doctype == defs.Credoctypes.CRE:
                            alert = zap_alert(
                                name=name,
                                id=externalId,
                                description=description,
                                tags=[tag],
                                code=code,
                            )
                            dbnode = cache.add_node(alert)
                            cache.add_link(
                                cre=db.dbCREfromCRE(link.document), node=dbnode
                            )
