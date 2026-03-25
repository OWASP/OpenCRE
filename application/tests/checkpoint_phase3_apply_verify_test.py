import unittest

from scripts import checkpoint_phase3_apply_verify


class TestCheckpointPhase3ApplyVerify(unittest.TestCase):
    def test_intermediate_apply_checkpoint_passes(self) -> None:
        report = checkpoint_phase3_apply_verify.run()
        self.assertEqual(report.dry_run_status, 200)
        self.assertEqual(report.apply_status, 200)
        self.assertEqual(report.apply_again_status, 200)
        self.assertEqual(report.conflict_status, 409)
        self.assertTrue(report.pass_status)

