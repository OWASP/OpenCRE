"""Tests for application.utils.noise_filter.regex_filter.

Uses unittest to match the project-wide discovery pattern.

Coverage groups:
    1. ConstructionTests   -- YAML loading, defaults, custom path
    2. PathRuleTests       -- each precedence rule fires correctly in isolation
    3. RealisticPathTests  -- table-driven against representative OWASP paths,
                              asserting >=90% rejection on known junk and 0%
                              on known docs (plan's acceptance criteria).
    4. RecordTests         -- is_noise_record + filter_records on ChangeRecords
"""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from application.utils.noise_filter.regex_filter import (
    DEFAULT_PATTERNS_PATH,
    RegexFilter,
)
from application.utils.noise_filter.schemas import ChangeRecord

# --- Helper: build a minimal ChangeRecord ---------------------------------


def _record_with_path(path: str) -> ChangeRecord:
    """Build a minimal valid ChangeRecord whose locator.path is `path`."""
    return ChangeRecord.model_validate(
        {
            "schema_version": "0.2.0",
            "chunk_id": f"chk:test:{path}",
            "artifact_id": f"art:test:{path}",
            "pipeline_run_id": "20260607T000000Z",
            "text": "non-empty text",
            "span": {"index": 0, "total": 1, "heading_path": []},
            "source": {
                "type": "github",
                "repo": "OWASP/test",
                "commit_sha": "abc123",
                "committed_at": "2026-06-07T00:00:00Z",
            },
            "locator": {"kind": "repo_path", "id": path, "path": path},
        }
    )


# --- 1. Construction ------------------------------------------------------


class ConstructionTests(unittest.TestCase):

    def test_default_patterns_file_loads(self) -> None:
        filt = RegexFilter()
        # Should have non-empty rule sets from the shipped YAML.
        self.assertTrue(len(filt.deny_extensions) > 0)
        self.assertTrue(len(filt.deny_filenames) > 0)
        self.assertTrue(len(filt.deny_paths) > 0)
        self.assertEqual(filt.patterns_path, DEFAULT_PATTERNS_PATH)

    def test_custom_patterns_path(self) -> None:
        custom_yaml = textwrap.dedent(
            """\
            deny_extensions: [.foo]
            deny_filenames: [BAR]
            deny_paths: ["baz/**"]
            allow_overrides: []
            """
        )
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(custom_yaml)
            tmp = Path(f.name)
        try:
            filt = RegexFilter(patterns_path=tmp)
            self.assertEqual(filt.deny_extensions, (".foo",))
            self.assertEqual(filt.deny_filenames, frozenset({"BAR"}))
            self.assertEqual(filt.deny_paths, ("baz/**",))
            self.assertEqual(filt.allow_overrides, ())
        finally:
            tmp.unlink()

    def test_empty_yaml_handled(self) -> None:
        """Empty YAML loads to None; the filter must tolerate this."""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            tmp = Path(f.name)
        try:
            filt = RegexFilter(patterns_path=tmp)
            self.assertEqual(filt.deny_extensions, ())
            self.assertEqual(filt.deny_filenames, frozenset())
            # Everything passes through.
            self.assertEqual(filt.is_noise_path("anything.css"), (False, ""))
        finally:
            tmp.unlink()


# --- 2. Per-rule precedence ------------------------------------------------


class PathRuleTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.filt = RegexFilter()

    def test_extension_match(self) -> None:
        is_noise, reason = self.filt.is_noise_path("frontend/styles/app.css")
        self.assertTrue(is_noise)
        self.assertIn("deny_extension", reason)
        self.assertIn(".css", reason)

    def test_filename_match(self) -> None:
        is_noise, reason = self.filt.is_noise_path("frontend/package-lock.json")
        self.assertTrue(is_noise)
        self.assertIn("deny_filename", reason)

    def test_path_glob_match(self) -> None:
        is_noise, reason = self.filt.is_noise_path("tests/integration/foo.py")
        self.assertTrue(is_noise)
        self.assertIn("deny_path", reason)

    def test_any_depth_test_path(self) -> None:
        """**/tests/** should catch deeply-nested test directories."""
        is_noise, _ = self.filt.is_noise_path(
            "application/utils/something/tests/foo.py"
        )
        self.assertTrue(is_noise)

    def test_passing_doc_path(self) -> None:
        """A normal security doc path should be accepted."""
        is_noise, reason = self.filt.is_noise_path(
            "document/4-Web_Application_Security_Testing/04-Authentication_Testing/01-Testing.md"
        )
        self.assertFalse(is_noise)
        self.assertEqual(reason, "")

    def test_allow_override_wins_over_deny(self) -> None:
        """An allow-override beats any deny rule on the same path."""
        custom = textwrap.dedent(
            """\
            deny_extensions: [.md]
            deny_filenames: []
            deny_paths: ["docs/**"]
            allow_overrides: ["docs/**"]
            """
        )
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(custom)
            tmp = Path(f.name)
        try:
            filt = RegexFilter(patterns_path=tmp)
            # Without the override, this would be denied twice (extension + path).
            # With it, accepted at both top-level and nested.
            self.assertFalse(filt.is_noise_path("docs/guide.md")[0])
            self.assertFalse(filt.is_noise_path("docs/designs/spec.md")[0])
        finally:
            tmp.unlink()


# --- 3. Realistic paths -- plan's acceptance criteria --------------------


# Representative paths chosen from real OWASP repos (WSTG, ASVS, CheatSheets,
# SAMM) plus common junk. Used to validate the >=90% / 0% rejection rates
# specified in the original plan.

KNOWN_JUNK_PATHS = [
    # Lockfiles + build artifacts
    "frontend/package-lock.json",
    "yarn.lock",
    "node_modules/lodash/index.js",
    "dist/bundle.js.map",
    "build/output.css",
    # Images
    "assets/logo.png",
    "static/images/icon.svg",
    "design/banner.jpg",
    # Layouts / Hugo templates
    "Website/layouts/single.html",
    "themes/default/_layouts/page.html",
    "src/_includes/footer.html",
    # CI/CD
    ".github/workflows/linter.yml",
    ".github/ISSUE_TEMPLATE.md",
    ".gitlab-ci.yml",
    # Test dirs at varying depths
    "tests/test_auth.py",
    "application/utils/parser/tests/fixtures/sample.json",
    "test/integration/test_api.py",
    # SAMM empirical hits
    "Supporting Resources/meetings/10012018.md",
    "Supporting Resources/enterprise metrics/overview.md",
    # Generic web fonts
    "static/fonts/Roboto.woff2",
    "assets/fonts/code.ttf",
]

KNOWN_DOC_PATHS = [
    # WSTG security testing docs
    "document/4-Web_Application_Security_Testing/04-Authentication_Testing/01-Testing.md",
    "document/4-Web_Application_Security_Testing/07-Input_Validation_Testing/12-Testing_for_Command_Injection.md",
    # ASVS appendices and chapters
    "5.0/en/0x12-V3-Authentication.md",
    "5.0/en/0x92-Appendix-C_Cryptography.md",
    # Cheatsheets
    "cheatsheets/OAuth2_Cheat_Sheet.md",
    "cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.md",
    # Top-level README that mentions a security project (allowed under recall-first)
    "README.md",
    # CONTRIBUTING with security@ mailto (mixed signal -- let Stage 2 judge)
    "CONTRIBUTING.md",
    # SAMM content (organizational but recall-first: let Stage 2 decide)
    "Website/content/en/sponsors.md",
    "Website/content/en/user-day/_index.md",
]


class RealisticPathTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.filt = RegexFilter()

    def test_rejection_rate_on_known_junk_at_least_90_percent(self) -> None:
        """Plan acceptance criterion: regex catches >=90% of known junk paths."""
        rejected = sum(1 for p in KNOWN_JUNK_PATHS if self.filt.is_noise_path(p)[0])
        rate = rejected / len(KNOWN_JUNK_PATHS)
        # Print details to make failures actionable.
        missed = [p for p in KNOWN_JUNK_PATHS if not self.filt.is_noise_path(p)[0]]
        self.assertGreaterEqual(
            rate,
            0.90,
            msg=(
                f"Junk rejection rate {rate:.0%} below 90%. "
                f"Paths missed by regex (would reach Stage 2): {missed}"
            ),
        )

    def test_zero_false_positives_on_known_doc_paths(self) -> None:
        """Plan acceptance criterion: no security docs are wrongly rejected."""
        false_positives = [p for p in KNOWN_DOC_PATHS if self.filt.is_noise_path(p)[0]]
        self.assertEqual(
            false_positives,
            [],
            msg=f"Security doc paths wrongly flagged as noise: {false_positives}",
        )


# --- 4. ChangeRecord-level API + generator -------------------------------


class RecordTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.filt = RegexFilter()

    def test_is_noise_record_uses_locator_path(self) -> None:
        rec = _record_with_path("frontend/styles/app.css")
        is_noise, reason = self.filt.is_noise_record(rec)
        self.assertTrue(is_noise)
        self.assertIn(".css", reason)

    def test_is_noise_record_accepts_security_doc(self) -> None:
        rec = _record_with_path(
            "document/4-Web_Application_Security_Testing/04-Authentication_Testing/01-Testing.md"
        )
        is_noise, _ = self.filt.is_noise_record(rec)
        self.assertFalse(is_noise)

    def test_filter_records_yields_only_accepted(self) -> None:
        records = [
            _record_with_path("frontend/app.css"),
            _record_with_path("document/security/auth.md"),
            _record_with_path("tests/test_something.py"),
            _record_with_path("cheatsheets/OAuth.md"),
        ]
        accepted = list(self.filt.filter_records(records))
        self.assertEqual(len(accepted), 2)
        self.assertEqual(
            sorted(r.locator.path for r in accepted),
            ["cheatsheets/OAuth.md", "document/security/auth.md"],
        )

    def test_filter_records_is_lazy(self) -> None:
        """The generator should not consume the iterable eagerly."""

        def gen():
            yield _record_with_path("a.css")
            raise RuntimeError("filter_records should not pull past the first record")

        out = self.filt.filter_records(gen())
        # We can advance once without raising -- the .css record is rejected,
        # so the generator pulls the next one and hits the RuntimeError.
        with self.assertRaises(RuntimeError):
            next(out)


if __name__ == "__main__":
    unittest.main()
