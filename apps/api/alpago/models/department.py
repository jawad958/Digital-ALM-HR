"""Departments — the org tree. Head office vs Contracting Division, etc."""

from uuid import UUID

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alpago.models.base import Auditable, Base, Timestamps, UUIDPK


class Department(Base, UUIDPK, Timestamps, Auditable):
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("departments.id"), nullable=True
    )
    head_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("users.id"), nullable=True
    )

    parent: Mapped["Department | None"] = relationship(remote_side="Department.id")
