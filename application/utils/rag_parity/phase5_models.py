"""SQLAlchemy model for knowledge_claim (additive; not wired into graph writes)."""

from __future__ import annotations

import uuid

import sqlalchemy as sqla
from sqlalchemy.dialects import postgresql

from application.database.db import BaseModel


def _uuid() -> str:
    return str(uuid.uuid4())


class KnowledgeClaim(BaseModel):  # type: ignore
    __tablename__ = "knowledge_claim"

    id = sqla.Column(sqla.String, primary_key=True, default=_uuid)
    claim = sqla.Column(sqla.Text, nullable=False)
    quote = sqla.Column(sqla.Text, nullable=False)
    confidence = sqla.Column(sqla.Float, nullable=False, default=0.0)
    source_ref = sqla.Column(sqla.String, nullable=True)
    status = sqla.Column(sqla.String, nullable=False, default="pending_review")
    metadata_json = sqla.Column(
        "metadata_json",
        sqla.JSON().with_variant(postgresql.JSONB(), "postgresql"),
        nullable=True,
    )
    created_at = sqla.Column(
        sqla.DateTime, nullable=False, server_default=sqla.func.now()
    )
    reviewed_at = sqla.Column(sqla.DateTime, nullable=True)
