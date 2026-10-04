"""Exercise incremental path discovery against real Git repositories."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from application.utils.harvester.change_detector import ChangeDetector
from application.utils.harvester.git_repository_client import GitRepositoryClient


class ChangeDetectorPathTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture_root = Path(__file__).resolve().parents[3] / "tmp" / "harvester-it"
        fixture_root.mkdir(parents=True, exist_ok=True)
        self.tempdir = tempfile.TemporaryDirectory(dir=fixture_root)
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.git("init", "--initial-branch=main")
        self.detector = ChangeDetector(
            GitRepositoryClient("LOCAL", "fixture", local_path=self.root)
        )

    def git(self, *args: str) -> str:
        return subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "user.name=Test User",
                "-c",
                "user.email=test@example.invalid",
                "-C",
                str(self.root),
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()

    def write_file(self, name: str, text: str = "# Auth\nUse MFA.\n") -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self) -> str:
        self.git("add", ".")
        self.git("commit", "--allow-empty", "-m", "Fixture snapshot")
        return self.git("rev-parse", "HEAD")

    def test_preserves_changed_paths_and_reads_their_committed_contents(self) -> None:
        paths = [
            "docs/plain.md",
            "docs/nested/café.md",
            "docs/login with spaces.md",
            'docs/quote"name.md',
            "docs/tab\tname.md",
            "docs/line\nname.md",
            "docs/carriage\rreturn.md",
            "docs/ whitespace .md",
        ]
        for path in paths:
            self.write_file(path)
        base = self.commit()
        expected_text = "# Auth\nRequire MFA and review sessions.\n"
        for path in paths:
            self.write_file(path, expected_text)
        self.write_file("docs/new.md", expected_text)
        target = self.commit()
        self.write_file("docs/untracked.md")

        for quote_paths in ("true", "false"):
            with self.subTest(quote_paths=quote_paths):
                self.git("config", "core.quotePath", quote_paths)
                changed = self.detector.get_modified_files_since(base, target)
                self.assertEqual(changed, sorted(paths + ["docs/new.md"]))
                for path in changed:
                    self.assertEqual(
                        self.detector.repository_client.get_file_at_commit(
                            target, path
                        ),
                        expected_text,
                    )

    def test_unchanged_snapshot_has_no_changed_paths(self) -> None:
        self.write_file("docs/auth.md")
        head = self.commit()
        self.assertEqual(self.detector.get_modified_files_since(head, head), [])

    def test_preserves_deleted_path_in_diff_results(self) -> None:
        path = "docs/café\nold.md"
        self.write_file(path)
        base = self.commit()
        self.git("rm", "--", path)
        target = self.commit()
        self.assertEqual(self.detector.get_modified_files_since(base, target), [path])


if __name__ == "__main__":
    unittest.main()
