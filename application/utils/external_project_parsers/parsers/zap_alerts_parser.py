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

from application.prompt_client import prompt_client as prompt_client
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)


class ZAP(ParserInterface):
    name = "ZAP Rule"
    zap_md_cwe_regexp = r"cwe: ?(?P<cweId>\d+)"
    zap_md_title_regexp = r"title: ?(?P<title>\".+\")"
    zap_md_alert_id_regexp = r"alertid: ?(?P<id>\d+(-\d+)?)"
    zap_md_alert_type_regexp = r"alerttype: ?(?P<type>\".+\")"
    zap_md_solution_regexp = r"solution: ?(?P<solution>\".+\")"
    zap_md_code_regexp = r"code: ?(?P<code>.+)"
    zap_md_top10_regexp = r"OWASP_(?P<year>\d\d\d\d)_A(?P<num>\d\d?)"
    alerts_path = "site/content/docs/alerts/"

    def __zap_alert(
        self, name: str, alert_id: str, description: str, tags: List[str], code: str
    ) -> defs.Tool:
        tags.append(alert_id)
        return defs.Tool(
            tooltype=defs.ToolTypes.Offensive,
            name=self.name,
            section=name,
            sectionID=alert_id,
            description=description,
            tags=tags,
            hyperlink=code,
        )

    def parse(
        self, cache: db.Node_collection, ph: prompt_client.PromptHandler
    ) -> List[defs.Tool]:
        zaproxy_website = "https://github.com/zaproxy/zaproxy-website.git"
        repo = git.clone(zaproxy_website)
        alerts = self.__register_alerts(repo=repo, cache=cache)
        return ParseResult(results={self.name: alerts})

    def __link_to_top10(
        self, alert: defs.Tool, top10: re.Match[str] | None, cache: db.Node_collection
    ):
        for match in top10:
            year = match.group("year")
            num = match.group("num")
            entries = cache.get_nodes(name=f"Top10 {year}", ntype="Standard")
            entry = [e for e in entries if str(int(num)) in e.section]
            if entry:
                logger.info(
                    f"Found zap alert {alert.name} linking to {entry[0].name}{entry[0].section}"
                )
                for cre in [
                    nl
                    for nl in entry[0].links
                    if nl.document.doctype == defs.Credoctypes.CRE
                ]:
                    alert.add_link(
                        defs.Link(
                            ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                            document=cre.document,
                        )
                    )
            else:
                logger.error(
                    f"Zap Alert {alert.name} links to OWASP top 10 {year}:{num} but CRE doesn't know about it, incomplete data?"
                )
        return alert

    def __link_to_cwe(
        self, alert: defs.Tool, cwe: re.Match[str] | None, cache: db.Node_collection
    ):
        cweId = cwe.group("cweId")
        logger.info(f"Found zap alert {alert.name} linking to CWE {cweId}")
        cwe_nodes = cache.get_nodes(name="CWE", sectionID=cweId)
        for node in cwe_nodes:
            for link in node.links:
                if link.document.doctype == defs.Credoctypes.CRE:
                    alert.add_link(
                        defs.Link(
                            ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                            document=link.document,
                        )
                    )
        if not cwe_nodes:
            logger.error(
                f"opencre.org does not know of CWE {cweId}, it is linked to by zap alert: {alert.name}"
            )
        return alert

    def __parse_md_file(self, mdtext: str, cache: db.Node_collection):
        title = re.search(self.zap_md_title_regexp, mdtext)
        name = title.group("title") if title else None

        id = re.search(self.zap_md_alert_id_regexp, mdtext)
        externalId = id.group("id") if id else None

        type_tag = re.search(self.zap_md_alert_type_regexp, mdtext)
        tag = type_tag.group("type") if type_tag else None

        desc = re.search(self.zap_md_solution_regexp, mdtext)
        description = desc.group("solution") if desc else None

        cd = re.search(self.zap_md_code_regexp, mdtext)
        if cd:
            code = cd.group("code")
        else:
            logger.error(
                f"Alert id: {externalId} titled {name} could not be parsed, missing link to code"
            )
            return
        cwe = re.search(self.zap_md_cwe_regexp, mdtext)
        alert = self.__zap_alert(
            name=name.replace('"', ""),
            alert_id=externalId,
            description=description.replace('"', "") if description else "",
            tags=[tag.replace('"', "")],
            code=code,
        )
        if not alert:
            raise Exception(f"alert {name} is None, this is a bug")
        top10 = re.finditer(self.zap_md_top10_regexp, mdtext)
        if top10:
            alert = self.__link_to_top10(alert=alert, top10=top10, cache=cache)

        if cwe:
            alert = self.__link_to_cwe(alert=alert, cwe=cwe, cache=cache)
        else:
            logger.error(
                f"CWE id not found in alert {externalId}:{alert.name}, skipping linking to cwe"
            )
        return alert

    def __register_alerts(self, cache: db.Node_collection, repo: git.git):
        alerts = []
        for mdfile in os.listdir(os.path.join(repo.working_dir, self.alerts_path)):
            pth = os.path.join(repo.working_dir, self.alerts_path, mdfile)
            with open(pth) as mdf:
                mdtext = mdf.read()
                alert = self.__parse_md_file(mdtext=mdtext, cache=cache)
                if alert:
                    alerts.append(alert)
                else:
                    logger.debug("ZAP Alert could not be registered")
        return alerts
