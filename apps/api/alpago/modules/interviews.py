"""Interviews module — all-in-one.

Flow:
  POST /interviews                      → schedule
  GET  /interviews/mine                 → my upcoming/past
  GET  /interviews/{id}                 → detail with evaluations
  POST /interviews/{id}/questions       → AI-draft tailored questions
  POST /interviews/{id}/evaluate        → score the interview
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Enum as SAEnum, ForeignKey, Integer, String, Uuid, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from alpago.api.deps import current_user, get_db
from alpago.core.exceptions import NotFound, ValidationFailed
from alpago.models.base import Auditable, Base, Timestamps, UUIDPK
from alpago.models.user import User
from alpago.modules.candidates import Candidate
from alpago.modules.hiring import HiringRequest


# ─────────────────── MODELS ────────────────────────────────────────────────

class InterviewStatus(str, Enum):
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class InterviewMode(str, Enum):
    in_person = "in_person"
    video = "video"
    phone = "phone"


class Interview(Base, UUIDPK, Timestamps, Auditable):
    __tablename__ = "interviews"

    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("candidates.id"), index=True, nullable=False
    )
    hiring_request_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("hiring_requests.id"), index=True, nullable=False
    )
    round_name: Mapped[str] = mapped_column(String(80), nullable=False, default="Round 1")
    scheduled_at: Mapped[datetime] = mapped_column(nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    mode: Mapped[InterviewMode] = mapped_column(
        SAEnum(InterviewMode, native_enum=False, length=20),
        default=InterviewMode.video, nullable=False,
    )
    location_or_link: Mapped[str | None] = mapped_column(String(500))
    interviewer_user_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[InterviewStatus] = mapped_column(
        SAEnum(InterviewStatus, native_enum=False, length=20),
        default=InterviewStatus.scheduled, nullable=False, index=True,
    )
    questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    questions_generated_by_ai: Mapped[bool] = mapped_column(default=False, nullable=False)

    evaluations: Mapped[list["InterviewEvaluation"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )


# Alpago Interview Evaluation Form (2024-Alpago/HR/IEF form-1.2).
# The six criteria and the agreement scale are taken verbatim from the form.
IEF_CRITERIA: list[tuple[str, str]] = [
    ("knowledge_skills",
     "The applicant has the knowledge, skills and abilities to perform the duties of this position"),
    ("education",
     "The applicant has the appropriate level of education for this position"),
    ("enthusiasm",
     "The applicant views this position with excitement and enthusiasm"),
    ("experience",
     "The applicant has the appropriate level of experience necessary for this position"),
    ("communication",
     "The applicant displayed the ability to communicate well"),
    ("recommended",
     "The applicant should be included in the final list of recommended applicants"),
]

IEF_CRITERIA_KEYS = [k for k, _ in IEF_CRITERIA]


class Agreement(str, Enum):
    strongly_agree = "strongly_agree"
    agree = "agree"
    disagree = "disagree"
    undetermined = "undetermined"


# Used to roll the agreement responses into a single comparable number.
AGREEMENT_POINTS: dict[str, int] = {
    "strongly_agree": 5,
    "agree": 4,
    "disagree": 2,
}


class InterviewEvaluation(Base, UUIDPK, Timestamps, Auditable):
    __tablename__ = "interview_evaluations"

    interview_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("interviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    interviewer_user_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("users.id"), nullable=False
    )

    # The six IEF criteria: {criterion_key: agreement}
    scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Relevant / UAE experience block
    relevant_industry_experience: Mapped[bool | None] = mapped_column(nullable=True)
    uae_work_experience: Mapped[bool | None] = mapped_column(nullable=True)

    # Free text blocks on the form
    strengths: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    areas_for_improvement: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    additional_comments: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    hr_notes: Mapped[str | None] = mapped_column(String(4000), nullable=True)

    # Derived from the responses so the pipeline can sort and filter
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verdict: Mapped[str] = mapped_column(String(40), nullable=False, default="hold")
    notes: Mapped[str | None] = mapped_column(String(4000))

    interview: Mapped["Interview"] = relationship(back_populates="evaluations")

    @property
    def recommended(self) -> bool:
        return self.scores.get("recommended") in ("strongly_agree", "agree")


# ─────────────────── SCHEMAS ───────────────────────────────────────────────

class InterviewCreate(BaseModel):
    candidate_id: UUID
    round_name: str = Field(default="Round 1", max_length=80)
    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=240)
    mode: InterviewMode = InterviewMode.video
    location_or_link: str | None = Field(default=None, max_length=500)
    interviewer_user_ids: list[UUID] = Field(default_factory=list, max_length=10)


class EvaluationCreate(BaseModel):
    """Mirrors the Alpago Interview Evaluation Form (IEF 1.2)."""
    scores: dict[str, Agreement] = Field(
        default_factory=dict,
        description="One entry per IEF criterion key",
    )
    relevant_industry_experience: bool | None = None
    uae_work_experience: bool | None = None
    strengths: str | None = Field(default=None, max_length=4000)
    areas_for_improvement: str | None = Field(default=None, max_length=4000)
    additional_comments: str | None = Field(default=None, max_length=4000)
    hr_notes: str | None = Field(default=None, max_length=4000)


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    interviewer_user_id: UUID
    scores: dict
    relevant_industry_experience: bool | None
    uae_work_experience: bool | None
    strengths: str | None
    areas_for_improvement: str | None
    additional_comments: str | None
    hr_notes: str | None
    overall_score: int | None
    verdict: str
    recommended: bool = False
    notes: str | None
    created_at: datetime


class EvaluationFormOut(BaseModel):
    """The blank form definition, so the UI renders the real criteria."""
    code: str = "2024-Alpago/HR/IEF form-1.2"
    title: str = "Interview Evaluation Form"
    criteria: list[dict]
    scale: list[dict]


class InterviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    candidate_id: UUID
    hiring_request_id: UUID
    round_name: str
    scheduled_at: datetime
    duration_minutes: int
    mode: str
    location_or_link: str | None
    interviewer_user_ids: list
    status: str
    questions: list
    questions_generated_by_ai: bool
    evaluations: list[EvaluationOut]
    created_at: datetime


# ─────────────────── SERVICE ───────────────────────────────────────────────

async def schedule_interview(session: AsyncSession, *, actor: User, body: InterviewCreate) -> Interview:
    candidate = await session.get(Candidate, body.candidate_id)
    if candidate is None:
        raise NotFound("candidate not found")
    i = Interview(
        candidate_id=candidate.id,
        hiring_request_id=candidate.hiring_request_id,
        round_name=body.round_name,
        scheduled_at=body.scheduled_at,
        duration_minutes=body.duration_minutes,
        mode=body.mode,
        location_or_link=body.location_or_link,
        interviewer_user_ids=[str(u) for u in body.interviewer_user_ids],
        created_by=actor.id, updated_by=actor.id,
    )
    session.add(i)
    # Move candidate stage forward
    from alpago.modules.candidates import CandidateStage
    if candidate.stage in (CandidateStage.shortlisted, CandidateStage.screened, CandidateStage.sourced):
        candidate.stage = CandidateStage.interviewing
    await session.flush()
    await session.refresh(i, attribute_names=["evaluations"])
    return i


async def list_my_interviews(session: AsyncSession, user: User) -> list[Interview]:
    # Interviews where this user is listed as an interviewer, or any (admin)
    stmt = (
        select(Interview)
        .options(selectinload(Interview.evaluations))
        .order_by(Interview.scheduled_at.desc())
        .limit(100)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [i for i in rows if str(user.id) in i.interviewer_user_ids] or rows


async def get_interview(session: AsyncSession, interview_id: UUID) -> Interview:
    stmt = select(Interview).options(selectinload(Interview.evaluations)).where(Interview.id == interview_id)
    i = (await session.execute(stmt)).scalar_one_or_none()
    if i is None:
        raise NotFound("interview not found")
    return i


async def draft_ai_questions(session: AsyncSession, interview_id: UUID) -> Interview:
    from alpago.ai import draft_interview_questions
    i = await get_interview(session, interview_id)
    candidate = await session.get(Candidate, i.candidate_id)
    hr = await session.get(HiringRequest, i.hiring_request_id)
    cv_text = candidate.cvs[0].parsed_text if candidate and candidate.cvs else ""
    jd_text = hr.jd_markdown if hr else ""
    try:
        qs = await draft_interview_questions(jd_text=jd_text, cv_text=cv_text, count=8)
        i.questions = [q.model_dump() for q in qs]
        i.questions_generated_by_ai = True
    except Exception as e:
        i.questions = [{"question": "AI question generation failed; please add questions manually.",
                        "kind": "role_fit", "rationale": str(e)[:200]}]
    await session.flush()
    return i


async def add_evaluation(
    session: AsyncSession, *, interview_id: UUID, actor: User, body: EvaluationCreate
) -> InterviewEvaluation:
    i = await get_interview(session, interview_id)
    if any(e.interviewer_user_id == actor.id for e in i.evaluations):
        raise ValidationFailed("you already submitted an evaluation for this interview")
    unknown = set(body.scores) - set(IEF_CRITERIA_KEYS)
    if unknown:
        raise ValidationFailed(f"unknown evaluation criteria: {', '.join(sorted(unknown))}")

    responses = {k: (v.value if isinstance(v, Agreement) else str(v)) for k, v in body.scores.items()}

    # Roll the agreement responses into one comparable number (1-5).
    points = [AGREEMENT_POINTS[v] for v in responses.values() if v in AGREEMENT_POINTS]
    overall = round(sum(points) / len(points)) if points else None

    recommended = responses.get("recommended")
    verdict = (
        "recommend" if recommended in ("strongly_agree", "agree")
        else "not_recommend" if recommended == "disagree"
        else "hold"
    )

    ev = InterviewEvaluation(
        interview_id=i.id,
        interviewer_user_id=actor.id,
        scores=responses,
        relevant_industry_experience=body.relevant_industry_experience,
        uae_work_experience=body.uae_work_experience,
        strengths=body.strengths,
        areas_for_improvement=body.areas_for_improvement,
        additional_comments=body.additional_comments,
        hr_notes=body.hr_notes,
        overall_score=overall,
        verdict=verdict,
        created_by=actor.id, updated_by=actor.id,
    )
    session.add(ev)
    i.status = InterviewStatus.completed
    await session.flush()

    from alpago.core.audit import record_audit
    await record_audit(
        session, actor=actor, action="interview.evaluated",
        subject_type="candidate", subject_id=i.candidate_id,
        after={"verdict": verdict, "overall_score": overall, "round": i.round_name},
        context={"interview_id": str(i.id)},
    )
    return ev


# ─────────────────── ROUTES ─────────────────────────────────────────────────

router = APIRouter(prefix="/interviews", tags=["interviews"])


@router.get("/evaluation-form", response_model=EvaluationFormOut)
async def evaluation_form(_: User = Depends(current_user)) -> EvaluationFormOut:
    """The blank IEF 1.2 definition the evaluation UI renders from."""
    return EvaluationFormOut(
        criteria=[{"key": k, "label": label} for k, label in IEF_CRITERIA],
        scale=[
            {"value": "strongly_agree", "label": "Strongly agree"},
            {"value": "agree", "label": "Agree"},
            {"value": "disagree", "label": "Disagree"},
            {"value": "undetermined", "label": "Could not determine"},
        ],
    )


@router.post("", response_model=InterviewOut, status_code=status.HTTP_201_CREATED)
async def create(
    body: InterviewCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Interview:
    return await schedule_interview(db, actor=user, body=body)


@router.get("/mine", response_model=list[InterviewOut])
async def mine(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[Interview]:
    return await list_my_interviews(db, user)


@router.get("/{interview_id}", response_model=InterviewOut)
async def get_one(
    interview_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Interview:
    return await get_interview(db, interview_id)


@router.post("/{interview_id}/questions", response_model=InterviewOut)
async def generate_questions(
    interview_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Interview:
    return await draft_ai_questions(db, interview_id)


@router.post("/{interview_id}/evaluate", response_model=EvaluationOut, status_code=status.HTTP_201_CREATED)
async def evaluate(
    interview_id: UUID,
    body: EvaluationCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewEvaluation:
    return await add_evaluation(db, interview_id=interview_id, actor=user, body=body)
