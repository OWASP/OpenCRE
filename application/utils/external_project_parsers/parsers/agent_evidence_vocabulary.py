"""Import the agent-evidence-vocabulary term registry as a standard.

The vocabulary keeps its CRE links in its own source: a term whose definition
states a requirement that a Common Requirement organizes carries an ``opencre``
list, one item per link::

    observation_vantage:
      definition: ...
      opencre:
        - cre: https://www.opencre.org/cre/026-280
          match: partial
          basis: "one line on what the term and the requirement share"

This parser reads ``vocabulary.yaml`` at the newest release tag (tags are named
``agent-evidence-vocabulary-vX.Y.Z``), makes one node per linked term and links
it to each CRE it names. ``match`` is one of ``exact``, ``structural`` or
``partial``; OpenCRE links carry no strength, so the match and its basis are
written into the node description. A CRE id the cache does not know, or a
malformed link, is logged and skipped without stopping the import.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import re
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client as prompt_client
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)


class AgentEvidenceVocabulary(ParserInterface):
    name = "Agent Evidence Vocabulary"
    repository = "probityai/agent-evidence"
    vocabulary_path = "packages/vocabulary/vocabulary.yaml"
    tag_prefix = "agent-evidence-vocabulary-v"
    # The first release whose terms carry opencre links.
    minimum_version = "0.4.0"
    match_values = ("exact", "structural", "partial")
    cre_url = re.compile(r"^https://(www\.)?opencre\.org/cre/(?P<cre>\d{3}-\d{3})$")
    tag_pattern = re.compile(r"^agent-evidence-vocabulary-v(?P<version>\d+\.\d+\.\d+)$")

    def tags_url(self) -> str:
        return f"https://api.github.com/repos/{self.repository}/tags?per_page=100"

    def raw_url(self, tag: str) -> str:
        return f"https://raw.githubusercontent.com/{self.repository}/{tag}/{self.vocabulary_path}"

    def term_url(self, tag: str, line: int) -> str:
        return f"https://github.com/{self.repository}/blob/{tag}/{self.vocabulary_path}#L{line}"

    def parse(
        self,
        cache: db.Node_collection,
        ph: Optional[prompt_client.PromptHandler],
    ) -> ParseResult:
        tag = self.latest_release_tag()
        resp = requests.get(self.raw_url(tag), timeout=60)
        if resp.status_code != 200:
            err_str = f"could not retrieve {self.vocabulary_path} at {tag}, status code {resp.status_code}"
            logger.fatal(err_str)
            raise RuntimeError(err_str)
        entries = self.parse_vocabulary(text=resp.text, tag=tag, cache=cache)
        results: Dict[str, List[defs.Document]] = {self.name: list(entries)}
        base_parser_defs.validate_classification_tags(results)
        return ParseResult(results=results)

    def latest_release_tag(self) -> str:
        """Return the newest release tag at or above ``minimum_version``."""
        url: Optional[str] = self.tags_url()
        releases: List[Tuple[Tuple[int, ...], str]] = []
        minimum = self.version_key(self.minimum_version)
        while url:
            resp = requests.get(url, timeout=60)
            if resp.status_code != 200:
                err_str = f"could not list tags of {self.repository}, status code {resp.status_code}"
                logger.fatal(err_str)
                raise RuntimeError(err_str)
            for item in resp.json():
                name = item.get("name", "") if isinstance(item, dict) else ""
                found = self.tag_pattern.match(name)
                if not found:
                    continue
                version = self.version_key(found.group("version"))
                if version >= minimum:
                    releases.append((version, name))
            url = resp.links.get("next", {}).get("url")
        if not releases:
            err_str = f"no {self.tag_prefix}X.Y.Z tag at or above {self.minimum_version} in {self.repository}"
            logger.fatal(err_str)
            raise RuntimeError(err_str)
        return max(releases)[1]

    @staticmethod
    def version_key(version: str) -> Tuple[int, ...]:
        return tuple(int(part) for part in version.split("."))

    def term_lines(self, text: str) -> Dict[Tuple[str, str], int]:
        """Map (group, term) to the 1-based line where the term's key starts."""
        lines: Dict[Tuple[str, str], int] = {}
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        if not isinstance(root, yaml.MappingNode):
            return lines
        for group_key, group_node in root.value:
            if not isinstance(group_node, yaml.MappingNode):
                continue
            for term_key, _ in group_node.value:
                lines[(group_key.value, term_key.value)] = term_key.start_mark.line + 1
        return lines

    def parse_vocabulary(
        self, text: str, tag: str, cache: db.Node_collection
    ) -> List[defs.Standard]:
        vocabulary = yaml.safe_load(text)
        if not isinstance(vocabulary, dict):
            raise ValueError(f"{self.vocabulary_path} at {tag} is not a mapping")
        version = self.version_of(vocabulary, tag)
        lines = self.term_lines(text)
        entries: List[defs.Standard] = []
        for group, terms in vocabulary.items():
            if group == "meta" or not isinstance(terms, dict):
                continue
            for term, body in terms.items():
                if not isinstance(body, dict) or "opencre" not in body:
                    continue
                standard = self.make_standard(
                    group=group,
                    term=term,
                    body=body,
                    version=version,
                    hyperlink=self.term_url(tag, lines.get((group, term), 1)),
                    cache=cache,
                )
                if standard is not None:
                    entries.append(standard)
        return entries

    def version_of(self, vocabulary: Dict[str, Any], tag: str) -> str:
        tag_version = tag[len(self.tag_prefix) :]
        meta = vocabulary.get("meta")
        declared = meta.get("version") if isinstance(meta, dict) else None
        if not declared:
            return tag_version
        if str(declared) != tag_version:
            logger.warning(
                f"{self.vocabulary_path} at {tag} declares version {declared}, using it"
            )
        return str(declared)

    def make_standard(
        self,
        group: str,
        term: str,
        body: Dict[str, Any],
        version: str,
        hyperlink: str,
        cache: db.Node_collection,
    ) -> Optional[defs.Standard]:
        links = body.get("opencre")
        if not isinstance(links, list):
            logger.error(f"{group}.{term}: opencre is not a list, skipping the term")
            return None
        definition = " ".join(str(body.get("definition") or "").split())
        standard = defs.Standard(
            name=self.name,
            section=term,
            sectionID=f"{group}.{term}",
            hyperlink=hyperlink,
            version=version,
            tags=base_parser_defs.build_tags(
                family=base_parser_defs.Family.STANDARD,
                subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
                audience=base_parser_defs.Audience.ARCHITECT,
                maturity=base_parser_defs.Maturity.DRAFT,
                source="agent_evidence_vocabulary",
                extra=[],
            ),
        )
        link_notes: List[str] = []
        linked: List[str] = []
        for item in links:
            parsed = self.parse_link(group, term, item)
            if parsed is None:
                continue
            cre_id, match, basis = parsed
            cres = cache.get_CREs(external_id=cre_id)
            if not cres:
                logger.warning(
                    f"{group}.{term}: CRE {cre_id} is not in the cache, skipping the link"
                )
                continue
            added = False
            for cre in cres:
                if cre.id in linked:
                    logger.warning(
                        f"{group}.{term}: CRE {cre_id} is listed twice, keeping the first"
                    )
                    continue
                standard.add_link(
                    defs.Link(
                        document=cre.shallow_copy(),
                        ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                    )
                )
                linked.append(cre.id)
                added = True
            if added:
                link_notes.append(f"CRE {cre_id} ({match}): {basis}")
        if not standard.links:
            logger.warning(f"{group}.{term}: no CRE link resolved, skipping the term")
            return None
        standard.description = "\n".join([definition] + link_notes).strip()
        return standard

    def parse_link(
        self, group: str, term: str, item: Any
    ) -> Optional[Tuple[str, str, str]]:
        if not isinstance(item, dict):
            logger.error(f"{group}.{term}: opencre item {item!r} is not a mapping")
            return None
        found = self.cre_url.match(str(item.get("cre", "")))
        if not found:
            logger.error(
                f"{group}.{term}: {item.get('cre')!r} is not an opencre.org/cre/NNN-NNN URL"
            )
            return None
        match = item.get("match")
        if match not in self.match_values:
            logger.error(
                f"{group}.{term}: match {match!r} is not one of {', '.join(self.match_values)}"
            )
            return None
        basis = " ".join(str(item.get("basis") or "").split())
        return found.group("cre"), match, basis
