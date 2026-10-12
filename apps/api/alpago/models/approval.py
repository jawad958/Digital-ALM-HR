"""Approval engine data model — the reusable spine of the platform.

Three tables:
  - approval_chain_templates : config per request_type (JSON chain)
  - approval_requests        : one per thing-needing-approval (polymorphic subject)
  - approval_steps           : one per approver in a request's chain

Every HR module (hiring, offers, leaves, compensation, assets) submits here.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alpago.models.base import Auditable, Base, Timestamps, UUIDPK


class ApprovalRequestStatus(str, Enum):
    draft = "draft"
    pending = "pending"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"
    changes_requested = "changes_requested"
    cancelled = "cancelled"


class ApprovalStepStatus(str, Enum):
    pending = "pending"
    active = "active"
    approved = "approved"
    rejected = "rejected"
    changes_requested = "changes_requested"
    skipped = "skipped"
    delegated = "delegated"
    escalated = "escalated"


class ApprovalChainTemplate(Base, UUIDPK, Timestamps, Auditable):
    """Chain config for one request_type. Admin-editable in-app, no deploy needed.

    `steps` is a JSON list; each element:
      {
        "role": "<role_key>",
        "scope": "department"|"global"|"self",
        "sla_hours": 48,
        "optional": false
      }
    """

    __table_args__ = (UniqueConstraint("request_type", "active", name="uq_chain_type_active"),)

    request_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


if TYPE_CHECKING:
    pass


class ApprovalRequest(Base, UUIDPK, Timestamps, Auditable):
    """One request instance.

    `subject_type` + `subject_id` are a polymorphic pointer to the thing being
    approved (e.g. hiring_request/<uuid>, offer/<uuid>, leave/<uuid>).
    """

    request_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(60), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False, index=True)

    chain_template_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("approval_chain_templates.id"), nullable=False
    )
    submitter_user_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("users.id"), nullable=False, index=True
    )

    status: Mapped[ApprovalRequestStatus] = mapped_column(
        SAEnum(ApprovalRequestStatus, native_enum=False, length=20),
        default=ApprovalRequestStatus.pending,
        nullable=False,
        index=True,
    )
    current_step_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    """Carries subject-specific hints the engine should surface to approvers (e.g.
    department_id for scope resolution, salary amount for context in email)."""

    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["ApprovalStep"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="ApprovalStep.step_index",
        lazy="selectin",  # async sessions can't lazy-load on attribute access
    )


class ApprovalStep(Base, UUIDPK, Timestamps, Auditable):
    """One approver turn in a request's chain."""

    __table_args__ = (UniqueConstraint("approval_request_id", "step_index", name="uq_step_order"),)

    approval_request_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("approval_requests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_role: Mapped[str] = mapped_column(String(40), nullable=False)
    approver_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("users.id"), nullable=True
    )
    scope: Mapped[str] = mapped_column(String(40), default="global", nullable=False)
    sla_hours: Mapped[int] = mapped_column(Integer, default=48, nullable=False)

    status: Mapped[ApprovalStepStatus] = mapped_column(
        SAEnum(ApprovalStepStatus, native_enum=False, length=20),
        default=ApprovalStepStatus.pending,
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    delegated_to_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("users.id"), nullable=True
    )

    request: Mapped["ApprovalRequest"] = relationship(back_populates="steps")

    @property
    def overdue_at(self) -> datetime | None:
        if self.activated_at is None:
            return None
        from datetime import timedelta
        return self.activated_at + timedelta(hours=self.sla_hours)
