"""Hiring module — one file: models + schemas + service + routes.

Flow:
  POST /hiring                → create a hiring request, kick off approval chain
  POST /hiring/{id}/generate-jd  → AI-draft the job description
  GET  /hiring[?status=]      → list
  GET  /hiring/{id}           → detail with its approval request
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Enum as SAEnum, ForeignKey, Integer, String, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from alpago.api.deps import current_user, get_db
from alpago.core.audit import record_audit, snapshot
from alpago.core.exceptions import NotFound
from alpago.domain.approvals import create_approval_request
from alpago.domain.approvals.service import DefaultStepResolver
from alpago.models.approval import ApprovalRequest
from alpago.models.base import Auditable, Base, Timestamps, UUIDPK
from alpago.models.user import User


# ─────────────────── MODELS ─────────────────────────────────────────────────

class HiringRequestStatus(str, Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    sourcing = "sourcing"
    filled = "filled"
    closed = "closed"
    cancelled = "cancelled"


class HiringRequest(Base, UUIDPK, Timestamps, Auditable):
    __tablename__ = "hiring_requests"

    role_title: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    department_id: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True)
    seniority: Mapped[str] = mapped_column(String(40), nullable=False, default="mid")
    positions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="AED")
    justification: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    target_start_date: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[HiringRequestStatus] = mapped_column(
        SAEnum(HiringRequestStatus, native_enum=False, length=30),
        default=HiringRequestStatus.draft, nullable=False, index=True,
    )
    jd_markdown: Mapped[str | None] = mapped_column(String, nullable=True)
    jd_generated_by_ai: Mapped[bool] = mapped_column(default=False, nullable=False)
    approval_request_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("approval_requests.id"), nullable=True
    )
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


# ─────────────────── SCHEMAS ────────────────────────────────────────────────

class HiringRequestCreate(BaseModel):
    role_title: str = Field(min_length=2, max_length=200)
    department: str = Field(min_length=1, max_length=100)
    seniority: str = Field(default="mid", pattern=r"^(junior|mid|senior|lead|director)$")
    positions: int = Field(default=1, ge=1, le=50)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    currency: str = Field(default="AED", max_length=10)
    justification: str | None = Field(default=None, max_length=2000)
    target_start_date: datetime | None = None
    generate_jd: bool = Field(default=True, description="Draft a JD with AI on creation")


class HiringRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    role_title: str
    department: str
    seniority: str
    positions: int
    salary_min: int | None
    salary_max: int | None
    currency: str
    justification: str | None
    status: str
    jd_markdown: str | None
    jd_generated_by_ai: bool
    approval_request_id: UUID | None
    created_at: datetime
    created_by: UUID | None
    target_start_date: datetime | None


class JdGenerateIn(BaseModel):
    notes: str = Field(default="", max_length=1000)


# ─────────────────── SERVICE ────────────────────────────────────────────────

async def create_hiring_request(
    session: AsyncSession, *, submitter: User, body: HiringRequestCreate
) -> HiringRequest:
    req = HiringRequest(
        role_title=body.role_title,
        department=body.department,
        seniority=body.seniority,
        positions=body.positions,
        salary_min=body.salary_min,
        salary_max=body.salary_max,
        currency=body.currency,
        justification=body.justification,
        target_start_date=body.target_start_date,
        status=HiringRequestStatus.pending_approval,
        created_by=submitter.id,
        updated_by=submitter.id,
    )
    session.add(req)
    await session.flush()

    # Fire the approval chain
    approval = await create_approval_request(
        session,
        DefaultStepResolver(),
        request_type="hiring_request",
        subject_type="hiring_request",
        subject_id=req.id,
        submitter_user_id=submitter.id,
        context={"role_title": req.role_title, "department": req.department},
    )
    req.approval_request_id = approval.id

    # Optional AI JD draft
    if body.generate_jd:
        try:
            from alpago.ai import draft_jd
            jd = await draft_jd(
                role_title=body.role_title, department=body.department,
                seniority=body.seniority, notes=body.justification or "",
            )
            req.jd_markdown = _format_jd_as_markdown(jd)
            req.jd_generated_by_ai = True
        except Exception:
            # AI failure doesn't block creation — JD can be generated later
            pass

    await session.flush()

    await record_audit(
        session, actor=submitter, action="hiring_request.created",
        subject_type="hiring_request", subject_id=req.id,
        after=snapshot(req, [
            "role_title", "department", "seniority", "positions",
            "salary_min", "salary_max", "status",
        ]),
        context={"approval_request_id": str(approval.id)},
    )
    return req


def _format_jd_as_markdown(jd) -> str:
    bullets = lambda items: "\n".join(f"- {s}" for s in items)
    parts = [
        f"# {jd.title}", "", "## About the role", jd.summary, "",
        "## Responsibilities", bullets(jd.responsibilities), "",
        "## Requirements", bullets(jd.requirements),
    ]
    if jd.nice_to_have:
        parts += ["", "## Nice to have", bullets(jd.nice_to_have)]
    if jd.offer_highlights:
        parts += ["", "## What we offer", bullets(jd.offer_highlights)]
    return "\n".join(parts)


async def list_hiring_requests(
    session: AsyncSession, *, status_filter: str | None = None
) -> list[HiringRequest]:
    stmt = select(HiringRequest).order_by(HiringRequest.created_at.desc())
    if status_filter:
        stmt = stmt.where(HiringRequest.status == status_filter)
    return list((await session.execute(stmt)).scalars().all())


async def get_hiring_request(session: AsyncSession, request_id: UUID) -> HiringRequest:
    row = await session.get(HiringRequest, request_id)
    if row is None:
        raise NotFound(f"hiring request {request_id} not found")
    # Lazy sync: if the approval chain has completed, reflect that here.
    from alpago.modules._approval_sync import sync_status_from_approval
    await sync_status_from_approval(
        session, subject=row,
        pending_value=HiringRequestStatus.pending_approval,
        approved_value=HiringRequestStatus.sourcing,  # approved → sourcing
        rejected_value=HiringRequestStatus.rejected,
    )
    return row


async def regenerate_jd(session: AsyncSession, request_id: UUID, notes: str) -> HiringRequest:
    from alpago.ai import draft_jd
    req = await get_hiring_request(session, request_id)
    jd = await draft_jd(
        role_title=req.role_title, department=req.department,
        seniority=req.seniority, notes=notes or (req.justification or ""),
    )
    req.jd_markdown = _format_jd_as_markdown(jd)
    req.jd_generated_by_ai = True
    await session.flush()

    await record_audit(
        session, action="hiring_request.jd_generated",
        subject_type="hiring_request", subject_id=req.id,
        after={"jd_generated_by_ai": True, "length": len(req.jd_markdown or "")},
    )
    return req


# ─────────────────── ROUTES ─────────────────────────────────────────────────

router = APIRouter(prefix="/hiring", tags=["hiring"])


@router.post("", response_model=HiringRequestOut, status_code=status.HTTP_201_CREATED)
async def create(
    body: HiringRequestCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> HiringRequest:
    return await create_hiring_request(db, submitter=user, body=body)


@router.get("", response_model=list[HiringRequestOut])
async def list_all(
    status_filter: str | None = None,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HiringRequest]:
    return await list_hiring_requests(db, status_filter=status_filter)


@router.get("/{request_id}", response_model=HiringRequestOut)
async def get_one(
    request_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> HiringRequest:
    return await get_hiring_request(db, request_id)


@router.post("/{request_id}/generate-jd", response_model=HiringRequestOut)
async def generate_jd_endpoint(
    request_id: UUID,
    body: JdGenerateIn,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> HiringRequest:
    return await regenerate_jd(db, request_id, body.notes)
