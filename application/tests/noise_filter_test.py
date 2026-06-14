"""
Unit tests for Noise Filter (GSoC Module B).

Tests cover:
- Regex-based stage 1 filtering
- Keyword matching fallback
- Batch processing
- Metrics tracking
- Error handling
"""

import unittest
from unittest.mock import MagicMock

from application.utils.noise_filter import (
    NoiseFilter,
    FilterReason,
)


class TestNoiseFilter(unittest.TestCase):
    """Test suite for NoiseFilter class."""

    def setUp(self):
        """Set up test fixtures."""
        self.filter = NoiseFilter()

    def test_regex_filters_lockfiles(self):
        """Test that lockfiles are filtered as noise."""
        noise_items = [
            "package-lock.json",
            "yarn.lock",
            "poetry.lock",
            "Gemfile.lock",
        ]

        for item in noise_items:
            is_noise, reason, pattern = self.filter.filter_stage_1_regex(item)
            self.assertTrue(is_noise, f"Failed to filter {item}")
            self.assertEqual(reason, FilterReason.LOCKFILE)

    def test_regex_filters_ci_config(self):
        """Test that CI configuration is filtered."""
        ci_items = [
            ".github/workflows/test.yml",
            ".gitlab-ci.yml",
            "Jenkinsfile",
            ".circleci/config.yml",
        ]

        for item in ci_items:
            is_noise, reason, pattern = self.filter.filter_stage_1_regex(item)
            self.assertTrue(is_noise, f"Failed to filter {item}")

    def test_regex_filters_linting(self):
        """Test that linting commits arefiltered."""
        linting_items = [
            "prettier: format code",
            "eslint: fix errors",
            "black formatting",
            "Bump lodash from 4.17.19 to 4.17.21",
            "chore: whitespace fix",
        ]

        for item in linting_items:
            is_noise, _, _ = self.filter.filter_stage_1_regex(item)
            self.assertTrue(is_noise, f"Failed to filter linting: {item}")

    def test_security_content_not_filtered_regex(self):
        """Test that security content passes regex stage."""
        security_items = [
            "ASVS-1.2.3: Authentication requirements",
            "Fix SQL injection vulnerability in query builder",
            "Add encryption to sensitive data storage",
            "Implement CSRF token validation",
        ]

        for item in security_items:
            is_noise, _, _ = self.filter.filter_stage_1_regex(item)
            self.assertFalse(
                is_noise, f"Incorrectly filtered security content: {item}"
            )

    def test_has_security_keywords(self):
        """Test security keyword detection."""
        security_content = [
            "vulnerability in authentication",
            "CVE-2021-12345 SQL injection",
            "OWASP Top 10: XSS attacks",
            "cryptographic signing implementation",
        ]

        for content in security_content:
            has_keywords = self.filter._has_security_keywords(content)
            self.assertTrue(
                has_keywords, f"Failed to detect keywords in: {content}"
            )

    def test_full_filter_pipeline(self):
        """Test full two-stage filtering."""
        # Noise content
        is_valid, metadata = self.filter.filter("package-lock.json")
        self.assertFalse(is_valid)
        self.assertEqual(metadata["stage"], 1)

        # Security content (uses keyword fallback)
        is_valid, metadata = self.filter.filter(
            "ASVS 2.1.3: Verify encrypted password"
        )
        self.assertTrue(is_valid)
        self.assertEqual(metadata["stage"], 2)

    def test_batch_filtering(self):
        """Test batch processing."""
        contents = [
            "package-lock.json",
            "Fix SQL injection",
            "yarn.lock",
            "Implement OAuth 2.0",
            "Format with prettier",
        ]

        results = self.filter.filter_batch(contents)

        self.assertEqual(len(results), 5)
        # Check pattern: noise, valid, noise, valid, noise
        self.assertFalse(results[0][1])  # lockfile
        self.assertTrue(results[1][1])   # security
        self.assertFalse(results[2][1])  # lockfile
        self.assertTrue(results[3][1])   # security
        self.assertFalse(results[4][1])  # linting

    def test_confidence_thresholding(self):
        """Test confidence score thresholding."""
        filter_high = NoiseFilter(confidence_threshold=0.9)
        filter_low = NoiseFilter(confidence_threshold=0.3)

        # With high threshold, more content is filtered
        is_valid_high, _ = filter_high.filter("security question")
        is_valid_low, _ = filter_low.filter("security question")

        # Low threshold should be more permissive
        self.assertLessEqual(is_valid_high, is_valid_low)

    def test_llm_client_integration(self):
        """Test LLM client integration."""
        mock_llm = MagicMock()
        mock_llm.evaluate_relevance.return_value = {
            "is_security_knowledge": True,
            "confidence": 0.95,
            "reasoning": "Discusses ASVS requirements",
        }

        filter_with_llm = NoiseFilter(llm_client=mock_llm)
        is_valid, metadata = filter_with_llm.filter("Some ASVS content")

        self.assertTrue(is_valid)
        self.assertEqual(metadata["confidence"], 0.95)

    def test_llm_client_error_handling(self):
        """Test fallback when LLM fails."""
        mock_llm = MagicMock()
        mock_llm.evaluate_relevance.side_effect = Exception("API Error")

        filter_with_llm = NoiseFilter(llm_client=mock_llm)
        is_valid, metadata = filter_with_llm.filter(
            "OWASP security testing"
        )

        # Should fall back to keyword matching
        self.assertIn("fallback", metadata["reasoning"].lower())

    def test_metrics_tracking(self):
        """Test that metrics are tracked correctly."""
        self.filter.filter("package-lock.json")  # Regex filtered
        self.filter.filter("ASVS requirement")    # Approved
        self.filter.filter("Prettier formatting")  # Regex filtered

        metrics = self.filter.get_metrics()

        self.assertEqual(metrics["total_processed"], 3)
        self.assertEqual(metrics["filtered_regex"], 2)
        self.assertEqual(metrics["approved"], 1)

    def test_approval_rate_calculation(self):
        """Test approval rate metrics."""
        contents = [
            "ASVS",
            "CVE",
            "Threat",
            "package-lock.json",
            "yarn.lock",
        ]

        for content in contents:
            self.filter.filter(content)

        metrics = self.filter.get_metrics()

        # Should have calculated rates
        self.assertIn("approval_rate", metrics)
        self.assertGreater(metrics["approval_rate"], 0)
        self.assertLess(metrics["approval_rate"], 100)


if __name__ == "__main__":
    unittest.main()
