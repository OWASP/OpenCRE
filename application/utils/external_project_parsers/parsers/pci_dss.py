from pprint import pprint
import logging
import os
from typing import Dict, Any, List, Optional
from application.database import db
from application.defs import cre_defs as defs
import re
from application.utils import spreadsheet as sheet_utils
from application.prompt_client import prompt_client as prompt_client
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_DEFAULT_PCI_DSS_CRE_SIMILARITY_THRESHOLDS = (0.55, 0.45, 0.35)
_DEFAULT_PCI_BRIDGE_STANDARDS = ("NIST 800-53 v5", "ISO 27001", "ASVS", "CWE")
_DEFAULT_PCI_BRIDGE_MIN_SIMILARITY = 0.4


def _parse_float_env(name: str, default: float) -> float:
    """Read a float from an environment variable, falling back on invalid values."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


def _parse_float_tuple_env(name: str, default: tuple[float, ...]) -> tuple[float, ...]:
    """Read a comma-separated float tuple from env, falling back on invalid values."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        values = tuple(float(part.strip()) for part in raw.split(",") if part.strip())
    except ValueError:
        logger.warning("Invalid %s=%r; using defaults %s", name, raw, default)
        return default
    return values or default


def _parse_str_tuple_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Read a comma-separated string tuple from env, falling back when empty."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    return values or default


PCI_DSS_CRE_SIMILARITY_THRESHOLDS = _parse_float_tuple_env(
    "PCI_DSS_CRE_SIMILARITY_THRESHOLDS", _DEFAULT_PCI_DSS_CRE_SIMILARITY_THRESHOLDS
)
PCI_BRIDGE_STANDARDS = _parse_str_tuple_env(
    "PCI_DSS_BRIDGE_STANDARDS", _DEFAULT_PCI_BRIDGE_STANDARDS
)
PCI_BRIDGE_MIN_SIMILARITY = _parse_float_env(
    "PCI_DSS_BRIDGE_MIN_SIMILARITY", _DEFAULT_PCI_BRIDGE_MIN_SIMILARITY
)


class PciDssLinkError(Exception):
    """Raised when one or more PCI DSS controls cannot be linked to a CRE."""


def pci_control_embedding_text(control: defs.Standard) -> str:
    """Text used for PCI→CRE similarity (avoid full Standard repr JSON noise)."""
    return "\n".join(
        part.strip()
        for part in (control.sectionID, control.section, control.description)
        if part and str(part).strip()
    )


def best_cre_via_bridge_standard(
    cache: db.Node_collection,
    control_embedding: List[float],
    standard_name: str,
    *,
    min_similarity: float = PCI_BRIDGE_MIN_SIMILARITY,
) -> Optional[defs.CRE]:
    """Pick the best CRE linked to ``standard_name`` by node embedding similarity."""
    import numpy as np
    from scipy import sparse
    from sklearn.metrics.pairwise import cosine_similarity

    if not control_embedding:
        return None

    embedding_array = sparse.csr_matrix(
        np.array(control_embedding, dtype=np.float64).reshape(1, -1)
    )
    best_similarity = -1.0
    best_cre: Optional[defs.CRE] = None

    for node in cache.get_nodes(name=standard_name) or []:
        node_embedding = cache.get_embeddings_for_doc(node)
        if not node_embedding:
            continue
        node_array = sparse.csr_matrix(
            np.array(node_embedding, dtype=np.float64).reshape(1, -1)
        )
        similarity = float(cosine_similarity(embedding_array, node_array)[0][0])
        if similarity < min_similarity or similarity <= best_similarity:
            continue
        linked_cres = cache.find_cres_of_node(node)
        if not linked_cres:
            continue
        cre = cache.get_cre_by_db_id(linked_cres[0].id)
        if cre:
            best_similarity = similarity
            best_cre = cre

    if best_cre:
        logger.info(
            "PCI DSS bridge match via %s (similarity %.3f)",
            standard_name,
            best_similarity,
        )
    return best_cre


def resolve_cre_for_pci_control(
    prompt: prompt_client.PromptHandler,
    cache: db.Node_collection,
    control_embedding: List[float],
) -> Optional[defs.CRE]:
    """Resolve a CRE for one PCI control using staged similarity + bridge fallbacks."""
    for threshold in PCI_DSS_CRE_SIMILARITY_THRESHOLDS:
        match = prompt.get_id_of_most_similar_cre_paginated(
            control_embedding, similarity_threshold=threshold
        )
        if match and match[0]:
            cre = cache.get_cre_by_db_id(match[0])
            if cre:
                logger.info(
                    "PCI DSS CRE similarity match %.3f (threshold %s)",
                    match[1],
                    threshold,
                )
                return cre

    for standard_name in PCI_BRIDGE_STANDARDS:
        cre = best_cre_via_bridge_standard(cache, control_embedding, standard_name)
        if cre:
            return cre

    standard_id = prompt.get_id_of_most_similar_node(control_embedding)
    if standard_id:
        nodes = cache.get_nodes(db_id=standard_id)
        if nodes:
            linked_cres = cache.find_cres_of_node(nodes[0])
            if linked_cres:
                cre = cache.get_cre_by_db_id(linked_cres[0].id)
                if cre:
                    logger.info(
                        "PCI DSS linked via global standard fallback (%s)",
                        nodes[0].name,
                    )
                    return cre
    return None


class PciDss(ParserInterface):
    name = "PCI DSS"

    def _ensure_similarity_prereqs(
        self, cache: db.Node_collection, prompt: prompt_client.PromptHandler
    ) -> None:
        """
        PCI linking relies on CRE embeddings for nearest-neighbor matching.
        Some import runs disable embedding generation, which leaves this parser
        with no way to infer CRE links and silently produces unlinked controls.
        """
        cre_embeddings = cache.get_embeddings_by_doc_type(defs.Credoctypes.CRE.value)
        if cre_embeddings:
            return
        if os.environ.get("CRE_NO_GEN_EMBEDDINGS") == "1":
            logger.warning(
                "CRE embeddings are empty and CRE_NO_GEN_EMBEDDINGS=1; "
                "PCI DSS controls may import without CRE links."
            )
            return
        logger.info(
            "CRE embeddings are empty before PCI DSS parse; generating CRE embeddings now."
        )
        try:
            prompt.generate_embeddings_for(defs.Credoctypes.CRE.value)
        except Exception as ex:
            logger.warning("Failed to generate CRE embeddings for PCI parser: %s", ex)

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        entries = self.parse_4(
            pci_file=sheet_utils.read_spreadsheet(
                alias="",
                url="https://docs.google.com/spreadsheets/d/18weo-qbik_C7SdYq7FSP2OMgUmsWdWWI1eaXcAfMz8I",
                parse_numbered_only=False,
            ),
            cache=cache,
        )
        results = {self.name: entries}
        base_parser_defs.validate_classification_tags(results)
        return ParseResult(results=results)

    def __parse(
        self,
        pci_file: Dict[str, Any],
        cache: db.Node_collection,
        version: str,
        pci_file_tab: str,
        standard_to_spreadsheet_mappings: Dict[str, str],
    ):
        prompt = prompt_client.PromptHandler(cache)
        self._ensure_similarity_prereqs(cache, prompt)
        standard_entries = []
        unlinked_controls: list[str] = []
        for row in pci_file.get(pci_file_tab):
            pci_control = defs.Standard(
                name=self.name,
                section=re.sub(
                    "([CUSTOMIZED APPROACH OBJECTIVE]:.*)",
                    "",
                    str(row.get(standard_to_spreadsheet_mappings["section"], "")),
                ).strip(),
                sectionID=str(
                    row.get(standard_to_spreadsheet_mappings["sectionID"], "")
                ).strip(),
                description=str(
                    row.get(standard_to_spreadsheet_mappings["description"], "")
                ).strip(),
                version=version,
                tags=base_parser_defs.build_tags(
                    family=base_parser_defs.Family.STANDARD,
                    subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
                    audience=(
                        base_parser_defs.Audience.AUDIT
                        if hasattr(base_parser_defs.Audience, "AUDIT")
                        else base_parser_defs.Audience.MANAGEMENT
                    ),
                    maturity=base_parser_defs.Maturity.STABLE,
                    source="pci_dss",
                    extra=[],
                ),
            )
            # Fix for Issue #328: Remove ID from Section Name if duplicated
            if pci_control.section.startswith(pci_control.sectionID):
                # Remove the ID and any leading whitespace/punctuation left over
                pci_control.section = pci_control.section[
                    len(pci_control.sectionID) :
                ].strip()

            existing = cache.get_nodes(
                name=pci_control.name,
                section=pci_control.section,
                sectionID=pci_control.sectionID,
            )
            if existing:
                embeddings = cache.get_embeddings_for_doc(existing[0])
                if embeddings:
                    logger.info(
                        f"Node {pci_control.todict()} already exists and has embeddings, skipping"
                    )

            control_embeddings = prompt.get_text_embeddings(
                pci_control_embedding_text(pci_control)
            )
            pci_control.embeddings = control_embeddings
            pci_control.embeddings_text = pci_control_embedding_text(pci_control)
            cre = resolve_cre_for_pci_control(prompt, cache, control_embeddings)
            pci_control.description = ""
            if cre:
                pci_control.add_link(
                    defs.Link(document=cre, ltype=defs.LinkTypes.AutomaticallyLinkedTo)
                )
                logger.info(f"successfully stored {pci_control.__repr__()}")
            else:
                unlinked_controls.append(
                    f"{pci_control.sectionID}: {pci_control.section}"
                )
                logger.error(
                    "PCI DSS control %s (%s) could not be linked to any CRE",
                    pci_control.sectionID,
                    pci_control.section,
                )
            standard_entries.append(pci_control)
        if unlinked_controls:
            sample = unlinked_controls[:5]
            extra = (
                f" (and {len(unlinked_controls) - len(sample)} more)"
                if len(unlinked_controls) > len(sample)
                else ""
            )
            raise PciDssLinkError(
                "PCI DSS import requires every control to link to a CRE; "
                f"{len(unlinked_controls)} control(s) failed: "
                f"{'; '.join(sample)}{extra}"
            )
        return standard_entries

    def parse_3_2(self, pci_file: Dict[str, Any], cache: db.Node_collection):
        self.__parse(
            pci_file=pci_file,
            cache=cache,
            version="3.2",
            pci_file_tab="Table 1 (3)",
            standard_to_spreadsheet_mappings={
                "section": "Control Description",
                "sectionID": "CID",
                "description": "Requirement Description",
            },
        )

    def parse_4(self, pci_file: Dict[str, Any], cache: db.Node_collection):
        return self.__parse(
            pci_file=pci_file,
            cache=cache,
            version="4",
            pci_file_tab="Original Content",
            standard_to_spreadsheet_mappings={
                "section": "Defined Approach Requirements",
                "sectionID": "PCI DSS ID",
                "description": "Requirement Description",
            },
        )
