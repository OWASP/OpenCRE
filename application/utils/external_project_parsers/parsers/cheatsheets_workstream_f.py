"""Cheat Sheet -> CRE mapping, Workstream F: review-artifacts + import adapter.

This module is the *decoupled tail* of the mapping pipeline. Upstream workstreams
(A-E) produce mapping candidates; this workstream owns the durable review
artifacts (``suggestions.json`` -> reviewer edits -> ``approved.json``) and,
in a later checkpoint, the conversion of approved suggestions into the import
pipeline's ``ParseResult``.

Checkpoints implemented here (F1 + F2 + F3 + F4):

* F1 -- the data contract: :data:`SUGGESTIONS_SCHEMA` (JSON Schema) plus the
  :class:`CandidateCRE` / :class:`MappingSuggestion` dataclasses.
* F2 -- the read/write adapters: :func:`write_suggestions_json` and
  :func:`load_approved_suggestions` (schema-validate -> parse -> filter to the
  reviewer-approved entries).
* F3 -- the import adapter: :func:`suggestions_to_parse_result`, which reconciles
  the review artifact with the *real* import types (real code wins):
    - fixed ``defs.Standard(name="OWASP Cheat Sheets")``; the suggestion ``title``
      maps to ``Standard.section`` (matching the existing cheatsheets_parser);
    - the import pipeline REQUIRES ``family:/subtype:/audience:/maturity:/source:``
      classification tags (``base_parser_defs.validate_classification_tags``
      raises otherwise) -- built via ``build_tags`` -- even though the RFC's
      §4 contract omits them; ``category`` rides along as an extra tag when set;
    - candidate CREs are resolved via ``cache.get_CREs(external_id=...)`` and
      unknown ids are skipped (collected + logged); a Standard with zero resolved
      links is dropped;
    - the advisory review fields (see the schema) have no home on
      ``defs.Standard`` and are intentionally not persisted.
* F4 -- the ``validate`` / ``generate`` / ``convert`` CLI (:func:`main`,
  :func:`build_arg_parser`) over the F1-F3 functions. ``convert`` resolves CREs
  through a live ``Node_collection`` obtained via :func:`_open_cache` and stops
  at printing the resulting ``ParseResult`` summary (including skipped unknown
  CRE ids).

Deliberately NOT in this module yet:

* F5 -- wiring ``convert``'s ``ParseResult`` into the live import/register flow
  (the real import path + DB registration). ``convert`` deliberately does not
  register anything into the graph in F4.

The advisory fields ``score``, ``confidence``, ``reason`` (per candidate) and
``cheatsheet_id`` / ``category`` (per item) exist so a human reviewer can triage
suggestions; they are carried through the round-trip but, per the approved
reconciliation, are NOT persisted onto ``defs.Standard`` in F3.

``jsonschema`` is a dev/tooling dependency (requirements-dev.txt). This module is
offline import tooling, not part of the live web app, so that is intentional; if
F ever runs in a production import path, promote ``jsonschema`` to
requirements.txt.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import jsonschema

from application.defs import cre_defs as defs
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.base_parser_defs import ParseResult

if TYPE_CHECKING:
    from application.database import db

logger = logging.getLogger(__name__)

# --- valid values -----------------------------------------------------------

#: Reviewer lifecycle for a suggestion. Only ``approved`` items are converted.
SUGGESTION_STATUSES = ("suggested", "approved", "rejected")

#: Advisory confidence buckets attached to a candidate by the upstream mapper.
CONFIDENCE_LEVELS = ("high", "medium", "low")


class SuggestionSchemaError(ValueError):
    """Raised when a suggestions document violates :data:`SUGGESTIONS_SCHEMA`.

    The message names the offending field (its JSON path) so a reviewer can find
    and fix it in the artifact.
    """


# --- F1: the JSON Schema for the suggestions document -----------------------

#: JSON Schema for one §4 suggestion item.
SUGGESTION_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "source",
        "cheatsheet_id",
        "title",
        "hyperlink",
        "category",
        "status",
        "candidate_cres",
    ],
    "properties": {
        "source": {"type": "string", "minLength": 1},
        "cheatsheet_id": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "hyperlink": {"type": "string", "minLength": 1},
        "category": {"type": "string"},
        "status": {"type": "string", "enum": list(SUGGESTION_STATUSES)},
        "candidate_cres": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["cre_id", "score", "confidence", "reason"],
                "properties": {
                    "cre_id": {"type": "string", "minLength": 1},
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                    "confidence": {
                        "type": "string",
                        "enum": list(CONFIDENCE_LEVELS),
                    },
                    "reason": {"type": "string"},
                },
            },
        },
    },
}

#: JSON Schema for the whole suggestions.json document: an array of items.
SUGGESTIONS_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "OWASP Cheat Sheet -> CRE mapping suggestions",
    "type": "array",
    "items": SUGGESTION_ITEM_SCHEMA,
}


# --- F1: the dataclasses ----------------------------------------------------


@dataclass
class CandidateCRE:
    """A single candidate CRE for a cheat sheet, with advisory review metadata.

    ``score``, ``confidence`` and ``reason`` are advisory: they help a human
    reviewer triage the candidate and are NOT persisted onto ``defs.Standard``
    when approved suggestions are converted in F3.
    """

    cre_id: str
    score: float
    confidence: str
    reason: str


@dataclass
class MappingSuggestion:
    """One reviewable cheat-sheet -> CRE(s) mapping suggestion (§4 item).

    ``cheatsheet_id`` and ``category`` are advisory review metadata with no home
    on ``defs.Standard``; ``title`` maps to ``Standard.section`` in F3.
    """

    source: str
    cheatsheet_id: str
    title: str
    hyperlink: str
    category: str
    candidate_cres: List[CandidateCRE] = field(default_factory=list)
    status: str = "suggested"


# --- F2: read / write adapters ----------------------------------------------


def _to_jsonable(suggestions: List[MappingSuggestion]) -> List[Dict[str, Any]]:
    """Convert dataclasses to plain dicts in the schema's field order."""
    return [dataclasses.asdict(s) for s in suggestions]


def write_suggestions_json(path: str, suggestions: List[MappingSuggestion]) -> None:
    """Write ``suggestions`` to ``path`` as a schema-valid JSON document.

    Output is deterministic (sorted keys, stable indent, trailing newline) so it
    round-trips and diffs cleanly under review.
    """
    doc = _to_jsonable(suggestions)
    # Validate what we emit so we can never write an artifact the loader rejects.
    _validate(doc)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def _validate(doc: Any) -> None:
    """Validate ``doc`` against :data:`SUGGESTIONS_SCHEMA`.

    Re-raises as :class:`SuggestionSchemaError` with the offending field named.
    """
    try:
        jsonschema.validate(instance=doc, schema=SUGGESTIONS_SCHEMA)
    except jsonschema.ValidationError as exc:
        field_path = _field_path(exc)
        raise SuggestionSchemaError(
            f"invalid suggestions document at {field_path}: {exc.message}"
        ) from exc


def _field_path(exc: jsonschema.ValidationError) -> str:
    """Render a human-readable field path for a validation error.

    For a missing ``required`` property jsonschema does not put the property in
    ``absolute_path``, so pull the field name out of the validator value.
    """
    parts = [str(p) for p in exc.absolute_path]
    if exc.validator == "required" and isinstance(exc.validator_value, list):
        missing = [f for f in exc.validator_value if f not in exc.instance]
        parts.extend(missing)
    return "/".join(parts) if parts else "<root>"


def _parse_suggestion(raw: Dict[str, Any]) -> MappingSuggestion:
    return MappingSuggestion(
        source=raw["source"],
        cheatsheet_id=raw["cheatsheet_id"],
        title=raw["title"],
        hyperlink=raw["hyperlink"],
        category=raw["category"],
        status=raw["status"],
        candidate_cres=[
            CandidateCRE(
                cre_id=c["cre_id"],
                score=c["score"],
                confidence=c["confidence"],
                reason=c["reason"],
            )
            for c in raw["candidate_cres"]
        ],
    )


def load_approved_suggestions(path: str) -> List[MappingSuggestion]:
    """Load ``path``, schema-validate it, and return only approved suggestions.

    Raises :class:`SuggestionSchemaError` (naming the bad field) if the document
    violates :data:`SUGGESTIONS_SCHEMA`.
    """
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    _validate(doc)
    return [_parse_suggestion(raw) for raw in doc if raw["status"] == "approved"]


# --- F3: import adapter -----------------------------------------------------

#: Fixed Standard name for every imported cheat sheet, matching the live
#: ``cheatsheets_parser`` so entries dedupe/merge against the same resource.
STANDARD_NAME = "OWASP Cheat Sheets"


def suggestions_to_parse_result(
    approved: List[MappingSuggestion],
    cache: "db.Node_collection",
) -> ParseResult:
    """Convert approved suggestions into a ``ParseResult`` the import flow accepts.

    Per approved suggestion, builds a ``defs.Standard`` (fixed name
    ``"OWASP Cheat Sheets"``; ``title`` -> ``section``; ``hyperlink``; the
    required classification tags via ``build_tags`` with ``category`` as an extra
    tag when non-empty). Each candidate ``cre_id`` is resolved via
    ``cache.get_CREs(external_id=...)``; unknown ids are collected, logged, and
    skipped. Resolved CREs are attached as ``AutomaticallyLinkedTo`` links (on a
    ``shallow_copy`` so the CRE's own links don't leak in, and guarded by
    ``has_link`` so a repeated id can't raise ``DuplicateLinkException``). A
    Standard with zero resolved links is dropped.

    The advisory review fields (``score`` / ``confidence`` / ``reason`` /
    ``cheatsheet_id``) have no home on ``defs.Standard`` and are not persisted.
    """
    standards: List[defs.Document] = []
    unknown_cre_ids: List[str] = []

    for suggestion in approved:
        category = suggestion.category.strip()
        extra = [category] if category else []
        standard = defs.Standard(
            name=STANDARD_NAME,
            section=suggestion.title,
            hyperlink=suggestion.hyperlink,
            tags=base_parser_defs.build_tags(
                family=base_parser_defs.Family.GUIDANCE,
                subtype=base_parser_defs.Subtype.CHEATSHEET,
                audience=base_parser_defs.Audience.DEVELOPER,
                maturity=base_parser_defs.Maturity.STABLE,
                source="owasp_cheatsheets",
                extra=extra,
            ),
        )

        for candidate in suggestion.candidate_cres:
            cres = cache.get_CREs(external_id=candidate.cre_id)
            if not cres:
                unknown_cre_ids.append(candidate.cre_id)
                logger.warning(
                    "Skipping unknown CRE id %s for cheat sheet %r; not in cache.",
                    candidate.cre_id,
                    suggestion.title,
                )
                continue
            for cre in cres:
                link = defs.Link(
                    document=cre.shallow_copy(),
                    ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                )
                # Guard against a repeated cre_id (add_link would otherwise raise
                # DuplicateLinkException on the second occurrence).
                if not standard.has_link(link):
                    standard.add_link(link)

        if standard.links:
            standards.append(standard)
        else:
            logger.info(
                "Dropping cheat sheet %r: no candidate CREs resolved.",
                suggestion.title,
            )

    if unknown_cre_ids:
        logger.warning(
            "suggestions_to_parse_result skipped %d unknown CRE id(s): %s",
            len(unknown_cre_ids),
            ", ".join(unknown_cre_ids),
        )

    return ParseResult(results={STANDARD_NAME: standards})


# --- F4: command-line interface ---------------------------------------------

# Exit codes, mirroring scripts/build_golden_dataset.py's convention.
_EXIT_OK = 0
_EXIT_ERROR = 1  # schema / logic error
_EXIT_USAGE = 2  # missing file / bad invocation


def _open_cache(db_uri: Optional[str] = None) -> "db.Node_collection":
    """Instantiate a live ``Node_collection`` for the ``convert`` subcommand.

    Delegates to ``cre_main.db_connect`` (``create_app`` + ``app_context().push()``)
    so the DB session has the Flask app context its queries need; a bare
    ``db.Node_collection()`` would construct but fail on the first query. Tests
    patch this seam with the F3 ``_StubCache`` stub, so no Postgres/Neo4j is
    required.
    """
    from application.cmd.cre_main import db_connect

    return db_connect(db_uri or "")


def _load_json_doc(path: str) -> Any:
    """Read+parse a JSON document, raising FileNotFoundError/JSONDecodeError."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _cmd_validate(args: argparse.Namespace) -> int:
    """Schema-validate a suggestions document; print OK or the offending field."""
    try:
        doc = _load_json_doc(args.suggestions)
    except FileNotFoundError:
        print(f"file not found: {args.suggestions}", file=sys.stderr)
        return _EXIT_USAGE
    except json.JSONDecodeError as exc:
        print(f"invalid JSON in {args.suggestions}: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    try:
        _validate(doc)
    except SuggestionSchemaError as exc:
        print(str(exc), file=sys.stderr)
        return _EXIT_ERROR

    count = len(doc) if isinstance(doc, list) else 0
    print(f"OK: {args.suggestions} is a valid suggestions document ({count} items)")
    return _EXIT_OK


def _cmd_generate(args: argparse.Namespace) -> int:
    """Validate + normalize an input suggestions document into a canonical file.

    Without workstreams A-E to synthesise candidates, this simply validates and
    re-writes the input in canonical form (schema check, sorted keys, stable
    indent, trailing newline).
    """
    try:
        doc = _load_json_doc(args.infile)
    except FileNotFoundError:
        print(f"file not found: {args.infile}", file=sys.stderr)
        return _EXIT_USAGE
    except json.JSONDecodeError as exc:
        print(f"invalid JSON in {args.infile}: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    try:
        _validate(doc)
        suggestions = [_parse_suggestion(raw) for raw in doc]
        write_suggestions_json(args.outfile, suggestions)
    except SuggestionSchemaError as exc:
        print(str(exc), file=sys.stderr)
        return _EXIT_ERROR
    except OSError as exc:
        print(f"cannot write {args.outfile}: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    print(f"wrote {len(suggestions)} suggestions to {args.outfile}")
    return _EXIT_OK


def _cmd_convert(args: argparse.Namespace) -> int:
    """Convert approved suggestions to a ParseResult and print a summary.

    NOTE: this stops at the in-memory ``ParseResult`` summary. Wiring it into the
    live import/register flow (DB registration) is F5, a separate PR.
    """
    try:
        approved = load_approved_suggestions(args.approved)
    except FileNotFoundError:
        print(f"file not found: {args.approved}", file=sys.stderr)
        return _EXIT_USAGE
    except json.JSONDecodeError as exc:
        print(f"invalid JSON in {args.approved}: {exc}", file=sys.stderr)
        return _EXIT_USAGE
    except SuggestionSchemaError as exc:
        print(str(exc), file=sys.stderr)
        return _EXIT_ERROR

    cache = _open_cache(args.db)
    result = suggestions_to_parse_result(approved, cache)
    standards = result.results.get(STANDARD_NAME, []) if result.results else []

    # F3 logs skipped unknown ids but does not return them; re-derive from the
    # result: any approved candidate id that resolved to no link was skipped.
    # ``link.document`` is typed as the base ``Document`` (which has no ``id``);
    # at runtime it is the resolved CRE, so read its id defensively.
    resolved = {
        getattr(link.document, "id", "")
        for standard in standards
        for link in standard.links
    }
    all_candidate_ids = [
        candidate.cre_id
        for suggestion in approved
        for candidate in suggestion.candidate_cres
    ]
    skipped = sorted({cid for cid in all_candidate_ids if cid not in resolved})
    total_links = sum(len(standard.links) for standard in standards)

    print(f"approved suggestions:   {len(approved)}")
    print(f"standards produced:     {len(standards)}")
    print(f"total CRE links:        {total_links}")
    print("skipped unknown CREs:   " + (", ".join(skipped) if skipped else "(none)"))
    print(
        "note: nothing was registered into the graph; live import/registration "
        "is F5 (follow-up PR)."
    )
    return _EXIT_OK


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the three Workstream F subcommands."""
    parser = argparse.ArgumentParser(
        prog="cheatsheets_workstream_f",
        description=(
            "OWASP Cheat Sheet -> CRE mapping review-artifact CLI (Workstream F)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="schema-validate a suggestions.json document")
    v.add_argument("suggestions", help="path to the suggestions document")
    v.set_defaults(func=_cmd_validate)

    g = sub.add_parser(
        "generate",
        help=(
            "validate + normalize a suggestions document; without workstreams "
            "A-E this just writes/normalizes the input"
        ),
    )
    g.add_argument("infile", help="input suggestions document")
    g.add_argument("outfile", help="output (normalized) suggestions document")
    g.set_defaults(func=_cmd_generate)

    c = sub.add_parser(
        "convert",
        help=(
            "convert approved suggestions to a ParseResult and print a summary; "
            "does NOT register into the graph (that is F5)"
        ),
    )
    c.add_argument("approved", help="path to the approved suggestions document")
    c.add_argument(
        "--db",
        default=None,
        help="database URI passed to cre_main.db_connect for CRE resolution",
    )
    c.set_defaults(func=_cmd_convert)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point: parse ``argv`` and dispatch to the chosen subcommand."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
