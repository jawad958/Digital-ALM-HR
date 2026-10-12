"""The approval workflow engine.

Build it correctly once. Every HR module submits here.

State machine (ApprovalRequest.status):

    draft ──submit──► pending ──activate──► in_review ──┬── all steps approved ─► approved (final)
                                                        ├── a step rejected ───► rejected (final)
                                                        └── a step requests changes ─► changes_requested
                                                                                        │
                                                                                        └─ resubmit ─► pending

State machine (ApprovalStep.status):

    pending ──activated─► active ──┬─ approve ────────► approved
                                   ├─ reject ─────────► rejected
                                   ├─ request_changes ► changes_requested
                                   └─ delegate ──────► delegated (new step inserted)

A step is `active` only when it is the current step of a request in state in_review.
Any decision on a non-active step raises ApprovalChainError.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alpago.core.exceptions import ApprovalChainError, NotFound
from alpago.models.approval import (
    ApprovalChainTemplate,
    ApprovalRequest,
    ApprovalRequestStatus,
    ApprovalStep,
    ApprovalStepStatus,
)
from alpago.models.audit import AuditLog


class ApprovalDecision(str, Enum):
    approve = "approve"
    reject = "reject"
    request_changes = "request_changes"


# ───────────────────────────────────────────────────────────────────────────────
# Resolver — maps a role+scope to a specific user to notify / assign the step to.
# Hiring: AGM of the submitter's department, GM is global, CEO is global, etc.
# Injectable so tests can use a fake resolver.
# ───────────────────────────────────────────────────────────────────────────────

class StepResolver(Protocol):
    async def resolve(
        self, *, role: str, scope: str, context: dict, session: AsyncSession
    ) -> UUID | None:
        """Return the user_id this role+scope resolves to, or None if unresolved."""


# ───────────────────────────────────────────────────────────────────────────────
# Engine operations (callable from services / routers / workers)
# ───────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ApprovalEngine:
    """Low-level engine. Prefer the module-level functions below in regular code."""

    session: AsyncSession
    resolver: StepResolver

    async def create(
        self,
        *,
        request_type: str,
        subject_type: str,
        subject_id: UUID,
        submitter_user_id: UUID,
        context: dict | None = None,
    ) -> ApprovalRequest:
        template = await self._active_template(request_type)
        req = ApprovalRequest(
            request_type=request_type,
            subject_type=subject_type,
            subject_id=subject_id,
            submitter_user_id=submitter_user_id,
            chain_template_id=template.id,
            status=ApprovalRequestStatus.pending,
            current_step_index=0,
            context=context or {},
            created_by=submitter_user_id,
            updated_by=submitter_user_id,
        )

        for i, step_cfg in enumerate(template.steps):
            req.steps.append(
                ApprovalStep(
                    step_index=i,
                    approver_role=step_cfg["role"],
                    scope=step_cfg.get("scope", "global"),
                    sla_hours=int(step_cfg.get("sla_hours", 48)),
                    status=ApprovalStepStatus.pending,
                    created_by=submitter_user_id,
                    updated_by=submitter_user_id,
                )
            )

        self.session.add(req)
        await self.session.flush()

        await self._activate_step(req, 0)
        await self.session.flush()
        self._audit("approval_request_created", submitter_user_id, req, after={"status": req.status.value})
        return req

    async def decide(
        self,
        *,
        step_id: UUID,
        decision: ApprovalDecision,
        actor_user_id: UUID,
        comment: str | None = None,
    ) -> ApprovalRequest:
        step = await self.session.get(ApprovalStep, step_id)
        if step is None:
            raise NotFound(f"approval step {step_id} not found")
        if step.status != ApprovalStepStatus.active:
            raise ApprovalChainError(
                f"step {step_id} is {step.status.value}, cannot decide"
            )
        req = await self.session.get(ApprovalRequest, step.approval_request_id)
        assert req is not None  # step FK guarantees it

        # Record the decision
        step.decided_at = datetime.now(tz=timezone.utc)
        step.comment = comment
        step.updated_by = actor_user_id

        if decision == ApprovalDecision.approve:
            step.status = ApprovalStepStatus.approved
            next_i = step.step_index + 1
            if next_i < len(req.steps):
                await self._activate_step(req, next_i)
                req.status = ApprovalRequestStatus.in_review
            else:
                req.status = ApprovalRequestStatus.approved
                req.decided_at = datetime.now(tz=timezone.utc)

        elif decision == ApprovalDecision.reject:
            step.status = ApprovalStepStatus.rejected
            req.status = ApprovalRequestStatus.rejected
            req.decided_at = datetime.now(tz=timezone.utc)
            # Remaining steps are skipped
            for s in req.steps[step.step_index + 1 :]:
                s.status = ApprovalStepStatus.skipped

        elif decision == ApprovalDecision.request_changes:
            step.status = ApprovalStepStatus.changes_requested
            req.status = ApprovalRequestStatus.changes_requested
            # Remaining steps are reset to pending; resubmit re-activates step 0
            for s in req.steps[step.step_index + 1 :]:
                s.status = ApprovalStepStatus.pending

        req.updated_by = actor_user_id
        await self.session.flush()
        self._audit(
            "approval_step_decided",
            actor_user_id,
            req,
            after={"decision": decision.value, "step_index": step.step_index, "status": req.status.value},
        )
        return req

    async def resubmit(self, *, request_id: UUID, actor_user_id: UUID) -> ApprovalRequest:
        req = await self.session.get(ApprovalRequest, request_id)
        if req is None:
            raise NotFound("approval request not found")
        if req.status != ApprovalRequestStatus.changes_requested:
            raise ApprovalChainError(
                f"request is {req.status.value}, cannot resubmit"
            )
        for s in req.steps:
            s.status = ApprovalStepStatus.pending
            s.decided_at = None
            s.activated_at = None
            s.comment = None
        req.current_step_index = 0
        req.status = ApprovalRequestStatus.pending
        req.updated_by = actor_user_id
        await self.session.flush()
        await self._activate_step(req, 0)
        await self.session.flush()
        self._audit("approval_request_resubmitted", actor_user_id, req)
        return req

    async def delegate(
        self, *, step_id: UUID, to_user_id: UUID, actor_user_id: UUID
    ) -> ApprovalStep:
        step = await self.session.get(ApprovalStep, step_id)
        if step is None:
            raise NotFound("step not found")
        if step.status != ApprovalStepStatus.active:
            raise ApprovalChainError("can only delegate the active step")
        step.delegated_to_user_id = to_user_id
        step.approver_user_id = to_user_id
        step.updated_by = actor_user_id
        await self.session.flush()
        self._audit(
            "approval_step_delegated",
            actor_user_id,
            await self.session.get(ApprovalRequest, step.approval_request_id),
            after={"to_user_id": str(to_user_id), "step_index": step.step_index},
        )
        return step

    async def escalate(self, *, step_id: UUID, actor_user_id: UUID | None = None) -> ApprovalStep:
        """Mark a step as escalated. Called by the Celery beat SLA checker."""
        step = await self.session.get(ApprovalStep, step_id)
        if step is None:
            raise NotFound("step not found")
        if step.status != ApprovalStepStatus.active:
            raise ApprovalChainError("only active steps can be escalated")
        step.status = ApprovalStepStatus.escalated
        step.updated_by = actor_user_id
        await self.session.flush()
        return step

    # ── internals ────────────────────────────────────────────────────────────

    async def _active_template(self, request_type: str) -> ApprovalChainTemplate:
        stmt = select(ApprovalChainTemplate).where(
            ApprovalChainTemplate.request_type == request_type,
            ApprovalChainTemplate.active.is_(True),
        )
        template = (await self.session.execute(stmt)).scalar_one_or_none()
        if template is None:
            raise ApprovalChainError(f"no active approval chain for request_type={request_type}")
        if not template.steps:
            raise ApprovalChainError(f"chain for {request_type} has no steps")
        return template

    async def _activate_step(self, req: ApprovalRequest, index: int) -> None:
        step = req.steps[index]
        step.status = ApprovalStepStatus.active
        step.activated_at = datetime.now(tz=timezone.utc)
        resolved = await self.resolver.resolve(
            role=step.approver_role, scope=step.scope, context=req.context, session=self.session
        )
        step.approver_user_id = resolved
        req.current_step_index = index
        req.status = (
            ApprovalRequestStatus.pending if index == 0 else ApprovalRequestStatus.in_review
        )

    def _audit(
        self,
        action: str,
        actor: UUID | None,
        req: ApprovalRequest | None,
        *,
        after: dict | None = None,
    ) -> None:
        if req is None:
            return
        self.session.add(
            AuditLog(
                actor_user_id=actor,
                action=action,
                subject_type="approval_request",
                subject_id=req.id,
                after=after,
                context={"request_type": req.request_type},
            )
        )


# ───────────────────────────────────────────────────────────────────────────────
# Thin module-level helpers (what callers mostly use)
# ───────────────────────────────────────────────────────────────────────────────

async def create_approval_request(
    session: AsyncSession,
    resolver: StepResolver,
    *,
    request_type: str,
    subject_type: str,
    subject_id: UUID,
    submitter_user_id: UUID,
    context: dict | None = None,
) -> ApprovalRequest:
    return await ApprovalEngine(session, resolver).create(
        request_type=request_type,
        subject_type=subject_type,
        subject_id=subject_id,
        submitter_user_id=submitter_user_id,
        context=context,
    )


async def decide_step(
    session: AsyncSession,
    resolver: StepResolver,
    *,
    step_id: UUID,
    decision: ApprovalDecision,
    actor_user_id: UUID,
    comment: str | None = None,
) -> ApprovalRequest:
    return await ApprovalEngine(session, resolver).decide(
        step_id=step_id,
        decision=decision,
        actor_user_id=actor_user_id,
        comment=comment,
    )


async def delegate_step(
    session: AsyncSession,
    resolver: StepResolver,
    *,
    step_id: UUID,
    to_user_id: UUID,
    actor_user_id: UUID,
) -> ApprovalStep:
    return await ApprovalEngine(session, resolver).delegate(
        step_id=step_id, to_user_id=to_user_id, actor_user_id=actor_user_id
    )


async def escalate_overdue(session: AsyncSession, resolver: StepResolver) -> int:
    """Called by Celery beat hourly. Returns number of steps escalated."""
    now = datetime.now(tz=timezone.utc)
    stmt = select(ApprovalStep).where(ApprovalStep.status == ApprovalStepStatus.active)
    rows = (await session.execute(stmt)).scalars().all()
    engine = ApprovalEngine(session, resolver)
    escalated = 0
    for step in rows:
        if step.overdue_at and step.overdue_at < now:
            await engine.escalate(step_id=step.id)
            escalated += 1
    return escalated
