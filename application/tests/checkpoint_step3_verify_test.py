import os
import subprocess
import sys
import tempfile
import unittest

from scripts import checkpoint_step3_verify


class TestCheckpointStep3Verify(unittest.TestCase):
    REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    def test_run_checkpoint3_with_manual_edit(self) -> None:
        db_path = tempfile.mkstemp(prefix="cp3_test_", suffix=".sqlite")[1]
        report = checkpoint_step3_verify.run_checkpoint_3_verify(
            db_path=db_path, simulate_manual_edit=True
        )
        self.assertEqual(report.import_runs_created, 2)
        self.assertEqual(report.latest_run_version, "run2")
        self.assertEqual(report.added, 1)
        self.assertEqual(report.removed, 1)
        self.assertEqual(report.modified, 1)
        self.assertEqual(report.change_set_ops, 3)
        self.assertGreater(report.conflict_ops, 0)
        self.assertTrue(report.pass_status)

    def test_run_checkpoint3_without_manual_edit(self) -> None:
        db_path = tempfile.mkstemp(prefix="cp3_test_no_manual_", suffix=".sqlite")[1]
        report = checkpoint_step3_verify.run_checkpoint_3_verify(
            db_path=db_path, simulate_manual_edit=False
        )
        self.assertEqual(report.conflict_ops, 0)
        self.assertTrue(report.pass_status)

    def test_script_entrypoint_passes(self) -> None:
        db_path = tempfile.mkstemp(prefix="cp3_script_", suffix=".sqlite")[1]
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/checkpoint_step3_verify.py",
                "--db",
                db_path,
            ],
            cwd=self.REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
        self.assertIn("Checkpoint3: PASS", proc.stdout)
