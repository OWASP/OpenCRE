"""
Unit tests for HITL Review Queue and API endpoints.

Tests cover:
- Queue management
- Review logging
- JSONL persistence
- API endpoints
- Error handling
"""

import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from application.utils.review_queue import ReviewQueue


class TestReviewQueue(unittest.TestCase):
    """Test suite for ReviewQueue class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.queue = ReviewQueue(log_dir=self.temp_dir)

    def tearDown(self):
        """Clean up test files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_to_queue(self):
        """Test adding content to queue."""
        result = self.queue.add_to_queue(
            "test1", "Sample content", "OWASP/ASVS"
        )
        self.assertTrue(result)
        self.assertEqual(len(self.queue.queue), 1)
        self.assertEqual(self.queue.stats["pending"], 1)

    def test_add_multiple_items(self):
        """Test adding multiple items."""
        self.queue.add_to_queue("test1", "Content 1", "OWASP/ASVS")
        self.queue.add_to_queue("test2", "Content 2", "OWASP/wstg")
        self.queue.add_to_queue("test3", "Content 3", "OWASP/API")

        self.assertEqual(len(self.queue.queue), 3)
        self.assertEqual(self.queue.stats["pending"], 3)

    def test_submit_review_approved(self):
        """Test submitting approved review."""
        self.queue.add_to_queue("test1", "Test content", "OWASP/ASVS")

        success, error = self.queue.submit_review("test1", "approved")

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(self.queue.stats["approved"], 1)
        self.assertEqual(self.queue.stats["pending"], 0)

    def test_submit_review_rejected(self):
        """Test submitting rejected review."""
        self.queue.add_to_queue("test1", "Noise content", "OWASP/ASVS")

        success, error = self.queue.submit_review("test1", "rejected")

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(self.queue.stats["rejected"], 1)
        self.assertEqual(self.queue.stats["pending"], 0)
        self.assertEqual(self.queue.stats["total_reviewed"], 1)

    def test_submit_review_invalid_decision(self):
        """Test submitting with invalid decision."""
        self.queue.add_to_queue("test1", "Content", "OWASP/ASVS")

        success, error = self.queue.submit_review("test1", "invalid")

        self.assertFalse(success)
        self.assertIsNotNone(error)
        self.assertIn("Invalid decision", error)

    def test_submit_review_not_found(self):
        """Test submitting review for nonexistent content."""
        success, error = self.queue.submit_review("nonexistent", "approved")

        self.assertFalse(success)
        self.assertIsNotNone(error)
        self.assertIn("not found", error)

    def test_submit_review_already_reviewed(self):
        """Test submitting review for already reviewed content."""
        self.queue.add_to_queue("test1", "Content", "OWASP/ASVS")
        self.queue.submit_review("test1", "approved")

        # Try to review again
        success, error = self.queue.submit_review("test1", "rejected")

        self.assertFalse(success)
        self.assertIsNotNone(error)

    def test_review_logging(self):
        """Test that reviews are logged to JSONL."""
        self.queue.add_to_queue("test1", "Content to review", "OWASP/ASVS")
        self.queue.submit_review("test1", "approved", "Good content")

        # Check log file exists
        log_files = list(Path(self.temp_dir).glob("reviews_*.jsonl"))
        self.assertEqual(len(log_files), 1)

        # Verify log content
        with open(log_files[0], "r") as f:
            log_line = f.readline()
            log_data = json.loads(log_line)
            self.assertEqual(log_data["id"], "test1")
            self.assertEqual(log_data["decision"], "approved")
            self.assertEqual(log_data["notes"], "Good content")

    def test_get_pending_items(self):
        """Test retrieving pending items."""
        self.queue.add_to_queue("test1", "Content 1", "OWASP/ASVS")
        self.queue.add_to_queue("test2", "Content 2", "OWASP/wstg")
        self.queue.submit_review("test1", "approved")

        pending = self.queue.get_pending_items()

        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], "test2")

    def test_get_pending_items_limit(self):
        """Test limit parameter for pending items."""
        for i in range(15):
            self.queue.add_to_queue(f"test{i}", f"Content {i}", "OWASP/ASVS")

        pending = self.queue.get_pending_items(limit=5)

        self.assertEqual(len(pending), 5)

    def test_get_queue_stats(self):
        """Test getting queue statistics."""
        self.queue.add_to_queue("test1", "Content 1", "OWASP/ASVS")
        self.queue.add_to_queue("test2", "Content 2", "OWASP/wstg")
        self.queue.submit_review("test1", "approved")

        stats = self.queue.get_queue_stats()

        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["approved"], 1)
        self.assertEqual(stats["rejected"], 0)
        self.assertEqual(stats["total_reviewed"], 1)

    def test_get_review_history(self):
        """Test retrieving review history."""
        self.queue.add_to_queue("test1", "Content 1", "OWASP/ASVS")
        self.queue.add_to_queue("test2", "Content 2", "OWASP/wstg")
        self.queue.submit_review("test1", "approved")
        self.queue.submit_review("test2", "rejected")

        history = self.queue.get_review_history()

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["id"], "test2")  # Most recent first


if __name__ == "__main__":
    unittest.main()
