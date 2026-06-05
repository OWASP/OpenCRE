# script to parse secure headers md files find the links to opencre.org and add the page to CRE
from typing import List
import logging
import os
import re
from urllib.parse import urlparse, parse_qs

from application.database import db
from application.defs import cre_defs as defs
from application.utils import git
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)
from application.prompt_client import prompt_client as prompt_client

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# GENERIC Markdown file parser

# OWASP markdown may reference retired CRE ids; map to current OpenCRE ids.
LEGACY_CRE_ID_REMAP = {
    # tab_bestpractices.md still links 403-005; corpus uses 743-110 for this topic.
    "403-005": "743-110",
}


class SecureHeadersLinkError(Exception):
    """Raised when a Secure Headers markdown CRE reference cannot be resolved."""


class SecureHeaders(ParserInterface):
    name = "Secure Headers"

    def entry(self, section: str, hyperlink: str, tags: List[str]) -> defs.Standard:
        return defs.Standard(
            name=self.name,
            section=section,
            tags=base_parser_defs.build_tags(
                family=base_parser_defs.Family.GUIDANCE,
                subtype=base_parser_defs.Subtype.CHEATSHEET,
                audience=base_parser_defs.Audience.DEVELOPER,
                maturity=base_parser_defs.Maturity.STABLE,
                source="owasp_secure_headers",
                extra=tags,
            ),
            hyperlink=hyperlink,
        )

    def resolve_cre_external_id(
        self, cache: db.Node_collection, external_id: str
    ) -> tuple[list[defs.CRE], str]:
        candidates = [external_id]
        remapped = LEGACY_CRE_ID_REMAP.get(external_id)
        if remapped and remapped not in candidates:
            candidates.append(remapped)
        for candidate in candidates:
            cres = cache.get_CREs(external_id=candidate)
            if cres:
                if candidate != external_id:
                    logger.info(
                        "Secure Headers remapped stale CRE id %s -> %s",
                        external_id,
                        candidate,
                    )
                return cres, candidate
        raise SecureHeadersLinkError(
            f"Secure Headers markdown references unknown CRE id {external_id!r}"
            + (f" (also tried remap {remapped!r})" if remapped else "")
        )

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        sh_repo = "https://github.com/owasp/www-project-secure-headers.git"
        file_path = "./"
        # Large OWASP site repo: only fetch markdown files (walk is *.md-only anyway).
        repo = git.clone(
            sh_repo,
            sparse_paths=["/**/*.md"],
            sparse_cone=False,
        )
        entries = self.register_headers(
            repo=repo, cache=cache, file_path=file_path, repo_path=sh_repo
        )
        results = {self.name: entries}
        base_parser_defs.validate_classification_tags(results)
        return ParseResult(results=results)

    def register_headers(self, cache: db.Node_collection, repo, file_path, repo_path):
        cre_link = r"\[([\w\s\d]+)\]\((?P<url>((?:\/|https:\/\/)(www\.)?opencre\.org/cre/(?P<creID>\d+-\d+)\?[\w\d\.\/\=\#\+\&\%\-]+))\)"
        entries = []
        for path, _, files in os.walk(repo.working_dir):
            for mdfile in files:
                if not mdfile.endswith(".md"):
                    continue
                pth = os.path.join(path, mdfile)

                if not os.path.isfile(pth):
                    continue
                try:
                    with open(pth, encoding="utf-8") as mdf:
                        mdtext = mdf.read()
                except UnicodeDecodeError:
                    logger.warning("Skipping non-UTF-8 markdown file: %s", pth)
                    continue

                if "opencre.org" not in mdtext:
                    continue
                links = re.finditer(cre_link, mdtext, re.MULTILINE)
                for cre in links:
                    parsed = urlparse(cre.group("url"))
                    creID = cre.group("creID")
                    queries = parse_qs(parsed.query)
                    section = queries.get("section")
                    link = queries.get("link")
                    cres, _resolved_id = self.resolve_cre_external_id(cache, creID)
                    cs = self.entry(
                        section=section[0] if section else "",
                        hyperlink=link[0] if link else "",
                        tags=[],
                    )
                    for dbcre in cres:
                        cs.add_link(
                            defs.Link(
                                document=dbcre,
                                ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                            )
                        )
                    entries.append(cs)
        return entries
