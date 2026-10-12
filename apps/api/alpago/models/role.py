"""Roles & role assignments.

Roles are the ten names from the auth-authorization spec:
  admin, hr_lead, ta, pro, initiating_manager, agm, gm, ceo, it, employee.

Each user has one or more roles via `user_roles`. A role may be scoped to a
department or scope-key via the JSON `scope` field (e.g. an AGM scoped to the
Contracting Division only).
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alpago.models.base import Auditable, Base, Timestamps, UUIDPK

if TYPE_CHECKING:
    from alpago.models.user import User


# Canonical role identifiers — add to this list rather than coining ad-hoc strings
ROLE_KEYS = {
    "admin",
    "hr_lead",
    "ta",
    "pro",
    "initiating_manager",
    "agm",
    "gm",
    "ceo",
    "it",
    "employee",
}


class Role(Base, UUIDPK, Timestamps):
    key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    permissions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UserRole(Base, UUIDPK, Timestamps, Auditable):
    __table_args__ = (UniqueConstraint("user_id", "role_id", "scope_key", name="uq_user_role_scope"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("roles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scope_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped["User"] = relationship(back_populates="user_roles", foreign_keys=[user_id])
    role: Mapped["Role"] = relationship()
