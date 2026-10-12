"""Approvals API — the public surface of the engine."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alpago.api.deps import current_user, get_db
from alpago.core.exceptions import NotFound
from alpago.domain.approvals import (
    create_approval_request,
    decide_step,
    delegate_step,
)
from alpago.domain.approvals.service import DefaultStepResolver
from alpago.models.approval import ApprovalRequest, ApprovalStep, ApprovalStepStatus
from alpago.models.user import User
from alpago.schemas.approval import (
    ApprovalDecisionRequest,
    ApprovalRequestOut,
    CreateApprovalRequest,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("", response_model=ApprovalRequestOut, status_code=status.HTTP_201_CREATED)
async def create(
    body: CreateApprovalRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequest:
    req = await create_approval_request(
        db,
        DefaultStepResolver(),
        request_type=body.request_type,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        submitter_user_id=user.id,
        context=body.context,
    )
    # Eager-load steps so the response includes them
    await db.refresh(req, attribute_names=["steps"])
    return req


@router.get("", response_model=list[ApprovalRequestOut])
async def list_all(
    request_type: str | None = None,
    status_filter: str | None = None,
    _: User = Depends(current_user),  # noqa: ARG001 — authn only
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRequest]:
    """Every approval request, newest first.

    `/pending` is deliberately narrow (only steps awaiting *you*). This is the
    full pipeline view — without it, a request whose approver role has no user
    assigned would be invisible to everyone.
    """
    stmt = (
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.steps))
        .order_by(ApprovalRequest.created_at.desc())
    )
    if request_type:
        stmt = stmt.where(ApprovalRequest.request_type == request_type)
    if status_filter:
        stmt = stmt.where(ApprovalRequest.status == status_filter)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/pending", response_model=list[ApprovalRequestOut])
async def pending_for_me(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRequest]:
    stmt = (
        select(ApprovalRequest)
        .join(ApprovalStep)
        .where(
            ApprovalStep.approver_user_id == user.id,
            ApprovalStep.status == ApprovalStepStatus.active,
        )
        .options(selectinload(ApprovalRequest.steps))
        .distinct()
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get("/unassigned", response_model=list[ApprovalRequestOut])
async def unassigned(
    _: User = Depends(current_user),  # noqa: ARG001 — authn only
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRequest]:
    """Active steps with no approver resolved — i.e. nobody holds that role yet.

    These are the requests that would otherwise sit silently in limbo.
    """
    stmt = (
        select(ApprovalRequest)
        .join(ApprovalStep)
        .where(
            ApprovalStep.approver_user_id.is_(None),
            ApprovalStep.status == ApprovalStepStatus.active,
        )
        .options(selectinload(ApprovalRequest.steps))
        .distinct()
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get("/{request_id}", response_model=ApprovalRequestOut)
async def get_one(
    request_id: UUID,
    user: User = Depends(current_user),  # noqa: ARG001 — authn only
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequest:
    stmt = (
        select(ApprovalRequest)
        .where(ApprovalRequest.id == request_id)
        .options(selectinload(ApprovalRequest.steps))
    )
    req = (await db.execute(stmt)).scalar_one_or_none()
    if req is None:
        raise NotFound(f"approval request {request_id} not found")
    return req


@router.post("/steps/{step_id}/decide", response_model=ApprovalRequestOut)
async def decide(
    step_id: UUID,
    body: ApprovalDecisionRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequest:
    req = await decide_step(
        db,
        DefaultStepResolver(),
        step_id=step_id,
        decision=body.decision,
        actor_user_id=user.id,
        comment=body.comment,
    )
    await db.refresh(req, attribute_names=["steps"])
    return req


@router.post("/steps/{step_id}/delegate", response_model=ApprovalRequestOut)
async def delegate(
    step_id: UUID,
    to_user_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequest:
    step = await delegate_step(
        db,
        DefaultStepResolver(),
        step_id=step_id,
        to_user_id=to_user_id,
        actor_user_id=user.id,
    )
    return await get_one(step.approval_request_id, user=user, db=db)
