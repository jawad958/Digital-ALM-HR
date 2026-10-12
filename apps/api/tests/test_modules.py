"""Smoke tests for the onboarding modules.

Covers the critical path: hiring request creation → approval chain, candidate
upload stage transitions, interview scheduling + evaluation, offer draft →
approve → send → accept flow.
"""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from alpago.domain.approvals import ApprovalDecision, decide_step
from alpago.domain.approvals.service import DefaultStepResolver
from alpago.models.approval import (
    ApprovalChainTemplate,
    ApprovalRequestStatus,
)
from alpago.modules.candidates import (
    CandidateCreate,
    CandidateStage,
    create_candidate,
    update_stage,
    upload_cv,
)
from alpago.modules.hiring import HiringRequestCreate, create_hiring_request
from alpago.modules.interviews import (
    EvaluationCreate,
    InterviewCreate,
    InterviewMode,
    add_evaluation,
    schedule_interview,
)
from alpago.modules.offers import (
    OfferCreate,
    OfferResponse,
    OfferStatus,
    create_offer,
    get_offer_by_token,
    respond_to_offer,
    send_offer,
)
from alpago.models.role import Role, UserRole


# ─── helpers ──────────────────────────────────────────────────────────────

@pytest.fixture
async def seeded_chains(session):
    """Insert the three chains needed by these tests."""
    for req_type, steps in [
        ("hiring_request", [
            {"role": "agm", "scope": "global", "sla_hours": 24},
            {"role": "ceo", "scope": "global", "sla_hours": 48},
        ]),
        ("offer", [
            {"role": "agm", "scope": "global", "sla_hours": 24},
            {"role": "ceo", "scope": "global", "sla_hours": 24},
        ]),
    ]:
        session.add(ApprovalChainTemplate(
            request_type=req_type, name=f"{req_type} test chain",
            steps=steps, active=True,
        ))
    await session.flush()


@pytest.fixture
async def seeded_roles_and_approvers(session, make_user):
    """Create role rows + assign agm/ceo users so the resolver can find them."""
    agm_role = Role(key="agm", name="AGM")
    ceo_role = Role(key="ceo", name="CEO")
    session.add_all([agm_role, ceo_role])
    await session.flush()

    agm = await make_user(email="agm@test.alpago")
    ceo = await make_user(email="ceo@test.alpago")
    session.add_all([
        UserRole(user_id=agm.id, role_id=agm_role.id, scope_key=None, scope={}),
        UserRole(user_id=ceo.id, role_id=ceo_role.id, scope_key=None, scope={}),
    ])
    await session.flush()
    return {"agm": agm, "ceo": ceo}


# ─── hiring ──────────────────────────────────────────────────────────────

async def test_create_hiring_request_fires_approval_chain(
    session, make_user, seeded_chains, seeded_roles_and_approvers
):
    submitter = await make_user(email="omar@test.alpago")
    hr = await create_hiring_request(
        session, submitter=submitter,
        body=HiringRequestCreate(
            role_title="Marketing Manager", department="Contracting",
            seniority="senior", positions=1, salary_min=28000, salary_max=34000,
            justification="Replace resignation", generate_jd=False,
        ),
    )
    assert hr.status.value == "pending_approval"
    assert hr.approval_request_id is not None

    # Approval request has 2 steps (agm, ceo) and first is active
    from alpago.models.approval import ApprovalRequest
    req = await session.get(ApprovalRequest, hr.approval_request_id)
    await session.refresh(req, attribute_names=["steps"])
    assert len(req.steps) == 2
    assert req.steps[0].status.value == "active"
    assert req.steps[0].approver_role == "agm"
    assert req.steps[0].approver_user_id == seeded_roles_and_approvers["agm"].id


# ─── candidates ──────────────────────────────────────────────────────────

async def test_candidate_create_and_cv_upload(session, make_user, seeded_chains, seeded_roles_and_approvers):
    submitter = await make_user(email="ta@test.alpago")
    hr = await create_hiring_request(
        session, submitter=submitter,
        body=HiringRequestCreate(
            role_title="Site Engineer", department="Contracting", seniority="senior",
            generate_jd=False,
        ),
    )
    cand = await create_candidate(
        session, actor=submitter,
        body=CandidateCreate(
            hiring_request_id=hr.id, name="Lina Nasser",
            email="lina@example.com", source="direct",
            current_role="Site Engineer, Emaar", years_experience=9, expected_salary=32000,
        ),
    )
    assert cand.stage == CandidateStage.sourced

    # Upload a plaintext "CV"
    upload = UploadFile(
        filename="cv.txt",
        file=BytesIO(b"9 years of site engineering experience with Emaar and DAMAC."),
        headers=Headers({"content-type": "text/plain"}),
    )
    cv = await upload_cv(session, candidate_id=cand.id, upload=upload)
    assert cv.filename == "cv.txt"
    assert cv.parsed_text and "site engineering" in cv.parsed_text


async def test_candidate_stage_transitions(session, make_user, seeded_chains, seeded_roles_and_approvers):
    user = await make_user()
    hr = await create_hiring_request(
        session, submitter=user,
        body=HiringRequestCreate(role_title="Test Role", department="Test Dept", generate_jd=False),
    )
    cand = await create_candidate(
        session, actor=user,
        body=CandidateCreate(hiring_request_id=hr.id, name="Zara", email="z@test.alpago"),
    )
    cand = await update_stage(session, candidate_id=cand.id, stage=CandidateStage.shortlisted, actor=user)
    assert cand.stage == CandidateStage.shortlisted


# ─── interviews ──────────────────────────────────────────────────────────

async def test_schedule_interview_and_evaluate(session, make_user, seeded_chains, seeded_roles_and_approvers):
    user = await make_user()
    hr = await create_hiring_request(
        session, submitter=user,
        body=HiringRequestCreate(role_title="Test Role", department="Test Dept", generate_jd=False),
    )
    cand = await create_candidate(
        session, actor=user,
        body=CandidateCreate(hiring_request_id=hr.id, name="Zara", email="z@test.alpago"),
    )
    i = await schedule_interview(
        session, actor=user,
        body=InterviewCreate(
            candidate_id=cand.id, round_name="Round 1",
            scheduled_at=datetime.now(tz=timezone.utc) + timedelta(days=2),
            duration_minutes=45, mode=InterviewMode.video,
            interviewer_user_ids=[user.id],
        ),
    )
    assert i.status.value == "scheduled"

    # Candidate stage auto-moved to interviewing
    await session.refresh(cand)
    assert cand.stage == CandidateStage.interviewing

    # Evaluate
    # IEF 1.2: six criteria on the agreement scale, not ad-hoc numeric scores
    from alpago.modules.interviews import IEF_CRITERIA_KEYS
    ev = await add_evaluation(
        session, interview_id=i.id, actor=user,
        body=EvaluationCreate(
            scores={k: "strongly_agree" for k in IEF_CRITERIA_KEYS},
            relevant_industry_experience=True,
            uae_work_experience=True,
            strengths="Excellent fit",
        ),
    )
    # all six "strongly agree" roll up to 5, and criterion 6 drives the verdict
    assert ev.overall_score == 5
    assert ev.verdict == "recommend"
    assert ev.recommended is True
    await session.refresh(i)
    assert i.status.value == "completed"


# ─── offers ──────────────────────────────────────────────────────────────

async def test_offer_full_lifecycle(session, make_user, seeded_chains, seeded_roles_and_approvers):
    hr_lead = await make_user(email="hr@test.alpago")
    hr = await create_hiring_request(
        session, submitter=hr_lead,
        body=HiringRequestCreate(role_title="PM", department="Contracting", generate_jd=False),
    )
    cand = await create_candidate(
        session, actor=hr_lead,
        body=CandidateCreate(hiring_request_id=hr.id, name="M. Nasr", email="m@test.alpago"),
    )

    # Draft the offer
    offer = await create_offer(
        session, actor=hr_lead,
        body=OfferCreate(
            candidate_id=cand.id, role_title="PM",
            base_salary=31000, currency="AED",
            allowances={"housing": 4500}, start_date=datetime.now(tz=timezone.utc) + timedelta(days=30),
            draft_letter=False,
        ),
    )
    assert offer.status == OfferStatus.pending_approval

    # Approve through the chain
    from alpago.models.approval import ApprovalRequest
    req = await session.get(ApprovalRequest, offer.approval_request_id)
    await session.refresh(req, attribute_names=["steps"])
    for step in req.steps:
        await decide_step(
            session, DefaultStepResolver(),
            step_id=step.id, decision=ApprovalDecision.approve,
            actor_user_id=step.approver_user_id,
        )
        await session.refresh(req, attribute_names=["steps"])
    await session.refresh(req)
    assert req.status == ApprovalRequestStatus.approved

    # Transition offer status to approved (would be done by a hook; do it manually here)
    offer.status = OfferStatus.approved
    await session.flush()

    # Send it
    sent = await send_offer(session, offer.id, hr_lead)
    assert sent.status == OfferStatus.sent
    assert sent.acceptance_token

    # Candidate reads via token
    public_view = await get_offer_by_token(session, sent.acceptance_token)
    assert public_view.id == sent.id

    # Candidate accepts
    resp = await respond_to_offer(session, sent.acceptance_token, OfferResponse(decision="accept"))
    assert resp.status == OfferStatus.accepted
    assert resp.acceptance_token is None  # token invalidated
    await session.refresh(cand)
    assert cand.stage == CandidateStage.hired
