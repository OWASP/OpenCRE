"""Edition remap: LLM (or heuristic) section-id map between two versions of one standard.

Used when Module C has **low results** on a new edition *and* an older edition of
the same standard already has Links in the hub. We ask the model once (cached)
to map new section ids → old section ids, then inherit those CRE links.

No hand-maintained remap tables — only prompt + id validation + cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
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

logger = logging.getLogger(__name__)

# family key → regexes that identify Node.name / Standard: line as that family.
_FAMILY_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    (
        "owasp_top10",
        re.compile(r"owasp\s*top\s*10(?!.*\b(llm|api|k8s|kubernetes)\b)", re.I),
    ),
    ("owasp_api_top10", re.compile(r"api\s*(security\s*)?top\s*10|owasp\s*api", re.I)),
    ("owasp_llm_top10", re.compile(r"(llm|genai).*top\s*10|top10\s*for\s*llm", re.I)),
    ("owasp_aisvs", re.compile(r"\baisvs\b", re.I)),
    ("owasp_k8s_top10", re.compile(r"kubernetes|k8s", re.I)),
)

_YEAR = re.compile(r"(20\d{2})")
_STANDARD_LINE = re.compile(r"(?im)^Standard:\s*(.+)$")
_VERSION_LINE = re.compile(r"(?im)^Version:\s*(.+)$")
_SECTION_ID_LINE = re.compile(r"(?im)^Section-ID:\s*(.+)$")
_SECTION_LINE = re.compile(r"(?im)^Section:\s*(.+)$")
_SOURCE_LINE = re.compile(r"(?im)^Source:\s*(.+)$")
_ID_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(A\d{2}|API\d{1,2}|LLM\d{2}|K\d{2}|AISVS\d{1,2})(?![A-Za-z0-9])",
    re.I,
)

# Low-results gate: fewer than this many caged candidates → try edition reseed.
LOW_RESULT_CANDIDATE_MAX = 2

LlmFn = Callable[[str, str], str]  # (system, user) -> raw JSON text


@dataclass(frozen=True)
class EditionSection:
    section_id: str
    title: str


@dataclass(frozen=True)
class StandardEdition:
    family: str
    year: int
    label: str  # original Node.name or Standard: value
    sections: Tuple[EditionSection, ...]


def family_and_year(label: str) -> Optional[Tuple[str, int]]:
    """Return ``(family_key, year)`` when ``label`` looks like a known OWASP family."""
    text = (label or "").strip()
    if not text:
        return None
    year_m = _YEAR.search(text)
    if not year_m:
        return None
    year = int(year_m.group(1))
    for family, pattern in _FAMILY_PATTERNS:
        if pattern.search(text):
            return family, year
    return None


def parse_chunk_standard(text: str) -> Optional[Tuple[str, int, str]]:
    """From chunk prefixes: ``(family, year, section_id)`` or None.

    Prefers ``Version:`` for the year when present; otherwise parses year from
    the ``Standard:`` label (e.g. ``owasp_top10_2025``).
    """
    std_m = _STANDARD_LINE.search(text or "")
    if not std_m:
        return None
    label = std_m.group(1).strip()
    ver_m = _VERSION_LINE.search(text or "")
    version = ver_m.group(1).strip() if ver_m else ""
    # Combine so family patterns + year both resolve.
    combined = f"{label} {version}".strip()
    fy = family_and_year(combined)
    if not fy:
        fy = family_and_year(label.replace("_", " ").replace(".json", ""))
    if not fy and version:
        # Family from Standard alone; year from Version.
        fam_only = None
        for family, pattern in _FAMILY_PATTERNS:
            if pattern.search(label.replace("_", " ")):
                fam_only = family
                break
        year_m = _YEAR.search(version) or _YEAR.search(label)
        if fam_only and year_m:
            fy = (fam_only, int(year_m.group(1)))
    if not fy:
        return None
    family, year = fy
    section_id = ""
    src = _SOURCE_LINE.search(text or "")
    if src:
        toks = _ID_TOKEN.findall(src.group(1))
        if toks:
            section_id = toks[0].upper()
    if not section_id:
        sid_line = _SECTION_ID_LINE.search(text or "")
        if sid_line:
            toks = _ID_TOKEN.findall(sid_line.group(1))
            if toks:
                section_id = toks[0].upper()
    if not section_id:
        return None
    return family, year, section_id


def heuristic_remap(
    new_sections: Sequence[EditionSection],
    old_sections: Sequence[EditionSection],
) -> Dict[str, List[str]]:
    """Title-token overlap fallback when the LLM is unavailable.

    Prefers topic match over same section-id (numbering often reshuffles).
    """
    old_by_id = {s.section_id.upper(): s for s in old_sections}

    def tokens(title: str) -> Set[str]:
        stop = {
            "the",
            "and",
            "for",
            "with",
            "owasp",
            "top",
            "broken",
            "failures",
            "failure",
            "security",
        }
        words = [
            t
            for t in re.findall(r"[a-z0-9]{3,}", (title or "").lower())
            if t not in stop
        ]
        stems: Set[str] = set()
        for w in words:
            stems.add(w)
            for suf in ("ic", "ies", "es", "s", "ing", "tion", "ment"):
                if len(w) > len(suf) + 4 and w.endswith(suf):
                    stems.add(w[: -len(suf)])
        return stems

    scored: List[Tuple[float, str, str]] = []
    for ns in new_sections:
        nt = tokens(ns.title)
        for oid, os_ in old_by_id.items():
            ot = tokens(os_.title)
            if not nt or not ot:
                continue
            inter = set(nt & ot)
            # Substring boost: configuration ⊂ misconfiguration
            for a in nt:
                for b in ot:
                    if len(a) >= 5 and len(b) >= 5 and (a in b or b in a):
                        inter.add(a)
            score = len(inter) / len(nt | ot)
            if ns.section_id.upper() == oid and score > 0:
                score += 0.05
            scored.append((score, ns.section_id.upper(), oid))
    scored.sort(reverse=True)

    out: Dict[str, List[str]] = {s.section_id.upper(): [] for s in new_sections}
    used_old: Set[str] = set()
    used_new: Set[str] = set()
    for score, nid, oid in scored:
        if score < 0.15:
            break
        if nid in used_new or oid in used_old:
            continue
        out[nid] = [oid]
        used_new.add(nid)
        used_old.add(oid)
    return out


def validate_remap(
    remap: Mapping[str, Sequence[str]],
    *,
    new_ids: Set[str],
    old_ids: Set[str],
) -> Dict[str, List[str]]:
    """Drop unknown ids; keep only maps whose keys are new and values are old."""
    clean: Dict[str, List[str]] = {}
    new_u = {i.upper() for i in new_ids}
    old_u = {i.upper() for i in old_ids}
    for key, vals in (remap or {}).items():
        k = str(key).upper().strip()
        if k not in new_u:
            continue
        kept = []
        for v in vals or []:
            vv = str(v).upper().strip()
            if vv in old_u and vv not in kept:
                kept.append(vv)
        clean[k] = kept
    for nid in new_u:
        clean.setdefault(nid, [])
    return clean


def parse_llm_remap_json(raw: str) -> Dict[str, List[str]]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("remap JSON must be an object")
    # Allow {"remap": {...}} wrapper
    if "remap" in data and isinstance(data["remap"], dict):
        data = data["remap"]
    out: Dict[str, List[str]] = {}
    for k, v in data.items():
        if isinstance(v, str):
            out[str(k)] = [v]
        elif isinstance(v, list):
            out[str(k)] = [str(x) for x in v]
        else:
            continue
    return out


def build_remap_prompt(
    *,
    family: str,
    new_year: int,
    old_year: int,
    new_sections: Sequence[EditionSection],
    old_sections: Sequence[EditionSection],
) -> Tuple[str, str]:
    system = (
        "You map section IDs between two editions of the SAME security standard. "
        "Return ONLY JSON: an object whose keys are NEW section ids and values are "
        "arrays of OLD section ids (usually one). Prefer topic/title match when "
        "numbering changed. Never invent ids not in the lists. Empty array if none."
    )
    payload = {
        "family": family,
        "new_year": new_year,
        "old_year": old_year,
        "new_sections": [{"id": s.section_id, "title": s.title} for s in new_sections],
        "old_sections": [{"id": s.section_id, "title": s.title} for s in old_sections],
    }
    user = (
        "Build the remap from new → old section ids.\n"
        + json.dumps(payload, indent=2)
        + '\n\nRespond like: {"A04": ["A02"], "A02": ["A05"]}'
    )
    return system, user


def propose_remap(
    *,
    family: str,
    new_year: int,
    old_year: int,
    new_sections: Sequence[EditionSection],
    old_sections: Sequence[EditionSection],
    llm_fn: Optional[LlmFn] = None,
) -> Dict[str, List[str]]:
    """LLM remap with heuristic fallback; always validated against known ids."""
    new_ids = {s.section_id.upper() for s in new_sections}
    old_ids = {s.section_id.upper() for s in old_sections}
    raw_map: Dict[str, List[str]] = {}
    if llm_fn is not None:
        try:
            system, user = build_remap_prompt(
                family=family,
                new_year=new_year,
                old_year=old_year,
                new_sections=new_sections,
                old_sections=old_sections,
            )
            raw_map = parse_llm_remap_json(llm_fn(system, user))
        except Exception:  # noqa: BLE001
            logger.warning("edition remap LLM failed; using heuristic", exc_info=True)
            raw_map = {}
    if not raw_map:
        raw_map = heuristic_remap(new_sections, old_sections)
    return validate_remap(raw_map, new_ids=new_ids, old_ids=old_ids)


def default_litellm_fn(model: Optional[str] = None) -> LlmFn:
    """LiteLLM completion → text (defaults to Gemini 2.5 Pro for remap quality)."""
    from application.prompt_client.litellm_router import system_user_fn

    model_name = model or os.environ.get(
        "CRE_LIBRARIAN_EDITION_REMAP_MODEL",
        os.environ.get(
            "CRE_LIBRARIAN_METADATA_MODEL",
            "gemini/gemini-2.5-pro",
        ),
    )
    return system_user_fn(
        model_name,
        temperature=0.0,
        extra_try_kwargs={"reasoning_effort": "minimal"},
    )


@dataclass
class EditionRemapCache:
    """Process-local + optional disk cache for remaps."""

    memory: Dict[str, Dict[str, List[str]]]
    disk_dir: Optional[Path] = None

    def _key(self, family: str, new_year: int, old_year: int, fingerprint: str) -> str:
        return f"{family}:{old_year}->{new_year}:{fingerprint}"

    @staticmethod
    def fingerprint(
        new_sections: Sequence[EditionSection], old_sections: Sequence[EditionSection]
    ) -> str:
        blob = json.dumps(
            {
                "n": [(s.section_id, s.title) for s in new_sections],
                "o": [(s.section_id, s.title) for s in old_sections],
            },
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def get(self, key: str) -> Optional[Dict[str, List[str]]]:
        if key in self.memory:
            return self.memory[key]
        if self.disk_dir is not None:
            path = self.disk_dir / f"{key.replace(':', '_').replace('>', '-')}.json"
            if path.is_file():
                data = json.loads(path.read_text())
                self.memory[key] = data
                return data
        return None

    def put(self, key: str, remap: Dict[str, List[str]]) -> None:
        self.memory[key] = remap
        if self.disk_dir is not None:
            self.disk_dir.mkdir(parents=True, exist_ok=True)
            path = self.disk_dir / f"{key.replace(':', '_').replace('>', '-')}.json"
            path.write_text(json.dumps(remap, indent=2, sort_keys=True))


class EditionTransferService:
    """Look up predecessor edition Links and expand a CRE allowlist via remap."""

    def __init__(
        self,
        *,
        editions: Sequence[StandardEdition],
        section_cre_ids: Mapping[Tuple[str, int, str], Set[str]],
        llm_fn: Optional[LlmFn] = None,
        cache: Optional[EditionRemapCache] = None,
        low_result_max: int = LOW_RESULT_CANDIDATE_MAX,
    ) -> None:
        self._editions = list(editions)
        self._section_cre_ids = dict(section_cre_ids)
        self._llm_fn = llm_fn
        self._cache = cache or EditionRemapCache(memory={})
        self.low_result_max = low_result_max

    def predecessor(self, family: str, year: int) -> Optional[StandardEdition]:
        older = [e for e in self._editions if e.family == family and e.year < year]
        if not older:
            return None
        # Prefer editions that actually have CRE Links (skip empty synthetics).
        with_links = [
            e
            for e in older
            if any(
                fam == family and y == e.year
                for (fam, y, _sid) in self._section_cre_ids
            )
        ]
        pool = with_links or older
        return max(pool, key=lambda e: e.year)

    def edition(self, family: str, year: int) -> Optional[StandardEdition]:
        for e in self._editions:
            if e.family == family and e.year == year:
                return e
        return None

    def remap_for(
        self, family: str, new_year: int, old_year: int
    ) -> Dict[str, List[str]]:
        new_ed = self.edition(family, new_year)
        old_ed = self.edition(family, old_year)
        if not new_ed or not old_ed:
            return {}
        fp = EditionRemapCache.fingerprint(new_ed.sections, old_ed.sections)
        key = self._cache._key(family, new_year, old_year, fp)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        remap = propose_remap(
            family=family,
            new_year=new_year,
            old_year=old_year,
            new_sections=new_ed.sections,
            old_sections=old_ed.sections,
            llm_fn=self._llm_fn,
        )
        self._cache.put(key, remap)
        return remap

    def cre_ids_for_new_section(
        self, family: str, new_year: int, section_id: str
    ) -> Set[str]:
        """CRE hub ids inherited from the predecessor via remap."""
        pred = self.predecessor(family, new_year)
        if pred is None:
            return set()
        remap = self.remap_for(family, new_year, pred.year)
        old_ids = remap.get(section_id.upper(), [])
        out: Set[str] = set()
        for oid in old_ids:
            out |= set(
                self._section_cre_ids.get((family, pred.year, oid.upper()), set())
            )
        return out

    def expand_allowlist_if_low(
        self,
        text: str,
        allowlist: FrozenSet[str],
        candidate_count: int,
    ) -> FrozenSet[str]:
        """If results are low and a predecessor exists, union remapped CRE ids."""
        if candidate_count > self.low_result_max:
            return allowlist
        parsed = parse_chunk_standard(text)
        if not parsed:
            return allowlist
        family, year, section_id = parsed
        if self.predecessor(family, year) is None:
            return allowlist
        extra = self.cre_ids_for_new_section(family, year, section_id)
        if not extra:
            return allowlist
        return frozenset(set(allowlist) | extra)


def build_edition_transfer_from_db(
    session: Any,
    *,
    llm_fn: Optional[LlmFn] = None,
    cache_dir: Optional[Path] = None,
) -> EditionTransferService:
    """Load Node+Links catalogs grouped by standard family/year."""
    from application.database.db import CRE, Links, Node

    # (family, year, label) -> sections; (family, year, section_id) -> cre keys
    section_titles: Dict[Tuple[str, int], Dict[str, str]] = {}
    labels: Dict[Tuple[str, int], str] = {}
    section_cres: Dict[Tuple[str, int, str], Set[str]] = {}

    rows = (
        session.query(Node.name, Node.section_id, Node.section, CRE.id, CRE.external_id)
        .join(Links, Links.node == Node.id)
        .join(CRE, CRE.id == Links.cre)
        .all()
    )
    for name, section_id, section, cre_id, ext in rows:
        fy = family_and_year(name or "")
        if not fy or not section_id:
            continue
        family, year = fy
        sid = str(section_id).upper().strip()
        # LLM nodes sometimes store LLM01:2025
        sid = sid.split(":")[0]
        if not re.match(
            r"^(A\d{2}|API\d{1,2}|LLM\d{2}|K\d{2}|AISVS\d{1,2})$", sid, re.I
        ):
            continue
        labels[(family, year)] = name
        section_titles.setdefault((family, year), {})
        title = (section or sid).strip()
        section_titles[(family, year)].setdefault(sid, title)
        slot = section_cres.setdefault((family, year, sid), set())
        if cre_id:
            slot.add(cre_id)
        # Do not seed external_id — embeddings / CE texts are UUID-keyed.

    # Also merge section catalogs from Nodes that have no CRE Links yet
    # (brand-new editions). Titles come from Node.section / oie.section_title —
    # never from Python dicts.
    bare_nodes = session.query(
        Node.name, Node.section_id, Node.section, Node.metadata_json
    ).all()
    for name, section_id, section, meta in bare_nodes:
        fy = family_and_year(name or "")
        if not fy or not section_id:
            continue
        family, year = fy
        sid = str(section_id).upper().strip().split(":")[0]
        if not re.match(
            r"^(A\d{2}|API\d{1,2}|LLM\d{2}|K\d{2}|AISVS\d{1,2})$", sid, re.I
        ):
            continue
        title = (section or "").strip()
        if isinstance(meta, dict):
            oie = meta.get("oie") or {}
            if isinstance(oie, dict) and oie.get("section_title"):
                title = str(oie["section_title"]).strip() or title
        if not title:
            title = sid
        labels.setdefault((family, year), name)
        section_titles.setdefault((family, year), {})
        section_titles[(family, year)].setdefault(sid, title)

    editions: List[StandardEdition] = []
    for (family, year), titles in section_titles.items():
        sections = tuple(
            EditionSection(section_id=sid, title=title)
            for sid, title in sorted(titles.items())
        )
        editions.append(
            StandardEdition(
                family=family,
                year=year,
                label=labels.get((family, year), f"{family} {year}"),
                sections=sections,
            )
        )

    cache = EditionRemapCache(
        memory={},
        disk_dir=cache_dir
        or Path(
            os.environ.get(
                "CRE_LIBRARIAN_EDITION_REMAP_CACHE",
                "tmp/oie_edition_remap_cache",
            )
        ),
    )
    return EditionTransferService(
        editions=editions,
        section_cre_ids=section_cres,
        llm_fn=llm_fn,
        cache=cache,
    )


__all__ = [
    "EditionRemapCache",
    "EditionSection",
    "EditionTransferService",
    "LOW_RESULT_CANDIDATE_MAX",
    "StandardEdition",
    "build_edition_transfer_from_db",
    "default_litellm_fn",
    "family_and_year",
    "heuristic_remap",
    "parse_chunk_standard",
    "propose_remap",
    "validate_remap",
]
