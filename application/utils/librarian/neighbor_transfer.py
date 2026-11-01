"""Neighbor-standard transfer for brand-new catalogs (path B).

When a chunk is K8s / API / new Top10 and the *same* standard has no
(or thin) hub Links:

1. **Narrow winners** — soft-cage only to title/topic/control winners (≤~30),
   never the full CCM/ASVS Linked set.
2. **Title latch** — fuzzy Section: ↔ neighbor section titles + ``oie.phrases``.
3. **Topic remap** — heuristic (LLM opt-in): chunk section → neighbor section
   ids → Linked CREs. Dynamic; no hand CRE maps.

AISVS neighbor transfer is off (pollutes the shortlist). K8s is heuristic-only.
Topic pins require a title latch (title ∩ topic) so noisy remaps do not pin.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from application.utils.librarian.control_name_seed import (
    _overlap,
    _tokens,
    section_title_from_text,
)
from application.utils.librarian.edition_remap import (
    EditionSection,
    LlmFn,
    _FAMILY_PATTERNS,
    family_and_year,
    heuristic_remap,
    parse_chunk_standard,
    parse_llm_remap_json,
    validate_remap,
)
from application.utils.librarian.problem_class import ProblemClass
from application.utils.librarian.standard_link_seed import (
    section_id_from_text,
    standard_label_from_text,
)

logger = logging.getLogger(__name__)

# Source catalog family → regexes matching **neighbor** Node.name values in hub.
_NEIGHBOR_NODE_PATTERNS: Mapping[str, Tuple[re.Pattern[str], ...]] = {
    "owasp_k8s_top10": (
        re.compile(r"cloud\s*controls\s*matrix", re.I),
        re.compile(r"nist\s*800-53", re.I),
    ),
    "owasp_api_top10": (
        re.compile(r"^ASVS$", re.I),
        re.compile(r"owasp\s*top\s*10(?!.*\b(llm|api|ml)\b)", re.I),
        re.compile(r"cheat\s*sheets?", re.I),
        re.compile(r"proactive\s*controls", re.I),
    ),
    "owasp_top10": (
        re.compile(r"^ASVS$", re.I),
        re.compile(r"cheat\s*sheets?", re.I),
        re.compile(r"proactive\s*controls", re.I),
        re.compile(r"wstg|web\s*security\s*testing", re.I),
    ),
    "owasp_aisvs": (
        re.compile(r"ai\s*exchange", re.I),
        re.compile(r"top\s*10\s*for\s*llm|llm\s*top\s*10", re.I),
        re.compile(r"nist\s*ai", re.I),
        re.compile(r"top\s*10\s*for\s*ml", re.I),
    ),
    "owasp_llm_top10": (
        re.compile(r"ai\s*exchange", re.I),
        re.compile(r"nist\s*ai", re.I),
        re.compile(r"top\s*10\s*for\s*ml", re.I),
    ),
}

_SID_FAMILY: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("owasp_api_top10", re.compile(r"^API\d{1,2}$", re.I)),
    ("owasp_k8s_top10", re.compile(r"^K\d{2}$", re.I)),
    ("owasp_llm_top10", re.compile(r"^LLM\d{2}$", re.I)),
    ("owasp_aisvs", re.compile(r"^AISVS", re.I)),
    ("owasp_top10", re.compile(r"^A\d{2}$", re.I)),
)

_SYNONYM_GROUPS: Tuple[FrozenSet[str], ...] = (
    frozenset(
        {
            "authorization",
            "authorisation",
            "authorize",
            "access",
            "rbac",
            "iam",
            "permission",
            "permissions",
            "permissive",
            "privilege",
            "privileges",
        }
    ),
    frozenset(
        {
            "authentication",
            "authenticate",
            "authn",
            "login",
            "session",
            "identity",
            "credential",
            "credentials",
        }
    ),
    frozenset({"secret", "secrets", "key", "keys", "password", "passwords"}),
    frozenset(
        {
            "network",
            "segmentation",
            "segregation",
            "isolation",
            "isolate",
            "firewall",
            "lateral",
        }
    ),
    frozenset({"logging", "monitoring", "monitor", "audit", "log", "alerting"}),
    frozenset(
        {
            "misconfiguration",
            "misconfigured",
            "configuration",
            "configurations",
            "hardening",
            "harden",
            "workload",
        }
    ),
    frozenset({"inventory", "component", "components", "dependency", "dependencies"}),
    frozenset({"ssrf", "forgery", "request"}),
    frozenset({"injection", "inject"}),
    frozenset({"consumption", "dos", "rate", "resource", "resources", "exhaustion"}),
)

# Cap how many neighbor sections we send to the LLM / keep in narrow prior.
_LLM_CANDIDATE_SECTIONS = 40
_NARROW_PRIOR_MAX = 28

# AISVS neighbor bags (CCM/ASVS-shaped) pollute the CE shortlist; keep off.
_DISABLED_FAMILIES: FrozenSet[str] = frozenset({"owasp_aisvs"})
# K8s title latch is high-precision; LLM topic remap was noisy on B2.
_HEURISTIC_ONLY_FAMILIES: FrozenSet[str] = frozenset({"owasp_k8s_top10"})


def detect_standard_family(text: str, problem: Optional[ProblemClass] = None) -> str:
    """Best-effort catalog family for neighbor transfer (may be empty)."""
    parsed = parse_chunk_standard(text or "")
    if parsed:
        return parsed[0]
    label = standard_label_from_text(text or "")
    blob = label.replace("_", " ").replace(".json", "")
    if blob:
        fy = family_and_year(blob + " 2020")
        if fy:
            return fy[0]
        for family, pattern in _FAMILY_PATTERNS:
            if pattern.search(blob):
                return family
    sid = ""
    if problem and problem.section_id:
        sid = str(problem.section_id).split(":")[0].strip().upper()
    if not sid:
        sid = section_id_from_text(text or "")
    for family, pattern in _SID_FAMILY:
        if sid and pattern.match(sid):
            return family
    if problem and problem.family == "ai":
        return "owasp_llm_top10"
    if problem and problem.family == "cloud":
        return "owasp_k8s_top10"
    if problem and problem.family == "api":
        return "owasp_api_top10"
    return ""


def _expand_tokens(tokens: Set[str]) -> Set[str]:
    out = set(tokens)
    for group in _SYNONYM_GROUPS:
        if out & group:
            out |= set(group)
    return out


def _title_score(query: Set[str], title: str) -> float:
    return _overlap(_expand_tokens(query), _expand_tokens(_tokens(title)))


def build_cross_standard_remap_prompt(
    *,
    source_family: str,
    new_sections: Sequence[EditionSection],
    old_sections: Sequence[EditionSection],
) -> Tuple[str, str]:
    system = (
        "You map a NEW security-standard section to RELATED standards already "
        "in a knowledge graph (e.g. Kubernetes Top 10 → Cloud Controls Matrix / "
        "NIST 800-53; API Top 10 → ASVS / OWASP Top 10). "
        "Return ONLY JSON: keys are NEW section ids, values are arrays of OLD "
        "section ids from the provided list (usually 1–3). Prefer topic/title "
        "match. Never invent ids. Empty array if none fit."
    )
    payload = {
        "source_family": source_family,
        "new_sections": [{"id": s.section_id, "title": s.title} for s in new_sections],
        "related_sections": [
            {"id": s.section_id, "title": s.title} for s in old_sections
        ],
    }
    user = (
        "Map new → related section ids.\n"
        + json.dumps(payload, indent=2)
        + '\n\nRespond like: {"K05": ["Cloud Controls Matrix|IVS-06", "…"]}'
    )
    return system, user


@dataclass(frozen=True)
class NeighborSectionHit:
    key: str
    title: str
    cre_ids: Tuple[str, ...]
    aliases: Tuple[str, ...] = ()

    def all_titles(self) -> Tuple[str, ...]:
        out = [self.title]
        for a in self.aliases:
            if a and a not in out:
                out.append(a)
        return tuple(out)

    def best_score(self, query: Set[str]) -> float:
        return max((_title_score(query, t) for t in self.all_titles()), default=0.0)


@dataclass
class NeighborRemapCache:
    memory: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)
    disk_dir: Optional[Path] = None

    def get(self, key: str) -> Optional[Dict[str, List[str]]]:
        if key in self.memory:
            return self.memory[key]
        if self.disk_dir is not None:
            path = self.disk_dir / f"{key}.json"
            if path.is_file():
                data = json.loads(path.read_text())
                self.memory[key] = data
                return data
        return None

    def put(self, key: str, remap: Dict[str, List[str]]) -> None:
        self.memory[key] = remap
        if self.disk_dir is not None:
            self.disk_dir.mkdir(parents=True, exist_ok=True)
            (self.disk_dir / f"{key}.json").write_text(
                json.dumps(remap, indent=2, sort_keys=True)
            )


@dataclass
class NeighborTransferIndex:
    """Organic neighbor winners + LLM/heuristic topic transfer."""

    bags: Mapping[str, FrozenSet[str]] = field(default_factory=dict)
    sections: Mapping[str, Tuple[NeighborSectionHit, ...]] = field(default_factory=dict)
    title_min_score: float = 0.22
    topic_min_score: float = 0.15
    preferred_limit: int = 12
    narrow_prior_max: int = _NARROW_PRIOR_MAX
    llm_fn: Optional[LlmFn] = None
    cache: Optional[NeighborRemapCache] = None
    disabled_families: FrozenSet[str] = field(
        default_factory=lambda: frozenset(_DISABLED_FAMILIES)
    )
    heuristic_only_families: FrozenSet[str] = field(
        default_factory=lambda: frozenset(_HEURISTIC_ONLY_FAMILIES)
    )
    pin_require_title_overlap: bool = True

    @classmethod
    def empty(cls) -> "NeighborTransferIndex":
        return cls()

    def bag_for(self, family: str) -> FrozenSet[str]:
        """Full neighbor Linked set (for ranking boosts only — not soft-cage)."""
        return self.bags.get(family, frozenset())

    def preferred_by_title(self, family: str, text: str) -> List[str]:
        title = section_title_from_text(text)
        query = _tokens(title)
        if len(query) < 2:
            return []
        scored: List[Tuple[float, str]] = []
        seen: Set[str] = set()
        for hit in self.sections.get(family, ()):
            score = hit.best_score(query)
            if score < self.title_min_score:
                continue
            for cid in hit.cre_ids:
                if cid and cid not in seen:
                    scored.append((score, cid))
                    seen.add(cid)
        scored.sort(reverse=True)
        return [cid for _, cid in scored[: self.preferred_limit]]

    def _shortlist_neighbor_sections(
        self, family: str, title: str
    ) -> List[NeighborSectionHit]:
        query = _tokens(title)
        hits = list(self.sections.get(family) or ())
        if not hits:
            return []
        ranked = sorted(
            ((h.best_score(query), h) for h in hits),
            key=lambda x: x[0],
            reverse=True,
        )
        kept = [h for score, h in ranked if score >= self.topic_min_score]
        if len(kept) < 8:
            kept = [h for _, h in ranked[:_LLM_CANDIDATE_SECTIONS]]
        return kept[:_LLM_CANDIDATE_SECTIONS]

    def preferred_by_topic_remap(self, family: str, text: str) -> List[str]:
        """LLM (cached) then heuristic remap → neighbor CRE UUIDs."""
        hits = self.sections.get(family) or ()
        if not hits:
            return []
        title = section_title_from_text(text)
        sid = section_id_from_text(text) or "NEW"
        if not title:
            return []

        candidates = self._shortlist_neighbor_sections(family, title)
        if not candidates:
            return []

        new_sections = (EditionSection(section_id=sid, title=title),)
        old_sections = tuple(
            EditionSection(section_id=h.key, title=h.title) for h in candidates
        )
        old_ids = self._remap_ids(family, sid, new_sections, old_sections)
        if not old_ids:
            best: List[Tuple[float, str]] = []
            q = _tokens(title)
            for h in candidates:
                sc = h.best_score(q)
                if sc >= self.topic_min_score:
                    best.append((sc, h.key))
            best.sort(reverse=True)
            old_ids = [k for _, k in best[:3]]

        cres_by_key = {h.key: h.cre_ids for h in candidates}
        out: List[str] = []
        seen: Set[str] = set()
        for oid in old_ids:
            for cid in cres_by_key.get(oid, ()):
                if cid not in seen:
                    seen.add(cid)
                    out.append(cid)
            if len(out) >= self.preferred_limit:
                break
        return out[: self.preferred_limit]

    def _remap_ids(
        self,
        family: str,
        sid: str,
        new_sections: Sequence[EditionSection],
        old_sections: Sequence[EditionSection],
    ) -> List[str]:
        cache = self.cache or NeighborRemapCache()
        fp = hashlib.sha256(
            json.dumps(
                {
                    "n": [(s.section_id, s.title) for s in new_sections],
                    "o": [(s.section_id, s.title) for s in old_sections],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]
        key = f"xstd_{family}_{sid}_{fp}"
        hit = cache.get(key)
        if hit is not None:
            return list(hit.get(sid.upper(), []) or hit.get(sid, []) or [])

        raw: Dict[str, List[str]] = {}
        use_llm = self.llm_fn is not None and family not in self.heuristic_only_families
        if use_llm:
            try:
                system, user = build_cross_standard_remap_prompt(
                    source_family=family,
                    new_sections=new_sections,
                    old_sections=old_sections,
                )
                raw = parse_llm_remap_json(self.llm_fn(system, user))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "cross-standard remap LLM failed; heuristic", exc_info=True
                )
                raw = {}
        if not raw:
            raw = heuristic_remap(new_sections, old_sections)
        new_ids = {s.section_id.upper() for s in new_sections}
        old_ids = {s.section_id.upper() for s in old_sections}
        # Keys may be mixed-case composite ids — validate case-insensitively.
        clean = validate_remap(
            {k.upper(): v for k, v in raw.items()},
            new_ids=new_ids,
            old_ids=old_ids,
        )
        # validate uppercases values; restore original old keys when possible
        old_by_upper = {s.section_id.upper(): s.section_id for s in old_sections}
        restored: Dict[str, List[str]] = {}
        for nk, vals in clean.items():
            restored[nk] = [old_by_upper.get(v.upper(), v) for v in vals]
        cache.put(key, restored)
        self.cache = cache
        return list(restored.get(sid.upper(), []) or [])

    def apply(
        self, problem: ProblemClass, text: str
    ) -> Tuple[FrozenSet[str], List[str], List[str], FrozenSet[str]]:
        """Return ``(narrow_prior, title_pref, topic_pref, full_bag)``.

        ``narrow_prior`` is what soft-cage should use (winners only).
        ``full_bag`` is only for boosting control-name hits.
        """
        family = detect_standard_family(text, problem)
        if (
            not family
            or family in self.disabled_families
            or (family not in self.bags and family not in self.sections)
        ):
            return frozenset(), [], [], frozenset()
        full_bag = self.bag_for(family)
        title_pref = self.preferred_by_title(family, text)
        topic_pref = self.preferred_by_topic_remap(family, text)
        if self.pin_require_title_overlap:
            title_set = set(title_pref)
            if title_set:
                topic_pref = [cid for cid in topic_pref if cid in title_set]
            else:
                topic_pref = []
        winners = list(dict.fromkeys([*title_pref, *topic_pref]))[
            : self.narrow_prior_max
        ]
        narrow = frozenset(winners)
        return narrow, title_pref, topic_pref, full_bag


def _oie_phrases(meta: Any) -> List[str]:
    """Collect all matchable strings from verbose ``oie`` metadata."""
    if not isinstance(meta, dict):
        return []
    oie = meta.get("oie") or {}
    if not isinstance(oie, dict):
        return []
    try:
        from application.utils.librarian.metadata_enricher import match_text_blob

        blob = match_text_blob(oie)
        # Split blob into lines / comma-ish chunks for alias list
        parts: List[str] = []
        for line in blob.splitlines():
            s = line.strip()
            if s:
                parts.append(s)
        return parts
    except Exception:  # noqa: BLE001
        out: List[str] = []
        for key in ("section_title", "summary", "aliases", "phrases", "related_topics"):
            val = oie.get(key)
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
            elif isinstance(val, list):
                out.extend(str(x).strip() for x in val if x)
        return out


def build_neighbor_transfer_index(
    session: Any,
    *,
    llm_fn: Optional[LlmFn] = None,
    cache_dir: Optional[Path] = None,
) -> NeighborTransferIndex:
    """Load neighbor bags + section→CRE maps (incl. ``oie.phrases`` aliases)."""
    from application.database.db import CRE, Links, Node

    bags: Dict[str, Set[str]] = {k: set() for k in _NEIGHBOR_NODE_PATTERNS}
    # family -> key -> (title, aliases, cres)
    section_acc: Dict[str, Dict[str, Tuple[str, List[str], List[str]]]] = {
        k: {} for k in _NEIGHBOR_NODE_PATTERNS
    }

    rows = (
        session.query(
            Node.name,
            Node.section_id,
            Node.section,
            Node.metadata_json,
            CRE.id,
        )
        .join(Links, Links.node == Node.id)
        .join(CRE, CRE.id == Links.cre)
        .all()
    )
    for name, section_id, section, meta, cre_id in rows:
        if not name or not cre_id:
            continue
        label = str(name)
        for family, patterns in _NEIGHBOR_NODE_PATTERNS.items():
            if not any(p.search(label) for p in patterns):
                continue
            bags[family].add(cre_id)
            raw_sid = str(section_id or "").strip()
            if not raw_sid:
                raw_sid = re.sub(r"[^A-Za-z0-9]+", "-", str(section or "x"))[:40]
            key = f"{label}|{raw_sid}"
            title = (section or raw_sid).strip()
            if not title or len(title) < 3:
                continue
            aliases = _oie_phrases(meta)[:30]
            slot = section_acc[family].setdefault(key, (title, [], []))
            alias_list = list(slot[1])
            for a in aliases:
                if a and a not in alias_list and a != title:
                    alias_list.append(a)
            cres = list(slot[2])
            if cre_id not in cres:
                cres.append(cre_id)
            section_acc[family][key] = (slot[0], alias_list, cres)

    sections: Dict[str, Tuple[NeighborSectionHit, ...]] = {}
    for family, by_key in section_acc.items():
        hits = [
            NeighborSectionHit(
                key=k,
                title=title,
                cre_ids=tuple(cres),
                aliases=tuple(aliases),
            )
            for k, (title, aliases, cres) in sorted(by_key.items())
            if cres
        ]
        if hits:
            sections[family] = tuple(hits)

    disk = cache_dir or Path(
        os.environ.get(
            "CRE_LIBRARIAN_NEIGHBOR_REMAP_CACHE",
            "tmp/oie_neighbor_remap_cache",
        )
    )
    return NeighborTransferIndex(
        bags={k: frozenset(v) for k, v in bags.items() if v},
        sections=sections,
        llm_fn=llm_fn,
        cache=NeighborRemapCache(disk_dir=disk),
    )


__all__ = [
    "NeighborTransferIndex",
    "NeighborSectionHit",
    "NeighborRemapCache",
    "build_neighbor_transfer_index",
    "build_cross_standard_remap_prompt",
    "detect_standard_family",
]
