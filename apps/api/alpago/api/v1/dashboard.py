"""Dashboard — live counts and the actionable queue for the signed-in user.

  GET /dashboard   stats + "needs your attention" items
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alpago.api.deps import current_user, get_db
from alpago.models.approval import ApprovalRequest, ApprovalStep, ApprovalStepStatus
from alpago.models.user import User
from alpago.modules.candidates import Candidate, CandidateStage
from alpago.modules.documents import Document, DocStatus
from alpago.modules.employees import Employee, EmploymentStatus, OnboardingTask
from alpago.modules.hiring import HiringRequest, HiringRequestStatus
from alpago.modules.interviews import Interview, InterviewStatus
from alpago.modules.offers import Offer, OfferStatus


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class Stat(BaseModel):
    label: str
    value: int
    sub: str | None = None
    tone: str = "default"   # default | ok | warn | bad
    href: str | None = None


class AttentionItem(BaseModel):
    kind: str               # approval | document | offer | onboarding
    pill: str
    pill_tone: str
    category: str
    title: str
    meta: str
    href: str
    initials: str = ""


class DashboardOut(BaseModel):
    greeting_name: str
    today: date
    attention_count: int
    stats: list[Stat]
    attention: list[AttentionItem]
    hires_this_month: int
    headcount: int


def _initials(name: str | None) -> str:
    if not name:
        return "—"
    parts = [p for p in name.replace("@", " ").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "—"


async def _count(db: AsyncSession, stmt) -> int:
    return (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()


@router.get("", response_model=DashboardOut)
async def dashboard(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardOut:
    today = date.today()
    now = datetime.now(tz=timezone.utc)
    week_end = now + timedelta(days=7)
    month_start = today.replace(day=1)

    # ── counts ──
    open_reqs = await _count(db, select(HiringRequest).where(
        HiringRequest.status.in_([
            HiringRequestStatus.pending_approval,
            HiringRequestStatus.approved,
            HiringRequestStatus.sourcing,
        ])
    ))

    pipeline = await _count(db, select(Candidate).where(
        Candidate.stage.notin_([
            CandidateStage.hired, CandidateStage.rejected, CandidateStage.withdrawn,
        ])
    ))

    interviews_week = await _count(db, select(Interview).where(
        Interview.scheduled_at >= now,
        Interview.scheduled_at <= week_end,
        Interview.status == InterviewStatus.scheduled,
    ))

    expiring_30 = await _count(db, select(Document).where(
        Document.deleted_at.is_(None),
        Document.expiry_date.is_not(None),
        Document.expiry_date <= today + timedelta(days=30),
    ))

    headcount = await _count(db, select(Employee).where(
        Employee.deleted_at.is_(None),
        Employee.status != EmploymentStatus.exited,
    ))

    onboarding_count = await _count(db, select(Employee).where(
        Employee.deleted_at.is_(None),
        Employee.status == EmploymentStatus.onboarding,
    ))

    hires_this_month = await _count(db, select(Employee).where(
        Employee.deleted_at.is_(None),
        Employee.join_date.is_not(None),
        Employee.join_date >= month_start,
        Employee.join_date <= today,
    ))

    # ── my approval queue ──
    my_steps = (await db.execute(
        select(ApprovalStep)
        .where(
            ApprovalStep.approver_user_id == user.id,
            ApprovalStep.status == ApprovalStepStatus.active,
        )
        .options(selectinload(ApprovalStep.request))
    )).scalars().all()

    attention: list[AttentionItem] = []

    for step in my_steps:
        req: ApprovalRequest | None = step.request
        if req is None:
            continue
        ctx = req.context or {}
        subject = ctx.get("role_title") or ctx.get("title") or req.request_type.replace("_", " ")
        overdue = ""
        if step.activated_at:
            activated = step.activated_at
            if activated.tzinfo is None:
                activated = activated.replace(tzinfo=timezone.utc)
            hours = (now - activated).total_seconds() / 3600
            if hours > step.sla_hours:
                overdue = f" · overdue by {int((hours - step.sla_hours) / 24) or 1}d"
        attention.append(AttentionItem(
            kind="approval",
            pill="Needs you", pill_tone="gold",
            category=req.request_type.replace("_", " ").title(),
            title=str(subject),
            meta=f"Awaiting your {(step.approver_role or '').upper()} decision{overdue}",
            href="/approvals",
            initials=_initials(str(subject)),
        ))

    # ── documents needing action ──
    urgent_docs = (await db.execute(
        select(Document)
        .where(
            Document.deleted_at.is_(None),
            Document.expiry_date.is_not(None),
            Document.expiry_date <= today + timedelta(days=30),
        )
        .order_by(Document.expiry_date.asc())
        .limit(5)
    )).scalars().all()

    emp_names: dict[UUID, str] = {}
    if urgent_docs:
        ids = [d.owner_id for d in urgent_docs]
        emps = (await db.execute(select(Employee).where(Employee.id.in_(ids)))).scalars().all()
        emp_names = {e.id: e.full_name for e in emps}

    for d in urgent_docs:
        days = (d.expiry_date - today).days
        who = emp_names.get(d.owner_id, "Unknown")
        label = d.doc_type.value.replace("_", " ").title()
        attention.append(AttentionItem(
            kind="document",
            pill="Expired" if days < 0 else "Expiring",
            pill_tone="bad" if days <= 7 else "warn",
            category=label,
            title=f"{who} — {label.lower()} {'expired' if days < 0 else f'expires in {days} days'}",
            meta=f"Expiry {d.expiry_date.isoformat()} · "
                 + ("verified" if d.status == DocStatus.verified else "awaiting verification"),
            href="/documents",
            initials=_initials(who),
        ))

    # ── offers awaiting approval ──
    pending_offers = (await db.execute(
        select(Offer).where(Offer.status == OfferStatus.pending_approval).limit(5)
    )).scalars().all()

    if pending_offers:
        cand_ids = [o.candidate_id for o in pending_offers]
        cands = (await db.execute(select(Candidate).where(Candidate.id.in_(cand_ids)))).scalars().all()
        cand_names = {c.id: c.name for c in cands}
        for o in pending_offers:
            who = cand_names.get(o.candidate_id, "Candidate")
            attention.append(AttentionItem(
                kind="offer",
                pill="Offer approval", pill_tone="warn",
                category=o.role_title,
                title=f"{who} — offer at {o.currency} {o.base_salary:,} / month",
                meta="Waiting on the offer approval chain",
                href="/offers",
                initials=_initials(who),
            ))

    # ── stalled onboarding ──
    stalled = (await db.execute(
        select(Employee)
        .where(
            Employee.deleted_at.is_(None),
            Employee.status == EmploymentStatus.onboarding,
        )
        .options(selectinload(Employee.onboarding_tasks))
        .limit(5)
    )).scalars().all()

    for e in stalled:
        tasks = e.onboarding_tasks or []
        outstanding = [t for t in tasks if not t.completed]
        if not outstanding:
            continue
        attention.append(AttentionItem(
            kind="onboarding",
            pill="Onboarding", pill_tone="default",
            category="Joining process",
            title=f"{e.full_name} — {len(outstanding)} task{'s' if len(outstanding) != 1 else ''} outstanding",
            meta=f"Next: {outstanding[0].title}"
                 + (f" · joins {e.join_date.isoformat()}" if e.join_date else ""),
            href=f"/employees/{e.id}",
            initials=_initials(e.full_name),
        ))

    stats = [
        Stat(label="Open requisitions", value=open_reqs,
             sub="Approved or in approval", href="/hiring"),
        Stat(label="Candidates in pipeline", value=pipeline,
             sub="Excludes hired and rejected", href="/candidates"),
        Stat(label="Interviews next 7 days", value=interviews_week,
             sub="Scheduled", href="/interviews"),
        Stat(label="Documents expiring (30d)", value=expiring_30,
             sub="Includes already expired",
             tone="bad" if expiring_30 else "default", href="/documents"),
    ]

    return DashboardOut(
        greeting_name=(user.name or user.email.split("@")[0]).split()[0],
        today=today,
        attention_count=len(attention),
        stats=stats,
        attention=attention[:8],
        hires_this_month=hires_this_month,
        headcount=headcount,
    )
