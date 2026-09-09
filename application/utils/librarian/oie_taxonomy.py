"""OIE taxonomy vocabulary + DB-backed index (no static section/keyword maps).

Runtime classification and priors load from ``Node.metadata_json["oie"]`` and
``CRE.metadata_json["oie"]`` (SQL column ``document_metadata``). Populate those
blocks with::

  PYTHONPATH=. python scripts/oie_tag_standard_sections.py --cache-file ...
  PYTHONPATH=. python scripts/oie_tag_cre_families.py --cache-file ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Coarse family vocabulary (names only — not a classification map).
FAMILIES = frozenset(
    {
        "auth",
        "access",
        "crypto",
        "injection",
        "logging",
        "integrity",
        "configuration",
        "availability",
        "ssrf",
        "secrets",
        "network",
        "ai",
        "api",
        "cloud",
        "appsec",
        "gov",
    }
)

OIE_META_VERSION = 2

# Expand class with related peers when smaller than this.
THIN_CLASS_THRESHOLD = 8
# Also pull sibling-transfer CREs when still smaller than this after related.
THIN_TRANSFER_THRESHOLD = 15

_DEFAULT_INDEX: Optional["TaxonomyIndex"] = None


def normalize_section_id(raw: str) -> str:
    return (raw or "").strip().upper()


def oie_block(meta: Any) -> Mapping[str, Any]:
    if isinstance(meta, Mapping):
        block = meta.get("oie")
        if isinstance(block, Mapping):
            return block
    return {}


@dataclass(frozen=True)
class TaxonomyIndex:
    """In-memory view of OIE tags loaded from Node/CRE ``document_metadata``."""

    section_id_to_class: Mapping[str, Tuple[str, str]] = field(default_factory=dict)
    #: (phrase_lower, class_id, family), longest phrases first.
    phrases: Tuple[Tuple[str, str, str], ...] = ()
    related_classes: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    family_to_transfer: Mapping[str, str] = field(default_factory=dict)
    #: (needle_lower, family) for Standard: → family defaults.
    standard_hints: Tuple[Tuple[str, str], ...] = ()

    @classmethod
    def empty(cls) -> "TaxonomyIndex":
        return cls()

    def lookup_section_id(self, section_id: str) -> Optional[Tuple[str, str]]:
        return self.section_id_to_class.get(normalize_section_id(section_id))

    def match_phrases(self, blob: str) -> Optional[Tuple[str, str]]:
        text = (blob or "").lower()
        if not text:
            return None
        for phrase, class_id, family in self.phrases:
            if phrase and phrase in text:
                return class_id, family
        return None

    def family_for_standard(self, standard: str) -> Optional[str]:
        text = (standard or "").lower()
        if not text:
            return None
        for needle, family in self.standard_hints:
            if needle and needle in text:
                return family
        return None

    @classmethod
    def from_node_metadata(
        cls, nodes: Iterable[Any], *, min_phrase_len: int = 3
    ) -> "TaxonomyIndex":
        """Build index from Node ORM rows (or duck-typed objects with metadata)."""
        section_map: Dict[str, Tuple[str, str]] = {}
        phrase_rows: List[Tuple[str, str, str]] = []
        related: Dict[str, List[str]] = {}
        family_transfer: Dict[str, str] = {}
        hints: List[Tuple[str, str]] = []
        seen_phrases: set = set()
        seen_hints: set = set()

        for node in nodes:
            meta = getattr(node, "metadata_json", None)
            if meta is None and isinstance(node, Mapping):
                meta = node.get("metadata_json") or node.get("oie") and node
            oie = oie_block(meta if not isinstance(node, Mapping) else meta)
            if not oie and isinstance(node, Mapping) and "class_id" in node:
                oie = node

            class_id = str(oie.get("class_id") or "").strip()
            family = str(oie.get("family") or "").strip()
            sid_raw = oie.get("section_id")
            if sid_raw is None:
                sid_raw = getattr(node, "section_id", None)
            sid = normalize_section_id(str(sid_raw or ""))

            if sid and class_id and family:
                section_map.setdefault(sid, (class_id, family))

            if class_id and family:
                section_title = (
                    getattr(node, "section", None) or oie.get("section_title") or ""
                )
                title = str(section_title).strip().lower()
                if len(title) >= min_phrase_len:
                    key = (title, class_id, family)
                    if key not in seen_phrases:
                        seen_phrases.add(key)
                        phrase_rows.append(key)
                for phrase in oie.get("phrases") or []:
                    p = str(phrase).strip().lower()
                    if len(p) < min_phrase_len:
                        continue
                    key = (p, class_id, family)
                    if key not in seen_phrases:
                        seen_phrases.add(key)
                        phrase_rows.append(key)
                # Verbose LLM enrichment fields (aliases / related topics / summary).
                for extra_key in ("aliases", "related_topics"):
                    for phrase in oie.get(extra_key) or []:
                        p = str(phrase).strip().lower()
                        if len(p) < min_phrase_len:
                            continue
                        key = (p, class_id, family)
                        if key not in seen_phrases:
                            seen_phrases.add(key)
                            phrase_rows.append(key)
                summary = str(oie.get("summary") or "").strip().lower()
                if len(summary) >= min_phrase_len:
                    # Index first ~120 chars as a soft phrase, not the full essay.
                    clip = summary[:120].rsplit(" ", 1)[0] or summary[:120]
                    key = (clip, class_id, family)
                    if key not in seen_phrases:
                        seen_phrases.add(key)
                        phrase_rows.append(key)

            peers = oie.get("related_classes") or []
            if class_id and peers:
                slot = related.setdefault(class_id, [])
                for peer in peers:
                    p = str(peer).strip()
                    if p and p not in slot:
                        slot.append(p)

            transfer = str(oie.get("transfer") or "").strip()
            if family and transfer:
                family_transfer.setdefault(family, transfer)

            for hint in oie.get("standard_hints") or []:
                h = str(hint).strip().lower()
                hint_family = str(oie.get("standard_family") or family or "").strip()
                if h and hint_family and (h, hint_family) not in seen_hints:
                    seen_hints.add((h, hint_family))
                    hints.append((h, hint_family))

            # Do not map Node.name → problem family: names like "OWASP Top 10"
            # would attach section families (access/auth) to Standard: defaults.

        phrase_rows.sort(key=lambda row: len(row[0]), reverse=True)
        # Longer / more specific standard hints first.
        hints.sort(key=lambda row: len(row[0]), reverse=True)

        return cls(
            section_id_to_class=section_map,
            phrases=tuple(phrase_rows),
            related_classes={k: tuple(v) for k, v in related.items()},
            family_to_transfer=dict(family_transfer),
            standard_hints=tuple(hints),
        )


def get_default_taxonomy_index() -> TaxonomyIndex:
    return _DEFAULT_INDEX or TaxonomyIndex.empty()


def set_default_taxonomy_index(index: Optional[TaxonomyIndex]) -> None:
    """Install process-wide index (factory / tests). Pass None to clear."""
    global _DEFAULT_INDEX
    _DEFAULT_INDEX = index


def load_taxonomy_index_from_session(session: Any) -> TaxonomyIndex:
    """Query Node rows and build a TaxonomyIndex from ``document_metadata.oie``."""
    from application.database.db import Node

    nodes = session.query(Node).filter(Node.metadata_json.isnot(None)).all()
    # Also include Nodes with section_id even if metadata empty (titles only).
    extra = (
        session.query(Node)
        .filter(Node.section_id.isnot(None), Node.metadata_json.is_(None))
        .all()
    )
    return TaxonomyIndex.from_node_metadata(list(nodes) + list(extra))


def lookup_section_id(
    section_id: str, index: Optional[TaxonomyIndex] = None
) -> Optional[Tuple[str, str]]:
    return (index or get_default_taxonomy_index()).lookup_section_id(section_id)


def match_keywords(
    blob: str, index: Optional[TaxonomyIndex] = None
) -> Optional[Tuple[str, str]]:
    return (index or get_default_taxonomy_index()).match_phrases(blob)


def family_for_standard(
    standard: str, index: Optional[TaxonomyIndex] = None
) -> Optional[str]:
    return (index or get_default_taxonomy_index()).family_for_standard(standard)


__all__ = [
    "FAMILIES",
    "OIE_META_VERSION",
    "THIN_CLASS_THRESHOLD",
    "THIN_TRANSFER_THRESHOLD",
    "TaxonomyIndex",
    "family_for_standard",
    "get_default_taxonomy_index",
    "load_taxonomy_index_from_session",
    "lookup_section_id",
    "match_keywords",
    "normalize_section_id",
    "oie_block",
    "set_default_taxonomy_index",
]
