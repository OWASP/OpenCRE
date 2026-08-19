"""
GSoC Module D: HITL Review API Endpoints

REST API for human-in-the-loop review interface.
Optimized for keyboard shortcuts and fast review workflow.
"""

from flask import Blueprint, request, jsonify
from application.utils.review_queue import ReviewQueue

review_bp = Blueprint("review", __name__, url_prefix="/api/review")
review_queue = ReviewQueue()


@review_bp.route("/queue/pending", methods=["GET"])
def get_pending_queue():
    """
    Get pending content from review queue.

    Query params:
        limit: Maximum number of items (default: 10)

    Returns:
        JSON list of pending items
    """
    try:
        limit = request.args.get("limit", default=10, type=int)
        pending = review_queue.get_pending_items(limit)
        return jsonify({"success": True, "items": pending}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@review_bp.route("/submit", methods=["POST"])
def submit_review():
    """
    Submit a review decision.

    JSON Body:
        {
            "content_id": "abc123",
            "decision": "approved|rejected",
            "notes": "optional notes"
        }

    Returns:
        JSON {"success": true/false, "message": "..."}
    """
    try:
        data = request.get_json()

        content_id = data.get("content_id")
        decision = data.get("decision")
        notes = data.get("notes", "")

        if not content_id or not decision:
            return (
                jsonify({
                    "success": False,
                    "error": "Missing content_id or decision"
                }),
                400,
            )

        success, error = review_queue.submit_review(
            content_id, decision, notes
        )

        if success:
            return (
                jsonify({
                    "success": True,
                    "message": f"Content {decision}: {content_id}"
                }),
                200,
            )
        else:
            return (
                jsonify({"success": False, "error": error}),
                400,
            )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@review_bp.route("/stats", methods=["GET"])
def get_stats():
    """
    Get review queue statistics.

    Returns:
        JSON with stats: {total_reviewed, approved, rejected, pending}
    """
    try:
        stats = review_queue.get_queue_stats()
        return jsonify({"success": True, "stats": stats}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@review_bp.route("/history", methods=["GET"])
def get_history():
    """
    Get review history from JSONL logs.

    Query params:
        limit: Maximum number of records (default: 100)

    Returns:
        JSON list of reviewed items
    """
    try:
        limit = request.args.get("limit", default=100, type=int)
        history = review_queue.get_review_history(limit)
        return jsonify({"success": True, "history": history}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
