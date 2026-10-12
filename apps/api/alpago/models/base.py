"""Declarative Base + mixins every table uses.

Dialect-neutral: uses SQLAlchemy's generic Uuid type (native UUID on Postgres,
CHAR(32) on SQLite) and generic JSON (JSONB on Postgres, JSON TEXT on SQLite).

Every row carries:
  - id (uuid4)
  - created_at, updated_at (UTC)
  - created_by, updated_by (user_id, nullable for system actions)
  - deleted_at (nullable; set on soft delete)
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Project base for every SQLAlchemy model."""

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805
        # CamelCase -> snake_case plural: User -> users, ApprovalStep -> approval_steps
        import re
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        return name if name.endswith("s") else name + "s"


class UUIDPK:
    """UUID primary key — dialect-neutral."""

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Auditable:
    """Who created/updated. Nullable — system actions and migrations have no actor."""

    @declared_attr
    def created_by(cls) -> Mapped[UUID | None]:  # noqa: N805
        return mapped_column(Uuid(), ForeignKey("users.id"), nullable=True)

    @declared_attr
    def updated_by(cls) -> Mapped[UUID | None]:  # noqa: N805
        return mapped_column(Uuid(), ForeignKey("users.id"), nullable=True)
