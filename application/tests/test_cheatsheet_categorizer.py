"""
Tests for Workstream C: cheatsheet_categorizer
===============================================

Covers:
  - TAXONOMY integrity
  - categorize_cheatsheet -- deterministic path
  - categorize_cheatsheet -- LLM path (success, bad labels, exception)
  - categorize_cheatsheet -- UNCATEGORIZED fallback
  - group_cheatsheets -- grouping, stable IDs, ordering
  - CheatsheetGroup.make_group_id -- determinism
  - _validate_labels helper
"""

import unittest

from application.utils.external_project_parsers.parsers.cheatsheet_categorizer import (  # noqa: E501
    TAXONOMY,
    UNCATEGORIZED,
    CheatsheetGroup,
    CheatsheetRecord,
    categorize_cheatsheet,
    group_cheatsheets,
    _validate_labels,
    _deterministic_categorize,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    source_id: str,
    title: str,
    headings=None,
    category_hints=None,
) -> CheatsheetRecord:
    """Return a minimal CheatsheetRecord for use in tests."""
    base = "https://cheatsheetseries.owasp.org/cheatsheets"
    return CheatsheetRecord(
        source="owasp_cheatsheets",
        source_id=source_id,
        title=title,
        hyperlink=f"{base}/{source_id}.html",
        summary="",
        headings=headings or [],
        raw_markdown_path=f"cheatsheets/{source_id}.md",
        category_hints=category_hints or [],
    )


# ---------------------------------------------------------------------------
# 1. TAXONOMY integrity
# ---------------------------------------------------------------------------


class TestTaxonomy(unittest.TestCase):
    """Verify the controlled taxonomy list stays well-formed."""

    def test_uncategorized_in_taxonomy(self):
        """UNCATEGORIZED sentinel must be present in TAXONOMY."""
        self.assertIn(UNCATEGORIZED, TAXONOMY)

    def test_no_duplicates(self):
        """Every label must appear exactly once."""
        self.assertEqual(len(TAXONOMY), len(set(TAXONOMY)))

    def test_all_lowercase(self):
        """Labels must be lowercase to allow case-insensitive matching."""
        for label in TAXONOMY:
            self.assertEqual(label, label.lower(), f"Label not lowercase: {label!r}")

    def test_minimum_size(self):
        """Taxonomy must have at least 10 real labels plus UNCATEGORIZED."""
        self.assertGreater(len(TAXONOMY), 10)


# ---------------------------------------------------------------------------
# 2. categorize_cheatsheet -- deterministic, known categories
# ---------------------------------------------------------------------------


class TestCategorizeDeterministic(unittest.TestCase):
    """Deterministic keyword-based categorisation."""

    def _cats(self, record):
        """Shorthand for categorize_cheatsheet."""
        return categorize_cheatsheet(record)

    # --- authentication ---
    def test_authentication_by_title(self):
        r = _make_record("Authentication_Cheat_Sheet", "Authentication Cheat Sheet")
        self.assertIn("authentication", self._cats(r))

    def test_password_implies_authentication(self):
        r = _make_record("Password_Storage_Cheat_Sheet", "Password Storage Cheat Sheet")
        self.assertIn("authentication", self._cats(r))

    def test_oauth_implies_authentication(self):
        r = _make_record(
            "OAuth_Cheat_Sheet",
            "OAuth 2.0 Cheat Sheet",
            headings=["Authorization Code Flow"],
        )
        self.assertIn("authentication", self._cats(r))

    # --- secrets management ---
    def test_secrets_management(self):
        r = _make_record(
            "Secrets_Management_Cheat_Sheet",
            "Secrets Management Cheat Sheet",
            headings=["Introduction", "Secret Rotation", "Operational Practices"],
        )
        self.assertIn("secrets-management", self._cats(r))

    def test_secrets_and_operations_both_match(self):
        r = _make_record(
            "Secrets_Management_Cheat_Sheet",
            "Secrets Management Cheat Sheet",
            headings=["Operational Practices", "Secret Rotation"],
        )
        result = self._cats(r)
        self.assertIn("secrets-management", result)
        self.assertIn("operations", result)

    # --- cryptography ---
    def test_cryptography_by_title(self):
        r = _make_record(
            "Cryptographic_Storage_Cheat_Sheet",
            "Cryptographic Storage Cheat Sheet",
        )
        self.assertIn("cryptography", self._cats(r))

    def test_tls_implies_cryptography(self):
        r = _make_record("TLS_Cheat_Sheet", "TLS Cheat Sheet")
        self.assertIn("cryptography", self._cats(r))

    # --- injection ---
    def test_sql_injection(self):
        r = _make_record("SQL_Injection_Prevention", "SQL Injection Prevention")
        self.assertIn("injection", self._cats(r))

    # --- logging ---
    def test_logging(self):
        r = _make_record("Logging_Cheat_Sheet", "Logging Cheat Sheet")
        self.assertIn("logging-and-monitoring", self._cats(r))

    # --- api security ---
    def test_api_security(self):
        r = _make_record(
            "REST_Security_Cheat_Sheet",
            "REST Security Cheat Sheet",
            headings=["API Security Overview"],
        )
        result = self._cats(r)
        self.assertIn(
            "api-security",
            result,
            f"Expected api-security in {result}",
        )

    # --- output encoding / xss ---
    def test_xss_implies_output_encoding(self):
        r = _make_record("XSS_Prevention_Cheat_Sheet", "XSS Prevention Cheat Sheet")
        self.assertIn("output-encoding", self._cats(r))

    # --- container security ---
    def test_docker_implies_container(self):
        r = _make_record("Docker_Security_Cheat_Sheet", "Docker Security Cheat Sheet")
        self.assertIn("container-security", self._cats(r))

    # --- category hints contribute ---
    def test_category_hints_used(self):
        r = _make_record(
            "Misc_Cheat_Sheet",
            "Miscellaneous Cheat Sheet",
            category_hints=["cloud"],
        )
        self.assertIn("cloud-security", self._cats(r))

    # --- output properties ---
    def test_output_is_sorted(self):
        r = _make_record(
            "Auth_Session",
            "Authentication Session Management",
            headings=["Session Tokens", "Password Policy"],
        )
        result = self._cats(r)
        self.assertEqual(result, sorted(result))

    def test_output_no_duplicates(self):
        r = _make_record("Auth_Auth", "Authentication Authentication")
        result = self._cats(r)
        self.assertEqual(len(result), len(set(result)))

    def test_labels_all_in_taxonomy(self):
        r = _make_record(
            "Secrets_Management_Cheat_Sheet",
            "Secrets Management Cheat Sheet",
            headings=["Secret Rotation", "Logging Practices", "Encryption"],
        )
        for label in categorize_cheatsheet(r):
            self.assertIn(label, TAXONOMY, f"Label {label!r} not in TAXONOMY")

    def test_determinism_same_input_same_output(self):
        r = _make_record(
            "Secrets_Management_Cheat_Sheet",
            "Secrets Management Cheat Sheet",
            headings=["Secret Rotation", "Operational Practices"],
        )
        self.assertEqual(categorize_cheatsheet(r), categorize_cheatsheet(r))


# ---------------------------------------------------------------------------
# 3. categorize_cheatsheet -- UNCATEGORIZED fallback
# ---------------------------------------------------------------------------


class TestUncategorizedFallback(unittest.TestCase):
    """Unknown inputs must map to UNCATEGORIZED without raising."""

    def test_empty_record_returns_uncategorized(self):
        r = _make_record("Unknown_Cheat_Sheet", "Unknown Topic")
        self.assertEqual(categorize_cheatsheet(r), [UNCATEGORIZED])

    def test_uncategorized_not_mixed_with_real_labels(self):
        """If any real label matches, UNCATEGORIZED must NOT appear."""
        r = _make_record("Auth_Cheat_Sheet", "Authentication Cheat Sheet")
        self.assertNotIn(UNCATEGORIZED, categorize_cheatsheet(r))


# ---------------------------------------------------------------------------
# 4. categorize_cheatsheet -- LLM path
# ---------------------------------------------------------------------------


class TestCategorizeLLMPath(unittest.TestCase):
    """LLM integration: success, fallback on bad output, fallback on error."""

    def _secrets_record(self):
        """Reusable secrets management record."""
        return _make_record(
            "Secrets_Management_Cheat_Sheet", "Secrets Management Cheat Sheet"
        )

    def test_llm_success_returns_llm_labels(self):
        def good_llm(record):
            return ["secrets-management", "operations"]

        result = categorize_cheatsheet(
            self._secrets_record(),
            use_llm=True,
            llm_categorize_fn=good_llm,
        )
        self.assertIn("secrets-management", result)
        self.assertIn("operations", result)

    def test_llm_bad_labels_falls_back_to_deterministic(self):
        """LLM returns labels not in TAXONOMY -- fall back."""

        def bad_llm(record):
            return ["not-a-real-label", "also-fake"]

        result = categorize_cheatsheet(
            self._secrets_record(),
            use_llm=True,
            llm_categorize_fn=bad_llm,
        )
        for label in result:
            self.assertIn(label, TAXONOMY)
        self.assertIn("secrets-management", result)

    def test_llm_exception_falls_back_to_deterministic(self):
        """LLM raises an exception -- fall back gracefully."""

        def crashing_llm(record):
            raise RuntimeError("API timeout")

        result = categorize_cheatsheet(
            self._secrets_record(),
            use_llm=True,
            llm_categorize_fn=crashing_llm,
        )
        self.assertIn("secrets-management", result)

    def test_llm_returns_empty_list_falls_back(self):
        """Empty LLM response triggers deterministic fallback."""

        def empty_llm(record):
            return []

        result = categorize_cheatsheet(
            self._secrets_record(),
            use_llm=True,
            llm_categorize_fn=empty_llm,
        )
        self.assertIn("secrets-management", result)

    def test_llm_returns_non_list_falls_back(self):
        """Non-list LLM response triggers deterministic fallback."""

        def bad_type_llm(record):
            return "secrets-management"  # string, not list

        result = categorize_cheatsheet(
            self._secrets_record(),
            use_llm=True,
            llm_categorize_fn=bad_type_llm,
        )
        for label in result:
            self.assertIn(label, TAXONOMY)

    def test_use_llm_false_ignores_llm_fn(self):
        """use_llm=False must not call llm_categorize_fn at all."""
        call_count = {"n": 0}

        def tracking_llm(record):
            call_count["n"] += 1
            return ["authentication"]

        categorize_cheatsheet(
            self._secrets_record(),
            use_llm=False,
            llm_categorize_fn=tracking_llm,
        )
        self.assertEqual(call_count["n"], 0)


# ---------------------------------------------------------------------------
# 5. group_cheatsheets
# ---------------------------------------------------------------------------


class TestGroupCheatsheets(unittest.TestCase):
    """Grouping behaviour, stable IDs, and membership completeness."""

    def setUp(self):
        self.auth_record = _make_record(
            "Authentication_Cheat_Sheet", "Authentication Cheat Sheet"
        )
        self.password_record = _make_record(
            "Password_Storage_Cheat_Sheet", "Password Storage Cheat Sheet"
        )
        self.secrets_record = _make_record(
            "Secrets_Management_Cheat_Sheet",
            "Secrets Management Cheat Sheet",
            headings=["Secret Rotation", "Operational Practices"],
        )
        self.unknown_record = _make_record("Unknown_Topic_Cheat_Sheet", "Unknown Topic")

    def test_same_category_same_group(self):
        """Records with identical label sets must land in the same group."""
        auth_labels = categorize_cheatsheet(self.auth_record)
        pwd_labels = categorize_cheatsheet(self.password_record)
        self.assertEqual(
            auth_labels,
            pwd_labels,
            "auth and password records must share the same labels",
        )
        groups = group_cheatsheets([self.auth_record, self.password_record])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].members), 2)

    def test_different_categories_different_groups(self):
        """Records with different label sets must land in different groups."""
        auth_labels = categorize_cheatsheet(self.auth_record)
        secrets_labels = categorize_cheatsheet(self.secrets_record)
        self.assertNotEqual(
            auth_labels,
            secrets_labels,
            "auth and secrets records must have different labels",
        )
        groups = group_cheatsheets([self.auth_record, self.secrets_record])
        self.assertGreater(len(groups), 1)

    def test_unknown_record_in_uncategorized_group(self):
        groups = group_cheatsheets([self.unknown_record])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].labels, [UNCATEGORIZED])

    def test_group_ids_are_stable(self):
        """Same input twice must produce the same group_ids."""
        records = [self.auth_record, self.secrets_record, self.unknown_record]
        first = {g.group_id for g in group_cheatsheets(records)}
        second = {g.group_id for g in group_cheatsheets(records)}
        self.assertEqual(first, second)

    def test_output_is_sorted_by_group_id(self):
        """Groups must be returned in ascending group_id order."""
        records = [
            self.auth_record,
            self.secrets_record,
            self.unknown_record,
            self.password_record,
        ]
        groups = group_cheatsheets(records)
        ids = [g.group_id for g in groups]
        self.assertEqual(ids, sorted(ids))

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(group_cheatsheets([]), [])

    def test_all_members_present(self):
        """Every input record must appear in exactly one group."""
        records = [self.auth_record, self.secrets_record, self.unknown_record]
        groups = group_cheatsheets(records)
        all_members = [m for g in groups for m in g.members]
        self.assertCountEqual(all_members, records)

    def test_group_labels_all_in_taxonomy(self):
        """Group labels must be drawn from TAXONOMY."""
        records = [self.auth_record, self.secrets_record, self.unknown_record]
        for group in group_cheatsheets(records):
            for label in group.labels:
                self.assertIn(label, TAXONOMY)

    def test_single_record(self):
        """A single record must produce exactly one group."""
        groups = group_cheatsheets([self.auth_record])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].members[0], self.auth_record)


# ---------------------------------------------------------------------------
# 6. CheatsheetGroup.make_group_id
# ---------------------------------------------------------------------------


class TestMakeGroupId(unittest.TestCase):
    """make_group_id must be deterministic and order-independent."""

    def test_same_labels_same_id(self):
        a = CheatsheetGroup.make_group_id(["authentication", "session-management"])
        b = CheatsheetGroup.make_group_id(["authentication", "session-management"])
        self.assertEqual(a, b)

    def test_order_independent(self):
        a = CheatsheetGroup.make_group_id(["authentication", "session-management"])
        b = CheatsheetGroup.make_group_id(["session-management", "authentication"])
        self.assertEqual(a, b)

    def test_different_labels_different_id(self):
        a = CheatsheetGroup.make_group_id(["authentication"])
        b = CheatsheetGroup.make_group_id(["cryptography"])
        self.assertNotEqual(a, b)

    def test_id_is_12_hex_chars(self):
        gid = CheatsheetGroup.make_group_id(["authentication"])
        self.assertEqual(len(gid), 12)
        self.assertTrue(all(c in "0123456789abcdef" for c in gid))


# ---------------------------------------------------------------------------
# 7. _validate_labels
# ---------------------------------------------------------------------------


class TestValidateLabels(unittest.TestCase):
    """_validate_labels must filter to taxonomy and deduplicate."""

    def test_valid_labels_pass_through(self):
        result = _validate_labels(["authentication", "cryptography"])
        self.assertEqual(result, ["authentication", "cryptography"])

    def test_invalid_labels_filtered(self):
        result = _validate_labels(["authentication", "not-a-real-label"])
        self.assertEqual(result, ["authentication"])

    def test_all_invalid_returns_empty(self):
        self.assertEqual(_validate_labels(["fake1", "fake2"]), [])

    def test_non_list_returns_empty(self):
        self.assertEqual(_validate_labels("authentication"), [])
        self.assertEqual(_validate_labels(None), [])
        self.assertEqual(_validate_labels(42), [])

    def test_duplicates_removed(self):
        result = _validate_labels(["authentication", "authentication", "cryptography"])
        self.assertEqual(len(result), 2)
        self.assertEqual(result, ["authentication", "cryptography"])

    def test_empty_list_returns_empty(self):
        self.assertEqual(_validate_labels([]), [])


# ---------------------------------------------------------------------------
# 8. _deterministic_categorize (direct unit tests)
# ---------------------------------------------------------------------------


class TestDeterministicCategorize(unittest.TestCase):
    """Direct tests of the internal keyword matcher."""

    def test_returns_list(self):
        """Function must always return a list."""
        r = _make_record("X", "Xa")
        self.assertIsInstance(_deterministic_categorize(r), list)

    def test_known_categories_three_plus(self):
        """Spot-check three categories to guard against regression."""
        cases = [
            (
                "Logging_Cheat_Sheet",
                "Logging Cheat Sheet",
                "logging-and-monitoring",
            ),
            (
                "XSS_Prevention",
                "XSS Prevention Cheat Sheet",
                "output-encoding",
            ),
            (
                "Docker_Security",
                "Docker Security Cheat Sheet",
                "container-security",
            ),
        ]
        for source_id, title, expected_label in cases:
            with self.subTest(source_id=source_id):
                r = _make_record(source_id, title)
                self.assertIn(expected_label, _deterministic_categorize(r))


if __name__ == "__main__":
    unittest.main()
