"""Behaviour contract for the approval engine.

These tests ARE the spec. Change them deliberately; they define what the engine
promises every HR module.
"""

from uuid import UUID, uuid4

import pytest

from alpago.core.exceptions import ApprovalChainError, NotFound
from alpago.domain.approvals import (
    ApprovalDecision,
    create_approval_request,
    decide_step,
    delegate_step,
)
from alpago.domain.approvals.engine import StepResolver
from alpago.models.approval import (
    ApprovalChainTemplate,
    ApprovalRequestStatus,
    ApprovalStepStatus,
)


# ── test doubles ───────────────────────────────────────────────────────────────

class FixedResolver(StepResolver):
    """Resolver that returns a preset user_id per role."""

    def __init__(self, mapping: dict[str, UUID]):
        self.mapping = mapping

    async def resolve(self, *, role, scope, context, session):
        return self.mapping.get(role)


@pytest.fixture
async def three_step_chain(session):
    tpl = ApprovalChainTemplate(
        request_type="hiring_request",
        name="hiring 3-step",
        steps=[
            {"role": "agm", "scope": "department", "sla_hours": 24},
            {"role": "gm", "scope": "global", "sla_hours": 48},
            {"role": "ceo", "scope": "global", "sla_hours": 72},
        ],
        active=True,
    )
    session.add(tpl)
    await session.flush()
    return tpl


@pytest.fixture
async def resolver(make_user):
    agm = await make_user(email="agm@alpago.test")
    gm = await make_user(email="gm@alpago.test")
    ceo = await make_user(email="ceo@alpago.test")
    return FixedResolver({"agm": agm.id, "gm": gm.id, "ceo": ceo.id})


# ── creation ───────────────────────────────────────────────────────────────────

async def test_create_opens_at_first_step(session, three_step_chain, resolver, make_user):
    submitter = await make_user(email="omar@alpago.test")
    req = await create_approval_request(
        session, resolver,
        request_type="hiring_request",
        subject_type="hiring_request",
        subject_id=uuid4(),
        submitter_user_id=submitter.id,
        context={"department_id": "dept-1"},
    )
    assert req.status == ApprovalRequestStatus.pending
    assert len(req.steps) == 3
    assert req.steps[0].status == ApprovalStepStatus.active
    assert req.steps[0].approver_role == "agm"
    assert req.steps[0].approver_user_id is not None  # resolver fired
    assert req.steps[1].status == ApprovalStepStatus.pending
    assert req.current_step_index == 0


async def test_create_without_active_chain_raises(session, resolver, make_user):
    submitter = await make_user()
    with pytest.raises(ApprovalChainError, match="no active approval chain"):
        await create_approval_request(
            session, resolver,
            request_type="nonexistent_type",
            subject_type="x", subject_id=uuid4(),
            submitter_user_id=submitter.id,
        )


# ── happy path ─────────────────────────────────────────────────────────────────

async def test_approve_advances_to_next_step(session, three_step_chain, resolver, make_user):
    submitter = await make_user()
    req = await create_approval_request(
        session, resolver,
        request_type="hiring_request",
        subject_type="hiring_request", subject_id=uuid4(),
        submitter_user_id=submitter.id,
    )
    await decide_step(
        session, resolver,
        step_id=req.steps[0].id,
        decision=ApprovalDecision.approve,
        actor_user_id=req.steps[0].approver_user_id,
    )
    await session.refresh(req)
    assert req.steps[0].status == ApprovalStepStatus.approved
    assert req.steps[1].status == ApprovalStepStatus.active
    assert req.status == ApprovalRequestStatus.in_review
    assert req.current_step_index == 1


async def test_approving_last_step_finalises(session, three_step_chain, resolver, make_user):
    submitter = await make_user()
    req = await create_approval_request(
        session, resolver,
        request_type="hiring_request",
        subject_type="hiring_request", subject_id=uuid4(),
        submitter_user_id=submitter.id,
    )
    for step in req.steps:
        await session.refresh(step)
        await decide_step(
            session, resolver,
            step_id=step.id,
            decision=ApprovalDecision.approve,
            actor_user_id=step.approver_user_id,
        )
    await session.refresh(req)
    assert req.status == ApprovalRequestStatus.approved
    assert req.decided_at is not None
    assert all(s.status == ApprovalStepStatus.approved for s in req.steps)


# ── rejection ──────────────────────────────────────────────────────────────────

async def test_reject_closes_request_and_skips_downstream(
    session, three_step_chain, resolver, make_user
):
    submitter = await make_user()
    req = await create_approval_request(
        session, resolver,
        request_type="hiring_request",
        subject_type="hiring_request", subject_id=uuid4(),
        submitter_user_id=submitter.id,
    )
    # Approve step 0, then reject at step 1
    await decide_step(
        session, resolver,
        step_id=req.steps[0].id,
        decision=ApprovalDecision.approve,
        actor_user_id=req.steps[0].approver_user_id,
    )
    await session.refresh(req)
    await decide_step(
        session, resolver,
        step_id=req.steps[1].id,
        decision=ApprovalDecision.reject,
        actor_user_id=req.steps[1].approver_user_id,
        comment="salary band too high",
    )
    await session.refresh(req)
    assert req.status == ApprovalRequestStatus.rejected
    assert req.steps[1].status == ApprovalStepStatus.rejected
    assert req.steps[1].comment == "salary band too high"
    assert req.steps[2].status == ApprovalStepStatus.skipped


# ── changes requested + resubmit ───────────────────────────────────────────────

async def test_request_changes_sets_state_and_pending_downstream(
    session, three_step_chain, resolver, make_user
):
    submitter = await make_user()
    req = await create_approval_request(
        session, resolver,
        request_type="hiring_request",
        subject_type="hiring_request", subject_id=uuid4(),
        submitter_user_id=submitter.id,
    )
    await decide_step(
        session, resolver,
        step_id=req.steps[0].id,
        decision=ApprovalDecision.request_changes,
        actor_user_id=req.steps[0].approver_user_id,
        comment="please add replacement reason",
    )
    await session.refresh(req)
    assert req.status == ApprovalRequestStatus.changes_requested
    assert req.steps[0].status == ApprovalStepStatus.changes_requested
    assert req.steps[1].status == ApprovalStepStatus.pending


# ── permissions / sanity ───────────────────────────────────────────────────────

async def test_cannot_decide_non_active_step(session, three_step_chain, resolver, make_user):
    submitter = await make_user()
    req = await create_approval_request(
        session, resolver,
        request_type="hiring_request",
        subject_type="hiring_request", subject_id=uuid4(),
        submitter_user_id=submitter.id,
    )
    with pytest.raises(ApprovalChainError, match="cannot decide"):
        # trying to decide step 1 before step 0 is approved
        await decide_step(
            session, resolver,
            step_id=req.steps[1].id,
            decision=ApprovalDecision.approve,
            actor_user_id=submitter.id,
        )


async def test_decide_unknown_step_404(session, resolver):
    with pytest.raises(NotFound):
        await decide_step(
            session, resolver,
            step_id=uuid4(),
            decision=ApprovalDecision.approve,
            actor_user_id=uuid4(),
        )


# ── delegation ────────────────────────────────────────────────────────────────

async def test_delegate_reassigns_active_step(session, three_step_chain, resolver, make_user):
    submitter = await make_user()
    standin = await make_user(email="standin@alpago.test")
    req = await create_approval_request(
        session, resolver,
        request_type="hiring_request",
        subject_type="hiring_request", subject_id=uuid4(),
        submitter_user_id=submitter.id,
    )
    step = req.steps[0]
    original_approver = step.approver_user_id
    await delegate_step(
        session, resolver,
        step_id=step.id, to_user_id=standin.id, actor_user_id=original_approver,
    )
    await session.refresh(step)
    assert step.approver_user_id == standin.id
    assert step.delegated_to_user_id == standin.id
    assert step.status == ApprovalStepStatus.active  # still awaiting decision
