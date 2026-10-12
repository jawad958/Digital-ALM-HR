"""Offers module — all-in-one.

Flow:
  POST /offers                    → draft offer; auto-create approval chain + AI letter
  GET  /offers?candidate_id=      → list
  GET  /offers/{id}               → detail
  POST /offers/{id}/send          → send to candidate (generates magic-link token)
  GET  /offers/accept/{token}     → candidate reads the offer (public, token-gated)
  POST /offers/accept/{token}     → candidate accepts/declines (public, token-gated)
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from secrets import token_urlsafe
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Enum as SAEnum, ForeignKey, Integer, String, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from alpago.api.deps import current_user, get_db
from alpago.core.audit import record_audit, snapshot
from alpago.core.exceptions import Forbidden, NotFound, ValidationFailed
from alpago.domain.approvals import create_approval_request
from alpago.domain.approvals.service import DefaultStepResolver
from alpago.models.base import Auditable, Base, Timestamps, UUIDPK
from alpago.models.user import AuthProvider, User, UserStatus
from alpago.modules.candidates import Candidate, CandidateStage
from alpago.modules.hiring import HiringRequest


# ─────────────────── MODELS ────────────────────────────────────────────────

class OfferStatus(str, Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected_internally = "rejected_internally"
    sent = "sent"
    accepted = "accepted"
    declined = "declined"
    withdrawn = "withdrawn"
    expired = "expired"


class Offer(Base, UUIDPK, Timestamps, Auditable):
    __tablename__ = "offers"

    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("candidates.id"), index=True, nullable=False
    )
    hiring_request_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("hiring_requests.id"), index=True, nullable=False
    )
    role_title: Mapped[str] = mapped_column(String(200), nullable=False)
    base_salary: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="AED")
    allowances: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    start_date: Mapped[datetime] = mapped_column(nullable=False)
    letter_markdown: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[OfferStatus] = mapped_column(
        SAEnum(OfferStatus, native_enum=False, length=30),
        default=OfferStatus.draft, nullable=False, index=True,
    )
    approval_request_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("approval_requests.id"), nullable=True
    )
    acceptance_token: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True, index=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(nullable=True)


# ─────────────────── SCHEMAS ───────────────────────────────────────────────

class OfferCreate(BaseModel):
    candidate_id: UUID
    role_title: str = Field(min_length=2, max_length=200)
    base_salary: int = Field(ge=0)
    currency: str = Field(default="AED", max_length=10)
    allowances: dict = Field(default_factory=dict)
    start_date: datetime
    draft_letter: bool = Field(default=True)


class OfferResponse(BaseModel):
    decision: str = Field(pattern=r"^(accept|decline)$")
    note: str | None = Field(default=None, max_length=1000)


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    candidate_id: UUID
    hiring_request_id: UUID
    role_title: str
    base_salary: int
    currency: str
    allowances: dict
    start_date: datetime
    letter_markdown: str | None
    status: str
    approval_request_id: UUID | None
    sent_at: datetime | None
    responded_at: datetime | None
    created_at: datetime


class OfferPublicOut(BaseModel):
    """What the candidate sees on the magic-link page — never exposes approval chain details."""
    role_title: str
    base_salary: int
    currency: str
    allowances: dict
    start_date: datetime
    letter_markdown: str | None
    status: str
    expires_at: datetime | None


# ─────────────────── SERVICE ───────────────────────────────────────────────

TOKEN_TTL_DAYS = 14


async def create_offer(session: AsyncSession, *, actor: User, body: OfferCreate) -> Offer:
    candidate = await session.get(Candidate, body.candidate_id)
    if candidate is None:
        raise NotFound("candidate not found")

    offer = Offer(
        candidate_id=candidate.id,
        hiring_request_id=candidate.hiring_request_id,
        role_title=body.role_title,
        base_salary=body.base_salary,
        currency=body.currency,
        allowances=body.allowances,
        start_date=body.start_date,
        status=OfferStatus.pending_approval,
        created_by=actor.id, updated_by=actor.id,
    )
    session.add(offer)
    await session.flush()

    # Fire approval chain
    approval = await create_approval_request(
        session, DefaultStepResolver(),
        request_type="offer",
        subject_type="offer",
        subject_id=offer.id,
        submitter_user_id=actor.id,
        context={
            "candidate_name": candidate.name,
            "role_title": body.role_title,
            "salary": body.base_salary,
            "currency": body.currency,
        },
    )
    offer.approval_request_id = approval.id

    # Candidate stage
    candidate.stage = CandidateStage.offer

    # AI letter draft
    if body.draft_letter:
        try:
            from alpago.ai import draft_offer_letter
            offer.letter_markdown = await draft_offer_letter(
                candidate_name=candidate.name,
                role_title=body.role_title,
                salary=f"{body.currency} {body.base_salary:,} per month",
                start_date=body.start_date.strftime("%d %B %Y"),
                allowances=body.allowances,
            )
        except Exception:
            offer.letter_markdown = None

    await session.flush()

    await record_audit(
        session, actor=actor, action="offer.created",
        subject_type="offer", subject_id=offer.id,
        after=snapshot(offer, ["role_title", "base_salary", "currency", "status"]),
        context={"candidate_id": str(offer.candidate_id)},
    )
    return offer


async def list_offers(session: AsyncSession, *, candidate_id: UUID | None = None) -> list[Offer]:
    stmt = select(Offer).order_by(Offer.created_at.desc())
    if candidate_id:
        stmt = stmt.where(Offer.candidate_id == candidate_id)
    return list((await session.execute(stmt)).scalars().all())


async def get_offer(session: AsyncSession, offer_id: UUID) -> Offer:
    o = await session.get(Offer, offer_id)
    if o is None:
        raise NotFound("offer not found")
    # Lazy sync: reflect approval chain completion in offer status
    from alpago.modules._approval_sync import sync_status_from_approval
    await sync_status_from_approval(
        session, subject=o,
        pending_value=OfferStatus.pending_approval,
        approved_value=OfferStatus.approved,
        rejected_value=OfferStatus.rejected_internally,
    )
    return o


async def send_offer(session: AsyncSession, offer_id: UUID, actor: User) -> Offer:
    offer = await get_offer(session, offer_id)
    if offer.status != OfferStatus.approved:
        raise ValidationFailed("offer must be approved before sending")
    offer.acceptance_token = token_urlsafe(32)
    offer.token_expires_at = datetime.now(tz=timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    offer.status = OfferStatus.sent
    offer.sent_at = datetime.now(tz=timezone.utc)
    offer.updated_by = actor.id
    await session.flush()

    # Fire notification (fire-and-forget via eager celery in dev)
    try:
        from alpago.notifications import notify
        from alpago.models.notification import NotificationChannel
        candidate = await session.get(Candidate, offer.candidate_id)
        await notify(
            session, user_id=actor.id,  # placeholder — real send goes to candidate email
            template="offer_sent",
            payload={
                "to": candidate.email if candidate else None,
                "candidate_name": candidate.name if candidate else "",
                "role_title": offer.role_title,
                "offer_url": f"/offers/accept/{offer.acceptance_token}",
            },
            channels=(NotificationChannel.email,),
        )
    except Exception:
        pass

    await record_audit(
        session, actor=actor, action="offer.sent",
        subject_type="offer", subject_id=offer.id,
        after=snapshot(offer, ["status", "sent_at"]),
        context={"candidate_id": str(offer.candidate_id)},
    )
    return offer


async def get_offer_by_token(session: AsyncSession, token: str) -> Offer:
    stmt = select(Offer).where(Offer.acceptance_token == token)
    offer = (await session.execute(stmt)).scalar_one_or_none()
    if offer is None:
        raise NotFound("offer link is invalid")
    now = datetime.now(tz=timezone.utc)
    if offer.token_expires_at and offer.token_expires_at < now:
        if offer.status == OfferStatus.sent:
            offer.status = OfferStatus.expired
            await session.flush()
        raise Forbidden("offer link has expired")
    if offer.status not in (OfferStatus.sent, OfferStatus.accepted, OfferStatus.declined):
        raise Forbidden("offer is not available for review")
    return offer


async def respond_to_offer(session: AsyncSession, token: str, body: OfferResponse) -> Offer:
    offer = await get_offer_by_token(session, token)
    if offer.status != OfferStatus.sent:
        raise ValidationFailed(f"offer already {offer.status.value}")

    if body.decision == "accept":
        offer.status = OfferStatus.accepted
        offer.responded_at = datetime.now(tz=timezone.utc)
        candidate = await session.get(Candidate, offer.candidate_id)
        if candidate:
            candidate.stage = CandidateStage.hired
            # Provision a User account for the candidate so they can self-serve post-join
            existing = (await session.execute(
                select(User).where(User.email == candidate.email.lower())
            )).scalar_one_or_none()
            if existing is None:
                session.add(User(
                    email=candidate.email.lower(),
                    name=candidate.name,
                    status=UserStatus.invited,
                    auth_provider=AuthProvider.magic_link,
                ))
    else:
        offer.status = OfferStatus.declined
        offer.responded_at = datetime.now(tz=timezone.utc)
    # Invalidate token
    offer.acceptance_token = None
    await session.flush()

    await record_audit(
        session,
        action="offer.accepted" if offer.status == OfferStatus.accepted else "offer.declined",
        subject_type="offer", subject_id=offer.id,
        after=snapshot(offer, ["status", "responded_at"]),
        context={"candidate_id": str(offer.candidate_id), "by": "candidate"},
    )
    return offer


# ─────────────────── ROUTES ─────────────────────────────────────────────────

router = APIRouter(prefix="/offers", tags=["offers"])


@router.post("", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
async def create(
    body: OfferCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Offer:
    return await create_offer(db, actor=user, body=body)


@router.get("", response_model=list[OfferOut])
async def list_all(
    candidate_id: UUID | None = None,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Offer]:
    return await list_offers(db, candidate_id=candidate_id)


@router.get("/{offer_id}", response_model=OfferOut)
async def get_one(
    offer_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Offer:
    return await get_offer(db, offer_id)


@router.post("/{offer_id}/send", response_model=OfferOut)
async def send_endpoint(
    offer_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Offer:
    return await send_offer(db, offer_id, user)


# ── Public (candidate-facing) endpoints — no auth, token-gated ──

public_router = APIRouter(prefix="/public/offers", tags=["public"])


@public_router.get("/accept/{token}", response_model=OfferPublicOut)
async def public_get(token: str, db: AsyncSession = Depends(get_db)) -> OfferPublicOut:
    offer = await get_offer_by_token(db, token)
    return OfferPublicOut(
        role_title=offer.role_title,
        base_salary=offer.base_salary,
        currency=offer.currency,
        allowances=offer.allowances,
        start_date=offer.start_date,
        letter_markdown=offer.letter_markdown,
        status=offer.status.value,
        expires_at=offer.token_expires_at,
    )


@public_router.post("/accept/{token}", response_model=OfferPublicOut)
async def public_respond(
    token: str, body: OfferResponse, db: AsyncSession = Depends(get_db)
) -> OfferPublicOut:
    offer = await respond_to_offer(db, token, body)
    return OfferPublicOut(
        role_title=offer.role_title,
        base_salary=offer.base_salary,
        currency=offer.currency,
        allowances=offer.allowances,
        start_date=offer.start_date,
        letter_markdown=offer.letter_markdown,
        status=offer.status.value,
        expires_at=offer.token_expires_at,
    )
