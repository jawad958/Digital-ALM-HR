"""Audit log — every write operation. The compliance record.

Call `audit(session, actor, action, subject, before=..., after=...)` from any
service that changes data. Reads are not audited.
"""

from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from alpago.models.base import Base, Timestamps, UUIDPK


class AuditLog(Base, UUIDPK, Timestamps):
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    """verb_noun, e.g. approval_decided, hiring_request_submitted"""

    subject_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    subject_id: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True, index=True)

    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
