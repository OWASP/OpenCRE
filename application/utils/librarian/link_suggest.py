"""``POST /rest/v1/link/suggest``: the Librarian's shortlist as a public API.

Given a CRE ``Standard`` document (the same JSON shape the importers and the
REST API already speak), return the CREs most likely to be its link targets,
ranked. This is C.1 of the Librarian exposed directly, so a standard author or
maintainer can ask "where does this section belong?" without running the OIE
pipeline, and without a second similarity stack growing beside the one that is
evaluated and gated in CI (#275, and the maintainer decision on #965: do not
build a parallel mapping path).

What this deliberately is not: the Librarian's *decision*. The pipeline's C.2
rerank and C.3 calibration run in a worker with a torch cross-encoder loaded;
the web process must not pay that (the same constraint the chat retrieval in
#1161 respects). The score returned here is the retriever's cosine similarity,
named as such, ranked, and suitable for a human to choose from. Automated
mapping with a confidence threshold is ``mapping_job`` territory (#965), which
calls the same retriever and then the rest of the chain.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import re
from typing import Any, Callable, Dict, List, Mapping, Optional

from application.defs import cre_defs as defs

#: The public CRE id shape ("287-251"); everything else is treated as a row id.
_PUBLIC_ID = re.compile(r"[0-9]{3}-[0-9]{3}")
#: What a top_k string may be: an optional sign and ASCII digits, nothing else.
_ASCII_INT = re.compile(r"[+-]?[0-9]+")

#: Hard ceiling on one request's shortlist. The retriever's own top_k is the
#: pipeline setting (20 by default); a caller may ask for fewer, never more.
MAX_TOP_K = 20
DEFAULT_TOP_K = 5

#: Fields of a Standard that carry text worth embedding, in the order they are
#: joined. ``name`` is excluded on purpose: "ASVS" adds nothing to a section's
#: meaning and would pull every ASVS section toward the same neighbourhood.
_TEXT_FIELDS = ("section", "subsection", "description")


class InvalidStandardError(ValueError):
    """The request body is not a Standard document this endpoint can embed."""


def standard_query_text(doc: Mapping[str, Any]) -> str:
    """Build the text C.1 embeds from a Standard document, or raise.

    Mirrors how the pipeline treats a section: the section heading, the
    subsection and the description are what carry the requirement; ids and
    hyperlinks are provenance. At least one text field must be non-empty.
    """
    if not isinstance(doc, Mapping):
        raise InvalidStandardError("body must be a JSON object")
    doctype = doc.get("doctype")
    if doctype != defs.Credoctypes.Standard.value:
        raise InvalidStandardError(
            f"doctype must be {defs.Credoctypes.Standard.value!r}, got {doctype!r}"
        )
    name = doc.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidStandardError("name is required")
    parts: List[str] = []
    for field in _TEXT_FIELDS:
        value = doc.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise InvalidStandardError(f"{field} must be a string")
        if value.strip():
            parts.append(value.strip())
    if not parts:
        raise InvalidStandardError(
            "at least one of section, subsection or description must be non-empty"
        )
    return ". ".join(parts)


def clamp_top_k(raw: Any) -> int:
    """Parse a caller's top_k; absent means the default, bad input raises."""
    if raw is None or raw == "":
        return DEFAULT_TOP_K
    # Whole numbers only. int() would quietly truncate 2.5 to 2 and read True
    # as 1; a limit the caller mistyped should be refused, not reinterpreted.
    if isinstance(raw, bool):
        raise InvalidStandardError("top_k must be an integer")
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, float) and raw.is_integer():
        value = int(raw)
    elif isinstance(raw, str):
        # Strict ASCII integer: isdigit() admits "\u00b2" and lstrip("-") admits
        # "--3", while int() itself admits "2_0". Only an optional sign and
        # ASCII digits are a top_k; everything else is a 400.
        if not _ASCII_INT.fullmatch(raw.strip()):
            raise InvalidStandardError("top_k must be an integer")
        value = int(raw.strip())
    else:
        raise InvalidStandardError("top_k must be an integer")
    if value < 1:
        raise InvalidStandardError("top_k must be at least 1")
    return min(value, MAX_TOP_K)


def _default_retriever(database: Any) -> Any:
    """C.1 exactly as the pipeline builds it, minus C.2 and C.3.

    A seam: tests and callers with their own retriever pass one in and this is
    never called. Lazy import keeps the web process free of ML imports until a
    request actually needs them.
    """
    from application.utils.librarian.factory import build_retriever_for

    retriever, _ = build_retriever_for(database)
    return retriever


def _resolve_cre(database: Any, candidate_id: str) -> Optional[defs.CRE]:
    """Find the graph's CRE for a retriever candidate id, whichever space it is in.

    The embeddings table keys CRE vectors by the CRE row's *internal* id, so
    both retriever backends hand back UUIDs, while everything a human or an
    importer sees is the external id ("287-251"). The eval harness translates
    the pool for exactly this reason; here the translation happens per result,
    so the endpoint is correct against a pool keyed either way.
    """
    # One lookup, chosen by the id's shape: public ids are "ddd-ddd" (the
    # pattern cre_defs.CRE enforces), anything else is a row id. A single miss
    # then logs once, instead of twice per stale candidate on every request.
    kwargs = (
        {"external_id": candidate_id}
        if _PUBLIC_ID.fullmatch(candidate_id or "")
        else {"internal_id": candidate_id}
    )
    try:
        matches = database.get_CREs(**kwargs) or []
    except Exception:
        # A malformed id must not take the whole shortlist down, but a lookup
        # that raises is not the same as a lookup that misses: say which
        # candidate failed so a broken database path does not read as "stale".
        logger.warning(
            "link_suggest: CRE lookup failed for candidate %r; "
            "returning it unresolved",
            candidate_id,
            exc_info=True,
        )
        return None
    if not matches:
        return None
    found: defs.CRE = matches[0]
    return found


def suggest_links(
    database: Any,
    doc: Mapping[str, Any],
    *,
    top_k: int = DEFAULT_TOP_K,
    retriever: Optional[Any] = None,
    retriever_factory: Optional[Callable[[Any], Any]] = None,
) -> List[Dict[str, Any]]:
    """Rank the CREs most likely to link to ``doc``.

    Returns the response shape #275 asked for, one entry per candidate, best
    first: ``{"doctype": "CRE", "id", "name", "tags", "score"}``. ``score`` is
    the retriever's cosine similarity in [0, 1]. ``name`` and ``tags`` come from
    the graph when the CRE is present; a candidate the retriever knows but the
    graph does not (a stale embedding) is still returned, with the retriever's
    name and no tags, rather than silently dropped.
    """
    text = standard_query_text(doc)
    if top_k < 1 or top_k > MAX_TOP_K:
        raise InvalidStandardError(f"top_k must be between 1 and {MAX_TOP_K}")
    if retriever is None:
        # Resolved at call time, not bound as a default, so the module-level
        # builder stays the single seam tests and callers can replace.
        factory = retriever_factory or _default_retriever
        retriever = factory(database)
    audit = retriever.retrieve(text)

    results: List[Dict[str, Any]] = []
    for cand in audit.candidates[:top_k]:
        cre = _resolve_cre(database, cand.cre_id)
        name = (
            (cre.name if cre is not None and cre.name else None) or cand.cre_name or ""
        )
        tags: List[str] = (
            sorted(t for t in (cre.tags or []) if t) if cre is not None else []
        )
        results.append(
            {
                "doctype": defs.Credoctypes.CRE.value,
                # Always the public id ("287-251"), whatever the pool was keyed by.
                "id": cre.id if cre is not None and cre.id else cand.cre_id,
                "name": name,
                "tags": tags,
                "score": (
                    round(cand.score_vector, 4)
                    if cand.score_vector is not None
                    else None
                ),
            }
        )
    return results


__all__ = [
    "DEFAULT_TOP_K",
    "MAX_TOP_K",
    "InvalidStandardError",
    "clamp_top_k",
    "standard_query_text",
    "suggest_links",
]
