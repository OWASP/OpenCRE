"""Seed C.1 preferred/prior from hub Links on any known standard family.

When a chunk carries ``Standard:`` / ``Section-ID:`` that match Nodes already
Linked in the hub, prefer those CRE UUIDs. Optional catalog bags (e.g. AI
Exchange) expand the soft-cage allowlist.

Loaded from DB Links at factory time — no hand-maintained SECTION_ID maps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from application.utils.librarian.problem_class import ProblemClass

_STANDARD_LINE = re.compile(r"(?im)^Standard:\s*(.+)$")
_VERSION_LINE = re.compile(r"(?im)^Version:\s*(.+)$")
_SOURCE_LINE = re.compile(r"(?im)^Source:\s*(.+)$")
_SECTION_ID_LINE = re.compile(r"(?im)^Section-ID:\s*(.+)$")
_YEAR = re.compile(r"(20\d{2})")

_SID_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(A\d{2}|API\d{1,2}|LLM\d{2}|K\d{2}|AISVS[\d.]+)(?![A-Za-z0-9])",
    re.I,
)


@dataclass(frozen=True)
class CatalogSpec:
    """One standard family whose hub Links can seed preferred CREs."""

    key: str
    node_patterns: Tuple[re.Pattern[str], ...]
    chunk_patterns: Tuple[re.Pattern[str], ...] = ()
    bag_only: bool = False
    problem_families: FrozenSet[str] = field(default_factory=frozenset)


_CATALOGS: Tuple[CatalogSpec, ...] = (
    CatalogSpec(
        key="llm_top10",
        node_patterns=(re.compile(r"top\s*10\s*for\s*llm|llm\s*top\s*10", re.I),),
        chunk_patterns=(
            re.compile(r"llm|genai", re.I),
            re.compile(r"(?<![A-Za-z0-9])LLM\d{2}", re.I),
        ),
        problem_families=frozenset({"ai"}),
    ),
    CatalogSpec(
        key="ai_exchange",
        node_patterns=(re.compile(r"ai\s*exchange", re.I),),
        chunk_patterns=(re.compile(r"llm|genai|ai\s*exchange", re.I),),
        bag_only=True,
        problem_families=frozenset({"ai"}),
    ),
    CatalogSpec(
        key="k8s_top10",
        node_patterns=(re.compile(r"kubernetes|k8s", re.I),),
        chunk_patterns=(
            re.compile(r"kubernetes|k8s", re.I),
            re.compile(r"(?<![A-Za-z0-9])K\d{2}", re.I),
        ),
    ),
    CatalogSpec(
        key="owasp_top10",
        node_patterns=(
            re.compile(r"owasp\s*top\s*10(?!.*\b(llm|api|k8s|kubernetes|ml)\b)", re.I),
        ),
        chunk_patterns=(
            re.compile(
                r"owasp[_\s-]*top[_\s-]*10(?!.*\b(llm|api|k8s|kubernetes|ml)\b)",
                re.I,
            ),
            re.compile(r"(?<![A-Za-z0-9])A\d{2}(?![A-Za-z0-9])", re.I),
        ),
    ),
    CatalogSpec(
        key="api_top10",
        node_patterns=(re.compile(r"api\s*(security\s*)?top\s*10|owasp\s*api", re.I),),
        chunk_patterns=(
            re.compile(r"api[_\s-]*(security[_\s-]*)?top[_\s-]*10|owasp[_\s-]*api", re.I),
            re.compile(r"(?<![A-Za-z0-9])API\d{1,2}", re.I),
        ),
    ),
    CatalogSpec(
        key="aisvs",
        node_patterns=(re.compile(r"\baisvs\b", re.I),),
        chunk_patterns=(
            re.compile(r"\baisvs\b", re.I),
            re.compile(r"(?<![A-Za-z0-9])AISVS", re.I),
        ),
        problem_families=frozenset({"ai"}),
    ),
    CatalogSpec(
        key="ccm",
        node_patterns=(re.compile(r"\bccm\b|cloud\s*controls\s*matrix", re.I),),
        chunk_patterns=(re.compile(r"\bccm\b|cloud\s*controls", re.I),),
    ),
)


def normalize_section_id(raw: str) -> str:
    """``LLM01:2025`` / ``K01`` / ``A01`` → canonical uppercase id without year."""
    text = (raw or "").strip().upper()
    if not text:
        return ""
    text = text.split(":")[0].strip()
    m = _SID_TOKEN.search(text)
    if m:
        return m.group(1).upper()
    if re.match(r"^(A\d{2}|API\d{1,2}|LLM\d{2}|K\d{2})$", text, re.I):
        return text.upper()
    return ""


def section_id_from_text(text: str) -> str:
    """Best-effort section id from Source / Section-ID prefixes."""
    src = _SOURCE_LINE.search(text or "")
    if src:
        sid = normalize_section_id(src.group(1))
        if sid:
            return sid
    sid_line = _SECTION_ID_LINE.search(text or "")
    if sid_line:
        toks = _SID_TOKEN.findall(sid_line.group(1))
        if toks:
            return toks[0].upper()
        sid = normalize_section_id(sid_line.group(1))
        if sid:
            return sid
    m = _SID_TOKEN.search(text or "")
    return m.group(1).upper() if m else ""


def standard_label_from_text(text: str) -> str:
    m = _STANDARD_LINE.search(text or "")
    return m.group(1).strip() if m else ""


def year_from_text(text: str) -> int:
    """Prefer ``Version:`` year, else year in ``Standard:`` / body head."""
    ver = _VERSION_LINE.search(text or "")
    if ver:
        m = _YEAR.search(ver.group(1))
        if m:
            return int(m.group(1))
    label = standard_label_from_text(text)
    if label:
        m = _YEAR.search(label)
        if m:
            return int(m.group(1))
    m = _YEAR.search((text or "")[:400])
    return int(m.group(1)) if m else 0


def year_from_node(name: str, version: str = "") -> int:
    for blob in (version or "", name or ""):
        m = _YEAR.search(blob)
        if m:
            return int(m.group(1))
    return 0


@dataclass(frozen=True)
class EditionLinkMap:
    """One edition (year) of a catalog: section_id → CRE UUIDs."""

    year: int
    section_to_cres: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class StandardLinkIndex:
    """Hub Link index: per-catalog editions + optional bags (CRE UUIDs)."""

    editions: Mapping[str, Tuple[EditionLinkMap, ...]] = field(default_factory=dict)
    bags: Mapping[str, FrozenSet[str]] = field(default_factory=dict)
    catalog_node_names: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "StandardLinkIndex":
        return cls()

    @property
    def section_maps(self) -> Mapping[str, Mapping[str, Tuple[str, ...]]]:
        """Flat union per catalog (tests / debug). Prefer ``preferred_for``."""
        out: Dict[str, Dict[str, List[str]]] = {}
        for key, eds in self.editions.items():
            bucket: Dict[str, List[str]] = {}
            for ed in eds:
                for sid, cres in ed.section_to_cres.items():
                    lst = bucket.setdefault(sid, [])
                    for c in cres:
                        if c not in lst:
                            lst.append(c)
            out[key] = {sid: tuple(v) for sid, v in bucket.items()}
        return out

    def _catalog_active(
        self, catalog: CatalogSpec, problem: ProblemClass, text: str
    ) -> bool:
        if problem.family in catalog.problem_families:
            return True
        label = standard_label_from_text(text)
        blob = " ".join(
            [
                label,
                text[:1200] if text else "",
                problem.section_id or "",
                problem.class_id or "",
                problem.family or "",
            ]
        )
        patterns = catalog.chunk_patterns or catalog.node_patterns
        return any(p.search(blob) for p in patterns)

    def _editions_for(
        self, catalog_key: str, year: int
    ) -> Sequence[EditionLinkMap]:
        eds = self.editions.get(catalog_key) or ()
        if not eds:
            return ()
        if year:
            matched = [e for e in eds if e.year == year]
            if matched:
                return matched
        return eds

    def preferred_for(self, problem: ProblemClass, text: str = "") -> List[str]:
        """Ordered CRE UUIDs Linked from matching catalog section Nodes."""
        sid = normalize_section_id(problem.section_id) or section_id_from_text(text)
        if not sid:
            return []
        year = year_from_text(text)
        out: List[str] = []
        seen: Set[str] = set()
        for catalog in _CATALOGS:
            if catalog.bag_only:
                continue
            if catalog.key not in self.editions:
                continue
            if not self._catalog_active(catalog, problem, text):
                continue
            for ed in self._editions_for(catalog.key, year):
                for cre_id in ed.section_to_cres.get(sid, ()):
                    if cre_id not in seen:
                        seen.add(cre_id)
                        out.append(cre_id)
        return out

    def prior_extra_for(self, problem: ProblemClass, text: str = "") -> FrozenSet[str]:
        """Bag CRE UUIDs (e.g. AI Exchange) to union into the soft-cage allowlist."""
        extra: Set[str] = set()
        for catalog in _CATALOGS:
            if not catalog.bag_only:
                continue
            bag = self.bags.get(catalog.key)
            if not bag:
                continue
            if self._catalog_active(catalog, problem, text):
                extra |= set(bag)
        return frozenset(extra)

    def has_section_links(self, problem: ProblemClass, text: str = "") -> bool:
        return bool(self.preferred_for(problem, text))


def _match_catalog(node_name: str) -> Optional[CatalogSpec]:
    for catalog in _CATALOGS:
        if any(p.search(node_name) for p in catalog.node_patterns):
            return catalog
    return None


def build_standard_link_index(session: Any) -> StandardLinkIndex:
    """Load section→CRE and bag maps from ``cre_node_links``."""
    from application.database.db import CRE, Links, Node

    nested: Dict[str, Dict[int, Dict[str, List[str]]]] = {}
    bags: Dict[str, Set[str]] = {}
    names: Dict[str, Set[str]] = {}

    rows = (
        session.query(Node.name, Node.version, Node.section_id, CRE.id)
        .join(Links, Links.node == Node.id)
        .join(CRE, CRE.id == Links.cre)
        .all()
    )
    for name, version, section_id, cre_id in rows:
        if not cre_id or not name:
            continue
        catalog = _match_catalog(str(name))
        if catalog is None:
            continue
        names.setdefault(catalog.key, set()).add(str(name))
        if catalog.bag_only:
            bags.setdefault(catalog.key, set()).add(cre_id)
            continue
        sid = normalize_section_id(str(section_id or ""))
        if not sid:
            continue
        year = year_from_node(str(name), str(version or ""))
        bucket = (
            nested.setdefault(catalog.key, {})
            .setdefault(year, {})
            .setdefault(sid, [])
        )
        if cre_id not in bucket:
            bucket.append(cre_id)

    editions: Dict[str, Tuple[EditionLinkMap, ...]] = {}
    for ck, by_year in nested.items():
        eds = []
        for year, sid_map in sorted(by_year.items()):
            eds.append(
                EditionLinkMap(
                    year=year,
                    section_to_cres={
                        sid: tuple(ids) for sid, ids in sorted(sid_map.items())
                    },
                )
            )
        editions[ck] = tuple(eds)

    return StandardLinkIndex(
        editions=editions,
        bags={k: frozenset(v) for k, v in bags.items()},
        catalog_node_names={k: tuple(sorted(v)) for k, v in names.items()},
    )


def hub_external_ids_by_section(
    session: Any,
    *,
    catalog_key: str,
    year: int = 0,
) -> Dict[str, List[str]]:
    """``section_id`` → distinct ``CRE.external_id`` for one catalog (gold rebuild)."""
    from application.database.db import CRE, Links, Node

    catalog = next((c for c in _CATALOGS if c.key == catalog_key), None)
    if catalog is None or catalog.bag_only:
        return {}

    out: Dict[str, List[str]] = {}
    rows = (
        session.query(Node.name, Node.version, Node.section_id, CRE.external_id)
        .join(Links, Links.node == Node.id)
        .join(CRE, CRE.id == Links.cre)
        .all()
    )
    for name, version, section_id, ext in rows:
        if not name or not ext:
            continue
        if not any(p.search(str(name)) for p in catalog.node_patterns):
            continue
        node_year = year_from_node(str(name), str(version or ""))
        if year and node_year and node_year != year:
            continue
        sid = normalize_section_id(str(section_id or ""))
        if not sid:
            continue
        bucket = out.setdefault(sid, [])
        if ext not in bucket:
            bucket.append(str(ext))
    return out


def normalize_llm_section_id(raw: str) -> str:
    sid = normalize_section_id(raw)
    return sid if sid.startswith("LLM") else ""


__all__ = [
    "CatalogSpec",
    "EditionLinkMap",
    "StandardLinkIndex",
    "build_standard_link_index",
    "hub_external_ids_by_section",
    "normalize_section_id",
    "normalize_llm_section_id",
    "section_id_from_text",
    "standard_label_from_text",
    "year_from_text",
    "year_from_node",
]
