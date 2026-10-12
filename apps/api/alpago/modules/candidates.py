"""Candidates module — all-in-one: models, schemas, service, routes.

Flow:
  POST /candidates                     → add candidate (name, email, phone, source)
  POST /candidates/{id}/cv             → upload CV (multipart); triggers AI screening
  POST /candidates/{id}/screen         → re-run AI screening against latest JD
  POST /candidates/{id}/stage          → move stage (sourced → screened → shortlisted → …)
  GET  /candidates?hiring_request_id=  → list for a request
  GET  /candidates/{id}                → detail
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import JSON, Enum as SAEnum, ForeignKey, String, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from alpago.api.deps import current_user, get_db
from alpago.core.config import settings
from alpago.core.audit import record_audit, snapshot
from alpago.core.exceptions import NotFound, ValidationFailed
from alpago.models.base import Auditable, Base, Timestamps, UUIDPK
from alpago.models.user import User
from alpago.modules.hiring import HiringRequest

# ─────────────────── MODELS ────────────────────────────────────────────────

class CandidateStage(str, Enum):
    sourced = "sourced"
    screened = "screened"
    shortlisted = "shortlisted"
    interviewing = "interviewing"
    offer = "offer"
    hired = "hired"
    rejected = "rejected"
    withdrawn = "withdrawn"


class Candidate(Base, UUIDPK, Timestamps, Auditable):
    __tablename__ = "candidates"

    hiring_request_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("hiring_requests.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str | None] = mapped_column(String(40))
    stage: Mapped[CandidateStage] = mapped_column(
        SAEnum(CandidateStage, native_enum=False, length=20),
        default=CandidateStage.sourced, nullable=False, index=True,
    )
    current_role: Mapped[str | None] = mapped_column(String(200))
    years_experience: Mapped[int | None] = mapped_column()
    expected_salary: Mapped[int | None] = mapped_column()
    # Captured on the Interview Evaluation Form header
    visa_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    joining_availability: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000))

    cvs: Mapped[list["Cv"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan",
        order_by="Cv.created_at.desc()",
    )


class Cv(Base, UUIDPK, Timestamps):
    __tablename__ = "cvs"

    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("candidates.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    parsed_text: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_score: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="cvs")


# ─────────────────── SCHEMAS ───────────────────────────────────────────────

class CandidateCreate(BaseModel):
    hiring_request_id: UUID
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    source: str | None = Field(default="direct", max_length=40)
    current_role: str | None = Field(default=None, max_length=200)
    years_experience: int | None = Field(default=None, ge=0, le=70)
    expected_salary: int | None = Field(default=None, ge=0)
    visa_status: str | None = Field(default=None, max_length=60)
    joining_availability: str | None = Field(default=None, max_length=120)


class CvOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    ai_score: dict | None
    created_at: datetime


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    hiring_request_id: UUID
    name: str
    email: EmailStr
    phone: str | None
    source: str | None
    stage: str
    current_role: str | None
    years_experience: int | None
    expected_salary: int | None
    notes: str | None
    cvs: list[CvOut]
    created_at: datetime


class StageUpdate(BaseModel):
    stage: CandidateStage


# ─────────────────── SERVICE ───────────────────────────────────────────────

MAX_CV_BYTES = 10 * 1024 * 1024   # 10 MB
ALLOWED_CV_TYPES = {"application/pdf", "application/msword",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "text/plain"}


async def _ensure_uploads_dir() -> Path:
    base = Path("./uploads/cvs").resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


async def create_candidate(session: AsyncSession, *, actor: User, body: CandidateCreate) -> Candidate:
    # Ensure the hiring request exists
    hr = await session.get(HiringRequest, body.hiring_request_id)
    if hr is None:
        raise NotFound("hiring request not found")

    c = Candidate(
        hiring_request_id=body.hiring_request_id,
        name=body.name, email=body.email, phone=body.phone,
        source=body.source, current_role=body.current_role,
        years_experience=body.years_experience, expected_salary=body.expected_salary,
        visa_status=body.visa_status, joining_availability=body.joining_availability,
        created_by=actor.id, updated_by=actor.id,
    )
    session.add(c)
    await session.flush()
    await session.refresh(c, attribute_names=["cvs"])

    await record_audit(
        session, actor=actor, action="candidate.created",
        subject_type="candidate", subject_id=c.id,
        after=snapshot(c, ["name", "email", "source", "stage"]),
        context={"hiring_request_id": str(c.hiring_request_id)},
    )
    return c


async def list_candidates(session: AsyncSession, *, hiring_request_id: UUID | None = None) -> list[Candidate]:
    stmt = select(Candidate).options(selectinload(Candidate.cvs)).order_by(Candidate.created_at.desc())
    if hiring_request_id:
        stmt = stmt.where(Candidate.hiring_request_id == hiring_request_id)
    return list((await session.execute(stmt)).scalars().all())


async def get_candidate(session: AsyncSession, candidate_id: UUID) -> Candidate:
    stmt = select(Candidate).options(selectinload(Candidate.cvs)).where(Candidate.id == candidate_id)
    c = (await session.execute(stmt)).scalar_one_or_none()
    if c is None:
        raise NotFound("candidate not found")
    return c


async def upload_cv(
    session: AsyncSession, *, candidate_id: UUID, upload: UploadFile
) -> Cv:
    if upload.content_type not in ALLOWED_CV_TYPES:
        raise ValidationFailed(f"unsupported CV type: {upload.content_type}")
    data = await upload.read()
    if len(data) > MAX_CV_BYTES:
        raise ValidationFailed(f"CV larger than {MAX_CV_BYTES // 1024 // 1024}MB")

    base = await _ensure_uploads_dir()
    ext = (upload.filename or "cv").rsplit(".", 1)[-1][:8] if "." in (upload.filename or "") else "bin"
    fname = f"{uuid4()}.{ext}"
    fpath = base / fname
    fpath.write_bytes(data)

    cv = Cv(
        candidate_id=candidate_id,
        filename=upload.filename or fname,
        file_path=str(fpath),
        parsed_text=_naive_text_extract(data, ext),
    )
    session.add(cv)
    await session.flush()

    # Fire AI screening asynchronously
    from alpago.workers.tasks import screen_cv_async
    screen_cv_async.delay(str(cv.id))
    return cv


def _naive_text_extract(data: bytes, ext: str) -> str:
    """Very basic text extractor for the MVP. Real PDF parsing lives in Phase 2."""
    if ext in ("txt", "md"):
        try:
            return data.decode("utf-8", errors="replace")[:50_000]
        except Exception:
            return ""
    # Pretty crude for PDFs/docx — just extract ASCII-ish characters.
    try:
        text = data.decode("latin-1", errors="ignore")
        return "".join(ch for ch in text if ch.isprintable() or ch in " \n\t")[:50_000]
    except Exception:
        return ""


async def screen_candidate(session: AsyncSession, candidate_id: UUID) -> Cv:
    """Run AI screening on the latest CV for a candidate."""
    c = await get_candidate(session, candidate_id)
    if not c.cvs:
        raise ValidationFailed("candidate has no CV to screen")
    hr = await session.get(HiringRequest, c.hiring_request_id)
    if hr is None or not hr.jd_markdown:
        raise ValidationFailed("hiring request has no JD to screen against")

    cv = c.cvs[0]
    try:
        from alpago.ai import screen_cv
        result = await screen_cv(cv_text=cv.parsed_text or "", jd_text=hr.jd_markdown)
        cv.ai_score = result.model_dump()
        if c.stage == CandidateStage.sourced:
            c.stage = CandidateStage.screened
    except Exception as e:
        cv.ai_score = {"error": str(e)[:300]}
    await session.flush()
    return cv


async def update_stage(session: AsyncSession, *, candidate_id: UUID, stage: CandidateStage, actor: User) -> Candidate:
    c = await get_candidate(session, candidate_id)
    before = snapshot(c, ["stage"])
    c.stage = stage
    c.updated_by = actor.id
    await session.flush()

    await record_audit(
        session, actor=actor, action="candidate.stage_changed",
        subject_type="candidate", subject_id=c.id,
        before=before, after=snapshot(c, ["stage"]),
    )
    return c


# ─────────────────── ROUTES ─────────────────────────────────────────────────

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
async def create(
    body: CandidateCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Candidate:
    return await create_candidate(db, actor=user, body=body)


@router.get("", response_model=list[CandidateOut])
async def list_all(
    hiring_request_id: UUID | None = None,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Candidate]:
    return await list_candidates(db, hiring_request_id=hiring_request_id)


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_one(
    candidate_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Candidate:
    return await get_candidate(db, candidate_id)


@router.post("/{candidate_id}/cv", response_model=CvOut, status_code=status.HTTP_201_CREATED)
async def upload_cv_endpoint(
    candidate_id: UUID,
    file: UploadFile = File(...),
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Cv:
    # ensure candidate exists first (nicer 404 than FK error)
    await get_candidate(db, candidate_id)
    return await upload_cv(db, candidate_id=candidate_id, upload=file)


@router.post("/{candidate_id}/screen", response_model=CvOut)
async def screen_endpoint(
    candidate_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Cv:
    return await screen_candidate(db, candidate_id)


@router.post("/{candidate_id}/stage", response_model=CandidateOut)
async def stage_endpoint(
    candidate_id: UUID,
    body: StageUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Candidate:
    return await update_stage(db, candidate_id=candidate_id, stage=body.stage, actor=user)
