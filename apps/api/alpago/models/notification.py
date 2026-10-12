"""Every notification sent — in-app, email, WhatsApp.

One row per channel per delivery attempt. The notification service writes
`pending` then a Celery task flips to `sent`/`failed` with the provider id.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum as SAEnum
from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from alpago.models.base import Base, Timestamps, UUIDPK


class NotificationChannel(str, Enum):
    in_app = "in_app"
    email = "email"
    whatsapp = "whatsapp"


class NotificationStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    delivered = "delivered"
    read = "read"


class Notification(Base, UUIDPK, Timestamps):
    user_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(NotificationChannel, native_enum=False, length=20), nullable=False
    )
    template: Mapped[str] = mapped_column(String(60), nullable=False)
    """e.g. 'approval_pending', 'offer_sent', 'document_expiring'"""

    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        SAEnum(NotificationStatus, native_enum=False, length=20),
        default=NotificationStatus.pending,
        nullable=False,
        index=True,
    )
    provider_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
