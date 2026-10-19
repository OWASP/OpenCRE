"""Log every answer and record the asker's thumbs up/down.

Logging is best effort: a failure here must never break answering a question.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from cre_logging import get_logger

logger = get_logger(__name__)

RATINGS = ("up", "down")
MAX_QUESTION = 4000
MAX_ANSWER = 20000
MAX_COMMENT = 2000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _active_flags() -> str:
    from application.utils.comprehension import flags

    return ",".join(flags.active())


def log_answer(
    *,
    source: str,
    question: str,
    answer: Optional[str],
    citations: Optional[Sequence[str]] = None,
    channel: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> Optional[str]:
    """Store an answer and return its id (None when logging is off or fails)."""
    if (os.environ.get("ANSWER_LOG_ENABLED", "1") or "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return None
    from application import sqla
    from application.database import db

    try:
        row = db.AnswerLog(
            created_at=_utcnow(),
            source=source,
            question=(question or "")[:MAX_QUESTION],
            answer=(answer or "")[:MAX_ANSWER],
            citations=json.dumps(list(citations or [])),
            channel=channel,
            flags=_active_flags(),
            latency_ms=latency_ms,
        )
        sqla.session.add(row)
        sqla.session.commit()
        return str(row.id)
    except Exception:  # noqa: BLE001 -- never break answering
        sqla.session.rollback()
        logger.warning("answer log failed", exc_info=True)
        return None


def record_rating(
    answer_id: str, rating: str, comment: Optional[str] = None
) -> Dict[str, Any]:
    """Set (or change) the thumbs for a logged answer. Raises ValueError / KeyError."""
    from application import sqla
    from application.database import db

    rating = (rating or "").strip().lower()
    if rating not in RATINGS:
        raise ValueError(f"rating must be one of: {', '.join(RATINGS)}")
    if not answer_id or not isinstance(answer_id, str):
        raise ValueError("answer_id is required")
    row = sqla.session.get(db.AnswerLog, answer_id)
    if row is None:
        raise KeyError("unknown answer_id")
    row.rating = rating
    row.comment = (comment or "").strip()[:MAX_COMMENT] or None
    row.rated_at = _utcnow()
    sqla.session.commit()
    return {"answer_id": answer_id, "rating": rating}


def list_feedback(
    rating: Optional[str] = None, limit: int = 100
) -> List[Dict[str, Any]]:
    """Newest rated answers first, for review and for building eval sets."""
    from application import sqla
    from application.database import db

    query = sqla.session.query(db.AnswerLog).filter(db.AnswerLog.rating.isnot(None))
    if rating:
        query = query.filter(db.AnswerLog.rating == rating)
    rows = (
        query.order_by(db.AnswerLog.rated_at.desc())
        .limit(max(1, min(int(limit), 500)))
        .all()
    )
    return [
        {
            "id": r.id,
            "source": r.source,
            "question": r.question,
            "answer": r.answer,
            "citations": json.loads(r.citations or "[]"),
            "rating": r.rating,
            "comment": r.comment,
            "flags": r.flags,
            "latency_ms": r.latency_ms,
            "rated_at": r.rated_at.isoformat() if r.rated_at else None,
        }
        for r in rows
    ]


def attach_answer_id(
    result: Dict[str, Any],
    *,
    question: str,
    source: str,
    latency_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Log an ``ask`` result and put the id on it so the client can rate it."""
    answer_id = log_answer(
        source=source,
        question=question,
        answer=str(result.get("message") or ""),
        citations=result.get("citations") or [],
        channel=str(result.get("channel") or ""),
        latency_ms=latency_ms,
    )
    if answer_id:
        result["answer_id"] = answer_id
    return result
