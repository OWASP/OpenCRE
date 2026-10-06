from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[2]


class TestBrevityBotSkill(unittest.TestCase):
    def test_skill_and_fixtures_exist(self) -> None:
        skill = REPO / ".cursor" / "skills" / "brevity-bot" / "SKILL.md"
        examples = REPO / ".cursor" / "skills" / "brevity-bot" / "examples.md"
        launcher = REPO / ".cursor" / "skills" / "review-brevity" / "SKILL.md"
        self.assertTrue(skill.is_file(), skill)
        self.assertTrue(examples.is_file(), examples)
        self.assertTrue(launcher.is_file(), launcher)
        text = skill.read_text(encoding="utf-8")
        self.assertIn("NO_COMMENTS", text)
        self.assertIn("without dropping the fixes", text)
        self.assertIn("preserving correctness, quality, and security", text)
        ex = examples.read_text(encoding="utf-8")
        self.assertIn("Do not drop a security fix", ex)
        self.assertIn("AI blurb", ex)
