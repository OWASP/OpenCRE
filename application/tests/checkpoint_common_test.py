"""Unit tests for application.utils.checkpoint_common."""

from __future__ import annotations

import os
import tempfile

from application.utils import checkpoint_common as cc


def test_diff_standards_empty() -> None:
    a, b, c = cc.diff_standards({}, {})
    assert a == b == c == []


def test_scoped_ga_diff_pair_scope() -> None:
    import_ga = {"A >> B": "1", "X >> Y": "2"}
    golden_ga = {"A >> B": "1", "X >> Y": "9"}
    names = {"A", "B"}
    missing, mismatch = cc.scoped_ga_diff(import_ga, golden_ga, names)
    assert "A >> B" not in missing
    assert "X >> Y" not in missing  # out of scope
    assert mismatch == []


def test_final_diff_bounds_errors() -> None:
    errs = cc.final_diff_bounds_errors(
        only_golden=0,
        only_import=1,
        changed=0,
        scoped_ga_missing=0,
        scoped_ga_mismatch=0,
        bounds={"only_import_max": 0},
        label="final",
    )
    assert any("only_import" in e for e in errs)


def test_metric_bounds_errors_min_max() -> None:
    metrics = {"node_count": 5, "gap_analysis_rows": 10}
    bounds = {"node_count_min": 1, "node_count_max": 10, "gap_analysis_rows_max": 9}
    errs = cc.metric_bounds_errors(metrics, bounds, "t")
    assert any("gap_analysis_rows" in e and "> max" in e for e in errs)


def test_sqlite_metrics_minimal_db() -> None:
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    try:
        import sqlite3

        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE node (
              id INTEGER PRIMARY KEY,
              name TEXT, section TEXT, subsection TEXT, version TEXT, section_id TEXT,
              description TEXT, tags TEXT, ntype TEXT, link TEXT, document_metadata TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE gap_analysis_results (
              cache_key TEXT PRIMARY KEY,
              ga_object TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE cre (
              id INTEGER PRIMARY KEY,
              name TEXT
            )
            """
        )
        conn.execute("INSERT INTO node (name, section, section_id) VALUES ('A','1','')")
        conn.execute("INSERT INTO gap_analysis_results VALUES ('k','{}')")
        conn.execute("INSERT INTO cre VALUES (1,'x')")
        conn.commit()
        conn.close()

        m = cc.sqlite_metrics(path)
        assert m["node_count"] == 1
        assert m["gap_analysis_rows"] == 1
        assert m["standards_keys"] == 1
        assert m["cre_count"] == 1
    finally:
        os.unlink(path)


def test_external_parser_classes_excludes_master() -> None:
    classes = cc.external_parser_classes()
    names = {getattr(c, "name", None) for c in classes}
    assert cc.MASTER_PARSER_NAME not in names
    assert len(classes) >= 1
