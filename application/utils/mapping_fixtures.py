"""Load OWASP mapping JSON from ``application/tests/fixtures/owasp_mappings``.

These files are **eval / unit-test gold**, not a production catalog. Other
projects should link to OpenCRE so we can parse at the source; shipping
hand-maintained CRE mappings as importers would make OpenCRE another
spreadsheet. The exception is GSoC/OIE pipeline validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

OWASP_MAPPING_FIXTURE_DIR = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "owasp_mappings"
)

MappingEntry = Dict[str, Any]


def list_owasp_mapping_fixtures() -> List[str]:
    """Return sorted JSON filenames in the mapping fixture directory."""
    return sorted(path.name for path in OWASP_MAPPING_FIXTURE_DIR.glob("*.json"))


def load_owasp_mapping_fixture(name: str) -> List[MappingEntry]:
    """Load one mapping fixture by filename or stem.

    ``name`` may be ``owasp_aisvs_1_0`` or ``owasp_aisvs_1_0.json``.
    """
    filename = name if name.endswith(".json") else f"{name}.json"
    path = OWASP_MAPPING_FIXTURE_DIR / filename
    if not path.is_file():
        known = ", ".join(list_owasp_mapping_fixtures()) or "(none)"
        raise FileNotFoundError(
            f"Unknown OWASP mapping fixture {filename!r}. Known: {known}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Fixture {filename} must be a JSON list, got {type(payload)}")
    return payload


def load_all_owasp_mapping_fixtures() -> Dict[str, List[MappingEntry]]:
    """Load every ``*.json`` mapping fixture, keyed by filename."""
    return {
        filename: load_owasp_mapping_fixture(filename)
        for filename in list_owasp_mapping_fixtures()
    }


def load_mapping_entries(
    name: str, override_path: Path | None = None
) -> List[MappingEntry]:
    """Load mapping rows from the named fixture, or from ``override_path`` (tests)."""
    if override_path is not None:
        payload = json.loads(Path(override_path).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(
                f"{override_path} must be a JSON list, got {type(payload)}"
            )
        return payload
    return load_owasp_mapping_fixture(name)


def index_by_section_id(
    entries: Sequence[Mapping[str, Any]],
) -> Dict[str, Mapping[str, Any]]:
    return {
        entry["section_id"]: entry
        for entry in entries
        if isinstance(entry.get("section_id"), str)
    }


def cre_ids_in_cache(
    cache: Any,
    entry: Mapping[str, Any],
    fallback_by_section_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> List[str]:
    """CRE ids that exist in ``cache``, then ``fallback_section_ids`` if none match."""
    found: List[str] = []
    for cre_id in entry.get("cre_ids") or []:
        if isinstance(cre_id, str) and cache.get_CREs(external_id=cre_id):
            found.append(cre_id)
    if found:
        return found
    if not fallback_by_section_id:
        return []
    seen: set[str] = set()
    resolved: List[str] = []
    for section_id in entry.get("fallback_section_ids") or []:
        if not isinstance(section_id, str):
            continue
        fallback_entry = fallback_by_section_id.get(section_id)
        if not fallback_entry:
            continue
        for cre_id in fallback_entry.get("cre_ids") or []:
            if (
                isinstance(cre_id, str)
                and cre_id not in seen
                and cache.get_CREs(external_id=cre_id)
            ):
                seen.add(cre_id)
                resolved.append(cre_id)
    return resolved


def linked_standards_from_mapping(
    cache: Any,
    standard_name: str,
    entries: Sequence[Mapping[str, Any]],
    *,
    fallback_entries: Sequence[Mapping[str, Any]] | None = None,
) -> List[Any]:
    """Build ``Standard`` documents with LinkedTo CREs from fixture rows."""
    from application.defs import cre_defs as defs

    fallback_index = index_by_section_id(fallback_entries or [])
    documents: List[Any] = []
    for entry in entries:
        standard = defs.Standard(
            name=standard_name,
            sectionID=str(entry.get("section_id") or ""),
            section=str(entry.get("section") or ""),
            hyperlink=str(entry.get("hyperlink") or ""),
        )
        for cre_id in cre_ids_in_cache(cache, entry, fallback_index):
            cres = cache.get_CREs(external_id=cre_id)
            if not cres:
                continue
            standard.add_link(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=cres[0].shallow_copy(),
                )
            )
        documents.append(standard)
    return documents


def resolved_cre_ids(
    entry: Mapping[str, Any],
    by_section_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> List[str]:
    """Return ``cre_ids`` for an entry, optionally following ``fallback_section_ids``.

    Fallback is used when the entry's own ``cre_ids`` are empty. Callers that
    also need "CRE missing from cache" behavior should filter after lookup.
    """
    own = [cre_id for cre_id in entry.get("cre_ids") or [] if isinstance(cre_id, str)]
    if own:
        return own
    if not by_section_id:
        return []
    fallbacks: Sequence[Any] = entry.get("fallback_section_ids") or []
    resolved: List[str] = []
    seen: set[str] = set()
    for section_id in fallbacks:
        if not isinstance(section_id, str):
            continue
        fallback_entry = by_section_id.get(section_id)
        if not fallback_entry:
            continue
        for cre_id in fallback_entry.get("cre_ids") or []:
            if isinstance(cre_id, str) and cre_id not in seen:
                seen.add(cre_id)
                resolved.append(cre_id)
    return resolved
