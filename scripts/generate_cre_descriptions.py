#!/usr/bin/env python3
"""One-shot CRE description generator → human approval table under tmp/.

Does **not** UPDATE ``cre.description``. After humans approve the table, run
staging surgery separately. Reuses LiteLLM via ``default_metadata_llm_fn`` and
linked Standard/Tool embedding prose (junk filtered). Not a Librarian runtime
module — steal ideas from cre_summary only.

Usage (local DB only — refuses Heroku/prod URLs):

  source venv/bin/activate
  set -a; source .env; set +a
  PYTHONPATH=. python scripts/generate_cre_descriptions.py \\
    --cache-file postgresql://cre:password@127.0.0.1:5432/cre \\
    --limit 5 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from application.utils.db_url import assert_local_db_url  # noqa: E402
from application.utils.cre_descriptions.generate import (  # noqa: E402
    CreDescriptionInput,
    propose_descriptions,
)
from application.utils.cre_descriptions.table import (  # noqa: E402
    write_approval_csv,
    write_approval_markdown,
)


def _load_neighbour_names(database: object) -> Dict[str, Tuple[str, ...]]:
    """``cre.id`` → neighbour CRE names via ``cre_links`` (both directions)."""
    session = getattr(database, "session", None)
    if session is None:
        return {}
    try:
        from application.database.db import CRE, InternalLinks
    except Exception:  # noqa: BLE001
        return {}

    id_to_name = {
        str(row.id): str(row.name or "")
        for row in session.query(CRE.id, CRE.name).all()
        if row.id
    }
    grouped: Dict[str, List[str]] = defaultdict(list)
    for link in session.query(InternalLinks.group, InternalLinks.cre).all():
        left, right = str(link.group), str(link.cre)
        if left in id_to_name and right in id_to_name:
            if id_to_name[right]:
                grouped[left].append(id_to_name[right])
            if id_to_name[left]:
                grouped[right].append(id_to_name[left])
    return {k: tuple(dict.fromkeys(v)) for k, v in grouped.items()}


def _load_inputs(database: object) -> List[CreDescriptionInput]:
    from application.utils.librarian.cre_text import load_linked_standard_refs

    session = getattr(database, "session", None)
    if session is None:
        return []
    from application.database.db import CRE

    linked = load_linked_standard_refs(database)
    neighbours = _load_neighbour_names(database)
    rows: List[CreDescriptionInput] = []
    for cre in session.query(CRE).order_by(CRE.external_id, CRE.name).all():
        cre_id = str(cre.id)
        refs = linked.get(cre_id) or ()
        prose = [ref.prose for ref in refs if getattr(ref, "prose", None)]
        rows.append(
            CreDescriptionInput(
                cre_id=cre_id,
                name=str(cre.name or ""),
                existing_description=str(cre.description or ""),
                linked_prose=prose,
                neighbour_names=list(neighbours.get(cre_id) or ()),
            )
        )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-file",
        default=os.environ.get("DEV_DATABASE_URL")
        or os.environ.get("CRE_CACHE_FILE", ""),
        help="SQLAlchemy URL (local only)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max CREs to process")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Emit approval rows without calling the LLM",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when cre.description is already non-empty",
    )
    parser.add_argument(
        "--output-dir",
        default="tmp",
        help="Directory for approval CSV/Markdown (default: tmp/)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get(
            "CRE_DESCRIPTION_MODEL",
            os.environ.get("CRE_LIBRARIAN_METADATA_MODEL", "gemini/gemini-2.5-flash"),
        ),
        help="LiteLLM model id recorded in the approval table",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.cache_file:
        print(
            "DEV_DATABASE_URL / CRE_CACHE_FILE / --cache-file required", file=sys.stderr
        )
        return 2
    assert_local_db_url(args.cache_file)

    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")

    from application.cmd.cre_main import db_connect

    database = db_connect(args.cache_file)
    records = _load_inputs(database)

    llm_fn = None
    if not args.dry_run:
        from application.utils.librarian.metadata_enricher import (
            default_metadata_llm_fn,
        )

        llm_fn = default_metadata_llm_fn(args.model)

    rows = propose_descriptions(
        records,
        llm_fn=llm_fn,
        model=args.model,
        limit=args.limit,
        force=args.force,
        dry_run=args.dry_run,
    )

    out_dir = Path(args.output_dir)
    csv_path = out_dir / "cre_description_approval.csv"
    md_path = out_dir / "cre_description_approval.md"
    write_approval_csv(csv_path, rows)
    write_approval_markdown(md_path, rows)
    print(
        f"wrote {len(rows)} approval rows → {csv_path} and {md_path} "
        f"(dry_run={args.dry_run} force={args.force})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
