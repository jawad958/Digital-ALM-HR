"""Activity / audit trail — read-only view over the AuditLog table.

  GET /activity                               latest across the system
  GET /activity?subject_type=&subject_id=     trail for one record
  GET /activity?actor_user_id=                what one person did
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alpago.api.deps import current_user, get_db
from alpago.models.audit import AuditLog
from alpago.models.user import User


router = APIRouter(prefix="/activity", tags=["activity"])


# Human-readable labels for the dotted action codes.
ACTION_LABELS: dict[str, str] = {
    "hiring_request.created": "raised a hiring request",
    "hiring_request.updated": "updated the hiring request",
    "hiring_request.jd_generated": "generated a job description",
    "candidate.created": "added a candidate",
    "candidate.stage_changed": "moved the candidate stage",
    "candidate.screened": "ran AI screening",
    "cv.uploaded": "uploaded a CV",
    "interview.scheduled": "scheduled an interview",
    "interview.evaluated": "submitted an interview evaluation",
    "offer.created": "drafted an offer",
    "offer.sent": "sent the offer",
    "offer.accepted": "offer accepted",
    "offer.declined": "offer declined",
    "approval.requested": "submitted for approval",
    "approval.approved": "approved",
    "approval.rejected": "rejected",
    "approval.changes_requested": "requested changes",
    "approval.delegated": "delegated the approval",
    "approval.escalated": "escalated past SLA",
    # The approval engine emits underscore-style names
    "approval_request_created": "submitted for approval",
    "approval_request_resubmitted": "resubmitted for approval",
    "approval_step_decided": "made an approval decision",
    "approval_step_delegated": "delegated the approval",
    "approval_step_escalated": "escalated past SLA",
    "document.uploaded": "uploaded a document",
    "document.verified": "verified a document",
    "document.rejected": "rejected a document",
    "document.deleted": "removed a document",
    "employee.created": "created an employee record",
    "employee.created_from_offer": "converted the offer into an employee",
    "employee.updated": "updated the employee profile",
    "employee.status_changed": "changed employment status",
    "onboarding_task.added": "added an onboarding task",
    "onboarding_task.completed": "completed an onboarding task",
    "onboarding_task.reopened": "reopened an onboarding task",
    "user.logged_in": "signed in",
}


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    action: str
    action_label: str = ""
    subject_type: str
    subject_id: UUID | None
    actor_user_id: UUID | None
    actor_name: str | None = None
    before: dict | None
    after: dict | None
    context: dict
    created_at: datetime


@router.get("", response_model=list[ActivityOut])
async def list_activity(
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    action: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityOut]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if subject_type:
        stmt = stmt.where(AuditLog.subject_type == subject_type)
    if subject_id:
        stmt = stmt.where(AuditLog.subject_id == subject_id)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)

    rows = list((await db.execute(stmt)).scalars().all())

    # Resolve actor names in one extra query rather than N
    actor_ids = {r.actor_user_id for r in rows if r.actor_user_id}
    names: dict[UUID, str] = {}
    if actor_ids:
        users = (
            await db.execute(select(User).where(User.id.in_(actor_ids)))
        ).scalars().all()
        names = {u.id: (u.name or u.email) for u in users}

    out = []
    for r in rows:
        item = ActivityOut.model_validate(r)
        label = ACTION_LABELS.get(r.action, r.action.replace(".", " ").replace("_", " "))

        # An approval step carries the actual verdict in `after.decision` —
        # surface it so the feed reads "Rania approved" not "made a decision".
        decision = (r.after or {}).get("decision") if isinstance(r.after, dict) else None
        if r.action == "approval_step_decided" and decision:
            label = {
                "approve": "approved this step",
                "reject": "rejected this step",
                "request_changes": "requested changes",
            }.get(str(decision), label)

        item.action_label = label
        item.actor_name = names.get(r.actor_user_id) if r.actor_user_id else "System"
        out.append(item)
    return out
