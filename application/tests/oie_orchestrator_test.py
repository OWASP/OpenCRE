"""Tests for the OIE PoC orchestrator (no Module A/B/C patches)."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from application.utils.oie_orchestrator.pipeline import run_oie_demo_pipeline


class OieOrchestratorTest(unittest.TestCase):
    def test_default_skips_a_and_records_b_todo_or_ok(self) -> None:
        """On main without #989, B is todo; with inject, B is ok."""
        result = run_oie_demo_pipeline(
            cache_file="sqlite:///:memory:",
            pipeline_run_id="run-test-1",
            skip_a=True,
            skip_b=False,
            skip_c=True,
            dry_run=True,
        )
        self.assertEqual(result.run_id, "run-test-1")
        by_name = {s.name: s for s in result.stages}
        self.assertEqual(by_name["module_a_harvester"].status, "skipped")
        self.assertIn(by_name["module_b_noise_filter"].status, ("todo", "ok", "error"))
        self.assertEqual(by_name["module_c_librarian"].status, "skipped")

    def test_run_a_without_entry_is_todo(self) -> None:
        result = run_oie_demo_pipeline(
            cache_file="sqlite:///:memory:",
            pipeline_run_id="run-a",
            skip_a=False,
            skip_b=True,
            skip_c=True,
        )
        stage = result.stages[0]
        self.assertEqual(stage.name, "module_a_harvester")
        self.assertEqual(stage.status, "todo")
        self.assertIn("TODO:", stage.detail)
        self.assertIn("run_harvester", stage.detail)

    def test_injected_b_and_c_entry_points(self) -> None:
        calls: list[str] = []

        def fake_b(session: object, run_id: str, dry_run: bool = False) -> object:
            calls.append(f"b:{run_id}:{dry_run}")
            return SimpleNamespace(
                to_json=lambda: json.dumps(
                    {"run_id": run_id, "read": 2, "inserted": 1, "dry_run": dry_run}
                )
            )

        def fake_c(
            cache_file: str, dry_run: bool = True, source_jsonl: str | None = None
        ) -> None:
            calls.append(f"c:{dry_run}:{source_jsonl}")

        result = run_oie_demo_pipeline(
            cache_file="sqlite:///:memory:",
            pipeline_run_id="run-inject",
            skip_a=True,
            skip_b=False,
            skip_c=False,
            dry_run=True,
            librarian_source_jsonl="fixture.jsonl",
            run_noise_filter_fn=fake_b,
            run_librarian_fn=fake_c,
        )
        by_name = {s.name: s for s in result.stages}
        self.assertEqual(by_name["module_b_noise_filter"].status, "ok")
        self.assertEqual(by_name["module_b_noise_filter"].summary["inserted"], 1)
        self.assertEqual(by_name["module_c_librarian"].status, "ok")
        self.assertEqual(calls, ["b:run-inject:True", "c:True:fixture.jsonl"])
        self.assertTrue(result.to_dict()["ok"])

    def test_b_error_surfaces_without_raising(self) -> None:
        def boom(*_a: object, **_k: object) -> object:
            raise RuntimeError("llm down")

        result = run_oie_demo_pipeline(
            cache_file="sqlite:///:memory:",
            pipeline_run_id="run-err",
            skip_a=True,
            skip_c=True,
            run_noise_filter_fn=boom,
        )
        self.assertEqual(result.stages[1].status, "error")
        self.assertIn("llm down", result.stages[1].detail)
        self.assertFalse(result.to_dict()["ok"])


if __name__ == "__main__":
    unittest.main()
