#!/usr/bin/env python3
"""
Checkpoint 4 verification (Steps 9 & 10):

- Step 9: central import pipeline is the entrypoint for applying ParseResult.
- Step 10: incremental GA: identical reimport should not reschedule GA; structural
  change should reschedule.

This verifier is intentionally unit-like (mocks gap_analysis + neo4j) so it can
run deterministically without external services.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass
from unittest.mock import Mock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from application import sqla
from application.cmd import cre_main
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_pipeline
from application.utils.external_project_parsers import base_parser_defs


@dataclass
class Checkpoint4Report:
    ga_schedule_calls_first: int
    ga_schedule_calls_second: int
    ga_schedule_calls_after_change: int
    pass_status: bool


def run(db_path: str) -> Checkpoint4Report:
    collection = cre_main.db_connect(path=db_path)
    sqla.create_all()

    # Seed another standard so GA would have a pair to schedule.
    collection.add_node(defs.Standard(name="ASVS", section="x", sectionID="V1"))

    std = defs.Standard(
        name="CWE",
        section="Some CWE",
        sectionID="123",
        tags=base_parser_defs.build_tags(
            family=base_parser_defs.Family.STANDARD,
            subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
            audience=base_parser_defs.Audience.DEVELOPER,
            maturity=base_parser_defs.Maturity.STABLE,
            source="checkpoint4",
            extra=[],
        ),
    )

    pr = base_parser_defs.ParseResult(
        results={"CWE": [std]},
        calculate_gap_analysis=True,
        calculate_embeddings=False,
    )

    redis_conn = Mock(get=Mock(return_value=None), set=Mock())

    with patch.object(cre_main, "populate_neo4j_db") as pop_mock, patch.object(
        cre_main.gap_analysis, "schedule"
    ) as schedule_mock, patch.object(
        cre_main.redis, "connect", return_value=redis_conn
    ), patch.object(
        cre_main.redis, "wait_for_jobs"
    ), patch.object(
        cre_main.job.Job, "fetch", return_value=Mock()
    ):
        # First apply: schedules GA.
        import_pipeline.apply_parse_result(
            parse_result=pr, collection=collection, db_connection_str=db_path
        )
        calls_first = schedule_mock.call_count

        # Second apply, identical structure: should skip GA.
        import_pipeline.apply_parse_result(
            parse_result=pr, collection=collection, db_connection_str=db_path
        )
        calls_second = schedule_mock.call_count

        # Structural change: add another node entry under CWE.
        std2 = defs.Standard(
            name="CWE",
            section="Another CWE section",
            sectionID="124",
            tags=base_parser_defs.build_tags(
                family=base_parser_defs.Family.STANDARD,
                subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
                audience=base_parser_defs.Audience.DEVELOPER,
                maturity=base_parser_defs.Maturity.STABLE,
                source="checkpoint4",
                extra=[],
            ),
        )
        pr_changed = base_parser_defs.ParseResult(
            results={"CWE": [std, std2]},
            calculate_gap_analysis=True,
            calculate_embeddings=False,
        )
        import_pipeline.apply_parse_result(
            parse_result=pr_changed, collection=collection, db_connection_str=db_path
        )
        calls_after_change = schedule_mock.call_count

    pass_status = (calls_first > 0) and (calls_second == calls_first) and (
        calls_after_change > calls_second
    )
    return Checkpoint4Report(
        ga_schedule_calls_first=calls_first,
        ga_schedule_calls_second=calls_second,
        ga_schedule_calls_after_change=calls_after_change,
        pass_status=pass_status,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Checkpoint 4 verification.")
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite DB path. Default: temporary file.",
    )
    args = parser.parse_args()

    db_path = args.db or tempfile.mkstemp(prefix="opencre_checkpoint4_", suffix=".sqlite")[1]
    report = run(db_path=db_path)

    print("=== Checkpoint 4 verification ===")
    print(f"DB: {db_path}")
    print(f"GA schedule calls after first import: {report.ga_schedule_calls_first}")
    print(f"GA schedule calls after second identical import: {report.ga_schedule_calls_second}")
    print(f"GA schedule calls after structural change: {report.ga_schedule_calls_after_change}")
    print(f"Checkpoint4: {'PASS' if report.pass_status else 'FAIL'}")

    if not report.pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

