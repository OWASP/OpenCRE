"""
GSoC Module D: Human-in-the-Loop (HITL) Review Backend

Provides REST API endpoints for content review with JSONL logging.
Designed for fast keyboard-optimized review workflow (<3 seconds per item).

Features:
- Review queue management
- JSONL-based logging (S3/MinIO ready)
- User authentication placeholder
- Statistics dashboard data
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class ReviewQueue:
    """Manages content review queue and logging."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

    def __init__(self, log_dir: str = "review_logs"):
        """
        Initialize review queue.

        Args:
            log_dir: Directory to store JSONL logs
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.queue: List[Dict] = []
        self.stats = {
            "total_reviewed": 0,
            "approved": 0,
            "rejected": 0,
            "pending": 0,
        }

    def add_to_queue(self, content_id: str, content: str, source: str) -> bool:
        """
        Add content to review queue.

        Args:
            content_id: Unique identifier for the content
            content: The content to review
            source: Source of the content (repo name, URL, etc.)

        Returns:
            True if added successfully
        """
        try:
            item = {
                "id": content_id,
                "content": content,
                "source": source,
                "status": self.PENDING,
                "created_at": datetime.utcnow().isoformat(),
                "reviewed_at": None,
                "decision": None,
            }
            self.queue.append(item)
            self.stats["pending"] += 1
            logger.info(f"Added content {content_id} to review queue")
            return True
        except Exception as e:
            logger.error(f"Error adding to queue: {e}")
            return False

    def submit_review(
        self, content_id: str, decision: str, notes: str = ""
    ) -> Tuple[bool, Optional[str]]:
        """
        Submit review decision for content.

        Args:
            content_id: ID of content being reviewed
            decision: "approved" or "rejected"
            notes: Optional reviewer notes

        Returns:
            Tuple of (success, error_message)
        """
        if decision not in [self.APPROVED, self.REJECTED]:
            return False, "Invalid decision (must be 'approved' or 'rejected')"

        try:
            # Find content in queue
            content_item = None
            for item in self.queue:
                if item["id"] == content_id:
                    content_item = item
                    break

            if not content_item:
                return False, f"Content {content_id} not found"

            if content_item["status"] != self.PENDING:
                return False, f"Content already reviewed: {content_item['status']}"

            # Update status
            content_item["status"] = decision
            content_item["decision"] = decision
            content_item["reviewed_at"] = datetime.utcnow().isoformat()
            content_item["notes"] = notes

            # Log to JSONL
            self._log_review(content_item)

            # Update stats
            self.stats["pending"] -= 1
            if decision == self.APPROVED:
                self.stats["approved"] += 1
            else:
                self.stats["rejected"] += 1
            self.stats["total_reviewed"] += 1

            logger.info(
                f"Review submitted for {content_id}: {decision}"
            )
            return True, None

        except Exception as e:
            logger.error(f"Error submitting review: {e}")
            return False, str(e)

    def _log_review(self, item: Dict) -> bool:
        """
        Log review decision to JSONL file.

        Args:
            item: Review item with decision

        Returns:
            True if logged successfully
        """
        try:
            log_file = (
                self.log_dir /
                f"reviews_{datetime.utcnow().strftime('%Y%m%d')}.jsonl"
            )

            with open(log_file, "a") as f:
                f.write(json.dumps(item) + "\n")

            logger.debug(f"Review logged to {log_file}")
            return True

        except Exception as e:
            logger.error(f"Error logging review: {e}")
            return False

    def get_queue_stats(self) -> Dict:
        """Get review queue statistics."""
        return self.stats.copy()

    def get_pending_items(self, limit: int = 10) -> List[Dict]:
        """
        Get pending items from queue.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of pending review items
        """
        pending = [
            {
                "id": item["id"],
                "content": item["content"],
                "source": item["source"],
                "created_at": item["created_at"],
            }
            for item in self.queue
            if item["status"] == self.PENDING
        ]
        return pending[:limit]

    def get_review_history(self, limit: int = 100) -> List[Dict]:
        """Get review history from JSONL logs."""
        history = []
        try:
            for log_file in self.log_dir.glob("reviews_*.jsonl"):
                with open(log_file, "r") as f:
                    for line in f:
                        try:
                            history.append(json.loads(line))
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in {log_file}")
        except Exception as e:
            logger.error(f"Error reading review history: {e}")

        return sorted(
            history,
            key=lambda x: x.get("reviewed_at", x.get("created_at", "")),
            reverse=True,
        )[:limit]
