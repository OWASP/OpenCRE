from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

from application.defs import cre_defs as defs
from application.prompt_client import prompt_client as prompt_client
from application.database import db

# abstract class/interface that shows how to import a project that is not cre or its core resources


class Family(str, Enum):
    # IMPORTANT: Enum values are the actual tag strings.
    # Tests deliberately assert against these literal strings to
    # guarantee the external tagging convention stays stable.
    STANDARD = "family:standard"
    GUIDANCE = "family:guidance"
    TAXONOMY = "family:taxonomy"


class Subtype(str, Enum):
    REQUIREMENTS_STANDARD = "subtype:requirements_standard"
    MATURITY_MODEL = "subtype:maturity_model"
    CHEATSHEET = "subtype:cheatsheet"
    TESTING_GUIDE = "subtype:testing_guide"
    BLOG = "subtype:blog"
    TOP10 = "subtype:top10"
    RISK_LIST = "subtype:risk_list"
    # Training / CTF-style vulnerable applications (Juice Shop, WrongSecrets, etc.)
    TRAINING_APP = "subtype:training_app"


class Audience(str, Enum):
    DEVELOPER = "audience:developer"
    TESTER = "audience:tester"
    ARCHITECT = "audience:architect"
    MANAGEMENT = "audience:management"


class Maturity(str, Enum):
    DRAFT = "maturity:draft"
    STABLE = "maturity:stable"
    LEGACY = "maturity:legacy"
    EXPERIMENTAL = "maturity:experimental"


def build_tags(
    family: Family,
    subtype: Subtype,
    audience: Audience,
    maturity: Maturity,
    source: str,
    extra: Optional[List[str]] = None,
) -> List[str]:
    """
    Helper to construct classification tags consistently.
    `source` must be a bare source identifier (e.g. 'owasp_cheatsheets'),
    it will be prefixed with 'source:'.
    """
    base = [
        family.value,
        subtype.value,
        audience.value,
        maturity.value,
        f"source:{source}",
    ]
    if extra:
        base.extend(extra)
    # de-duplicate while preserving order
    seen = set()
    result: List[str] = []
    for t in base:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _has_prefix(tags: List[str], prefix: str) -> bool:
    return any(t.startswith(prefix) for t in tags)


def validate_classification_tags(documents: Dict[str, List[defs.Document]]) -> None:
    """
    Ensure every Document produced by parsers has the required classification tags:
    - family:*
    - subtype:*
    - source:*
    - audience:*
    - maturity:*

    Raises ValueError if any document is missing one of these.
    """
    for group_name, docs in documents.items():
        for doc in docs:
            tags = doc.tags or []
            missing = []
            if not _has_prefix(tags, "family:"):
                missing.append("family:*")
            if not _has_prefix(tags, "subtype:"):
                missing.append("subtype:*")
            if not _has_prefix(tags, "source:"):
                missing.append("source:*")
            if not _has_prefix(tags, "audience:"):
                missing.append("audience:*")
            if not _has_prefix(tags, "maturity:"):
                missing.append("maturity:*")
            if missing:
                raise ValueError(
                    f"Parser produced unclassified document in group '{group_name}': "
                    f"{doc.name!r} (doctype={doc.doctype}) missing tags {missing}"
                )


@dataclass
class ParseResult(object):
    results: Dict[str, List[defs.Document]] = None
    calculate_gap_analysis: bool = True
    calculate_embeddings: bool = True


class ParserInterface(object):
    # The name of the resource being parsed
    name: str

    def parse(
        database: db.Node_collection,
        prompt_client: Optional[prompt_client.PromptHandler],
    ) -> ParseResult:
        """
        Parses the resources of a project,
        links the resource of the project to CREs
        this can be done either using glue resources, AI or any other supported method
        then calls cre_main.register_node
        Returns a dict with a key of the resource for importing and a value of list of documents with CRE links, optionally with their embeddings filled in
        """
        raise NotImplementedError
