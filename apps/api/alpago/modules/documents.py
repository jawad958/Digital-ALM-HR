"""Documents module — models, schemas, service, routes in one file.

Every document in the business attaches to exactly one owner: an employee or a
candidate. Each owner type has a *required* checklist, so at any moment we can
answer "what is missing for this person?" and "what expires in the next 60 days?"

  POST   /documents                      upload (multipart) against an owner
  GET    /documents                      list, filterable by owner/type/status
  GET    /documents/expiring?days=60     expiry watchlist
  GET    /documents/checklist/{t}/{id}   required-vs-present for one owner
  GET    /documents/{id}                 detail
  GET    /documents/{id}/download        stream the file back
  POST   /documents/{id}/verify          mark verified by HR/PRO
  DELETE /documents/{id}                 soft delete
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Enum as SAEnum, Integer, String, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from alpago.api.deps import current_user, get_db
from alpago.core.audit import record_audit, snapshot
from alpago.core.exceptions import NotFound, ValidationFailed
from alpago.models.base import Auditable, Base, Timestamps, UUIDPK
from alpago.models.user import User


# ─────────────────── MODELS ────────────────────────────────────────────────

class OwnerType(str, Enum):
    employee = "employee"
    candidate = "candidate"


class DocType(str, Enum):
    # Identity
    passport = "passport"
    passport_cover = "passport_cover"
    national_id = "national_id"
    visa = "visa"
    visa_cancellation = "visa_cancellation"
    emirates_id = "emirates_id"
    labour_card = "labour_card"
    photo = "photo"
    # Employment
    offer_letter = "offer_letter"
    contract = "contract"
    noc = "noc"
    salary_certificate = "salary_certificate"
    # Candidate pipeline
    cv = "cv"
    # Credentials
    degree_certificate = "degree_certificate"
    degree_transcript = "degree_transcript"
    experience_letter = "experience_letter"
    trade_licence = "trade_licence"
    # Health & insurance
    medical_fitness = "medical_fitness"
    health_insurance = "health_insurance"
    # Catch-all
    other = "other"


class DocStatus(str, Enum):
    pending_review = "pending_review"
    verified = "verified"
    rejected = "rejected"
    expired = "expired"


# Which doc types each owner type must have on file. Drives the completeness
# percentage on every employee/candidate profile.
REQUIRED_DOCS: dict[OwnerType, list[DocType]] = {
    OwnerType.employee: [
        DocType.passport,
        DocType.visa,
        DocType.emirates_id,
        DocType.contract,
        DocType.photo,
        DocType.medical_fitness,
        DocType.health_insurance,
    ],
    OwnerType.candidate: [
        DocType.cv,
        DocType.passport,
    ],
}


# Named checklists. The default one per owner type comes from REQUIRED_DOCS above;
# these are the specific packs HR collects for a particular process. Notes carry
# the spec HR writes on the paper list, because "a photo" and "a 2x2 inch 600px
# photo on a white background" are not the same request.
CHECKLISTS: dict[str, dict] = {
    "new_visa_application": {
        "title": "New Visa Document List",
        "description": "Everything required to lodge a new employment visa application.",
        "items": [
            {"doc_type": DocType.passport, "required": True,
             "note": "Clear scan. India: 2 pages. Pakistan: full passport scan."},
            {"doc_type": DocType.passport_cover, "required": True,
             "note": "Clear scan of the passport cover."},
            {"doc_type": DocType.national_id, "required": False,
             "note": "Required for Pakistani citizens."},
            {"doc_type": DocType.degree_certificate, "required": False,
             "note": "Clear scan, attested from MOFA UAE, if the candidate holds one."},
            {"doc_type": DocType.degree_transcript, "required": False,
             "note": "Submitted alongside the attested degree."},
            {"doc_type": DocType.visa, "required": True,
             "note": "Proof of current status: employment, sponsor or visit visa. "
                     "A visit visa or cancellation must have at least 20 days validity remaining."},
            {"doc_type": DocType.visa_cancellation, "required": False,
             "note": "For cancelled visas, include the old Emirates ID."},
            {"doc_type": DocType.photo, "required": True,
             "note": "Fresh photo, 2x2 inch (600 pixels), white background."},
        ],
    },
    "employee_file": {
        "title": "Employee File",
        "description": "The standing document set every active employee must have.",
        "items": [
            {"doc_type": dt, "required": True, "note": None}
            for dt in REQUIRED_DOCS[OwnerType.employee]
        ],
    },
    "candidate_file": {
        "title": "Candidate File",
        "description": "Minimum documents to progress a candidate.",
        "items": [
            {"doc_type": dt, "required": True, "note": None}
            for dt in REQUIRED_DOCS[OwnerType.candidate]
        ],
    },
}

# Doc types that carry an expiry date we actively watch.
EXPIRING_TYPES = {
    DocType.passport,
    DocType.visa,
    DocType.emirates_id,
    DocType.labour_card,
    DocType.medical_fitness,
    DocType.health_insurance,
    DocType.trade_licence,
}

DOC_TYPE_LABELS: dict[str, str] = {
    "passport": "Passport",
    "passport_cover": "Passport Cover Page",
    "national_id": "National ID (home country)",
    "visa_cancellation": "Visa Cancellation Proof",
    "visa": "Residence Visa",
    "emirates_id": "Emirates ID",
    "labour_card": "Labour Card",
    "photo": "Passport Photo",
    "offer_letter": "Offer Letter",
    "contract": "Employment Contract",
    "noc": "NOC",
    "salary_certificate": "Salary Certificate",
    "cv": "CV / Résumé",
    "degree_certificate": "Degree Certificate",
    "degree_transcript": "Degree Transcript",
    "experience_letter": "Experience Letter",
    "trade_licence": "Trade Licence",
    "medical_fitness": "Medical Fitness",
    "health_insurance": "Health Insurance",
    "other": "Other",
}

ALLOWED_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_BYTES = 15 * 1024 * 1024


class Document(Base, UUIDPK, Timestamps, Auditable):
    __tablename__ = "documents"

    owner_type: Mapped[OwnerType] = mapped_column(
        SAEnum(OwnerType, native_enum=False, length=20), nullable=False, index=True
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False, index=True)

    doc_type: Mapped[DocType] = mapped_column(
        SAEnum(DocType, native_enum=False, length=40), nullable=False, index=True
    )
    status: Mapped[DocStatus] = mapped_column(
        SAEnum(DocStatus, native_enum=False, length=20),
        default=DocStatus.pending_review, nullable=False, index=True,
    )

    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    # Nullable: HR often knows a document exists and when it expires long before
    # the scan is collected. Those records still belong on the expiry watchlist.
    file_path: Mapped[str | None] = mapped_column(String(600), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Reference data captured off the document itself
    document_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(nullable=True, index=True)
    issuing_country: Mapped[str | None] = mapped_column(String(80), nullable=True)

    verified_by: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)

    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # ── derived ──
    @property
    def days_to_expiry(self) -> int | None:
        if self.expiry_date is None:
            return None
        return (self.expiry_date - date.today()).days

    @property
    def expiry_bucket(self) -> str:
        """none | ok | warn_60 | warn_30 | urgent_7 | expired"""
        d = self.days_to_expiry
        if d is None:
            return "none"
        if d < 0:
            return "expired"
        if d <= 7:
            return "urgent_7"
        if d <= 30:
            return "warn_30"
        if d <= 60:
            return "warn_60"
        return "ok"


# ─────────────────── SCHEMAS ───────────────────────────────────────────────

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    owner_type: str
    owner_id: UUID
    doc_type: str
    doc_type_label: str = ""
    status: str
    filename: str
    content_type: str | None
    size_bytes: int
    has_file: bool = False
    document_number: str | None
    issue_date: date | None
    expiry_date: date | None
    issuing_country: str | None
    verified_at: datetime | None
    notes: str | None
    days_to_expiry: int | None = None
    expiry_bucket: str = "none"
    created_at: datetime

    @classmethod
    def of(cls, d: Document) -> "DocumentOut":
        out = cls.model_validate(d)
        out.has_file = bool(d.file_path)
        out.doc_type_label = DOC_TYPE_LABELS.get(d.doc_type.value, d.doc_type.value)
        out.days_to_expiry = d.days_to_expiry
        out.expiry_bucket = d.expiry_bucket
        return out


class ChecklistItem(BaseModel):
    doc_type: str
    label: str
    required: bool
    present: bool
    note: str | None = None
    status: str | None = None
    document_id: UUID | None = None
    expiry_date: date | None = None
    expiry_bucket: str = "none"


class ChecklistOut(BaseModel):
    name: str = "default"
    title: str = "Required documents"
    description: str = ""
    owner_type: str
    owner_id: UUID
    total_required: int
    present_required: int
    percent_complete: int
    missing: list[str]
    items: list[ChecklistItem]


class VerifyIn(BaseModel):
    approved: bool = True
    notes: str | None = Field(default=None, max_length=1000)


# ─────────────────── SERVICE ───────────────────────────────────────────────

async def _uploads_dir() -> Path:
    base = Path("uploads") / "documents"
    base.mkdir(parents=True, exist_ok=True)
    return base


async def create_document(
    session: AsyncSession,
    *,
    actor: User | None,
    owner_type: OwnerType,
    owner_id: UUID,
    doc_type: DocType,
    upload: UploadFile,
    document_number: str | None = None,
    issue_date: date | None = None,
    expiry_date: date | None = None,
    issuing_country: str | None = None,
    notes: str | None = None,
) -> Document:
    if upload.content_type and upload.content_type not in ALLOWED_TYPES:
        raise ValidationFailed(f"unsupported file type: {upload.content_type}")
    data = await upload.read()
    if len(data) > MAX_BYTES:
        raise ValidationFailed(f"file larger than {MAX_BYTES // 1024 // 1024}MB")
    if not data:
        raise ValidationFailed("file is empty")

    base = await _uploads_dir()
    original = upload.filename or f"{doc_type.value}.bin"
    ext = original.rsplit(".", 1)[-1][:8] if "." in original else "bin"
    stored = base / f"{uuid4()}.{ext}"
    stored.write_bytes(data)

    doc = Document(
        owner_type=owner_type,
        owner_id=owner_id,
        doc_type=doc_type,
        filename=original,
        file_path=str(stored),
        content_type=upload.content_type,
        size_bytes=len(data),
        document_number=document_number,
        issue_date=issue_date,
        expiry_date=expiry_date,
        issuing_country=issuing_country,
        notes=notes,
        status=DocStatus.pending_review,
        created_by=getattr(actor, "id", None),
        updated_by=getattr(actor, "id", None),
    )
    session.add(doc)
    await session.flush()

    await record_audit(
        session, actor=actor, action="document.uploaded",
        subject_type="document", subject_id=doc.id,
        after=snapshot(doc, ["owner_type", "owner_id", "doc_type", "filename", "expiry_date"]),
        context={"owner_type": owner_type.value, "owner_id": str(owner_id)},
    )
    return doc


async def list_documents(
    session: AsyncSession,
    *,
    owner_type: OwnerType | None = None,
    owner_id: UUID | None = None,
    doc_type: DocType | None = None,
    status_filter: DocStatus | None = None,
) -> list[Document]:
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if owner_type:
        stmt = stmt.where(Document.owner_type == owner_type)
    if owner_id:
        stmt = stmt.where(Document.owner_id == owner_id)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)
    stmt = stmt.order_by(Document.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def get_document(session: AsyncSession, doc_id: UUID) -> Document:
    doc = await session.get(Document, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise NotFound(f"document {doc_id} not found")
    return doc


async def expiring_documents(session: AsyncSession, *, days: int = 60) -> list[Document]:
    """Documents already expired or expiring within `days`, soonest first."""
    cutoff = date.today() + timedelta(days=days)
    stmt = (
        select(Document)
        .where(
            Document.deleted_at.is_(None),
            Document.expiry_date.is_not(None),
            Document.expiry_date <= cutoff,
        )
        .order_by(Document.expiry_date.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def checklist_for(
    session: AsyncSession,
    *,
    owner_type: OwnerType,
    owner_id: UUID,
    name: str | None = None,
) -> ChecklistOut:
    """Required-vs-present for one owner.

    `name` picks a named pack from CHECKLISTS (e.g. new_visa_application);
    without it, the standing requirement for that owner type is used.
    """
    docs = await list_documents(session, owner_type=owner_type, owner_id=owner_id)
    by_type: dict[str, Document] = {}
    for d in docs:
        # Keep the newest of each type
        if d.doc_type.value not in by_type:
            by_type[d.doc_type.value] = d

    if name:
        spec = CHECKLISTS.get(name)
        if spec is None:
            raise NotFound(f"unknown checklist: {name}")
        plan = spec["items"]
        title, description = spec["title"], spec["description"]
    else:
        plan = [
            {"doc_type": dt, "required": True, "note": None}
            for dt in REQUIRED_DOCS.get(owner_type, [])
        ]
        title, description = "Required documents", ""
        name = "default"

    items: list[ChecklistItem] = []
    planned_keys: set[str] = set()

    for entry in plan:
        dt = entry["doc_type"]
        key = dt.value if isinstance(dt, DocType) else str(dt)
        planned_keys.add(key)
        doc = by_type.get(key)
        items.append(ChecklistItem(
            doc_type=key,
            label=DOC_TYPE_LABELS.get(key, key),
            required=entry.get("required", True),
            note=entry.get("note"),
            present=doc is not None,
            status=doc.status.value if doc else None,
            document_id=doc.id if doc else None,
            expiry_date=doc.expiry_date if doc else None,
            expiry_bucket=doc.expiry_bucket if doc else "none",
        ))

    # Anything on file beyond the plan still shows, marked optional
    for key, doc in by_type.items():
        if key in planned_keys:
            continue
        items.append(ChecklistItem(
            doc_type=key,
            label=DOC_TYPE_LABELS.get(key, key),
            required=False,
            present=True,
            status=doc.status.value,
            document_id=doc.id,
            expiry_date=doc.expiry_date,
            expiry_bucket=doc.expiry_bucket,
        ))

    required_items = [i for i in items if i.required]
    present_required = sum(1 for i in required_items if i.present)
    total_required = len(required_items)
    pct = int(round(100 * present_required / total_required)) if total_required else 100

    return ChecklistOut(
        name=name,
        title=title,
        description=description,
        owner_type=owner_type.value,
        owner_id=owner_id,
        total_required=total_required,
        present_required=present_required,
        percent_complete=pct,
        missing=[i.label for i in required_items if not i.present],
        items=items,
    )


async def verify_document(
    session: AsyncSession, *, doc_id: UUID, actor: User, approved: bool, notes: str | None
) -> Document:
    doc = await get_document(session, doc_id)
    before = snapshot(doc, ["status", "verified_at"])
    doc.status = DocStatus.verified if approved else DocStatus.rejected
    doc.verified_by = actor.id
    doc.verified_at = datetime.now(tz=timezone.utc)
    if notes:
        doc.notes = notes
    doc.updated_by = actor.id
    await session.flush()

    await record_audit(
        session, actor=actor,
        action="document.verified" if approved else "document.rejected",
        subject_type="document", subject_id=doc.id,
        before=before, after=snapshot(doc, ["status", "verified_at"]),
    )
    return doc


async def soft_delete_document(session: AsyncSession, *, doc_id: UUID, actor: User) -> None:
    doc = await get_document(session, doc_id)
    doc.deleted_at = datetime.now(tz=timezone.utc)
    doc.updated_by = actor.id
    await session.flush()
    await record_audit(
        session, actor=actor, action="document.deleted",
        subject_type="document", subject_id=doc.id,
        before=snapshot(doc, ["filename", "doc_type"]),
    )


async def mark_expired_documents(session: AsyncSession) -> int:
    """Flip anything past its expiry date to `expired`. Returns the count."""
    stmt = select(Document).where(
        Document.deleted_at.is_(None),
        Document.expiry_date.is_not(None),
        Document.expiry_date < date.today(),
        Document.status != DocStatus.expired,
    )
    rows = list((await session.execute(stmt)).scalars().all())
    for d in rows:
        d.status = DocStatus.expired
    if rows:
        await session.flush()
    return len(rows)


# ─────────────────── ROUTES ────────────────────────────────────────────────

router = APIRouter(prefix="/documents", tags=["documents"])


def _parse_date(value: str | None) -> date | None:
    """Multipart fields arrive as strings; an untouched date input sends ''."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationFailed(f"invalid date: {value!r} (expected YYYY-MM-DD)")


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    owner_type: OwnerType = Form(...),
    owner_id: UUID = Form(...),
    doc_type: DocType = Form(...),
    file: UploadFile = File(...),
    document_number: str | None = Form(default=None),
    issue_date: str | None = Form(default=None),
    expiry_date: str | None = Form(default=None),
    issuing_country: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    doc = await create_document(
        db, actor=user, owner_type=owner_type, owner_id=owner_id,
        doc_type=doc_type, upload=file, document_number=document_number,
        issue_date=_parse_date(issue_date), expiry_date=_parse_date(expiry_date),
        issuing_country=issuing_country, notes=notes,
    )
    return DocumentOut.of(doc)


@router.get("", response_model=list[DocumentOut])
async def list_all(
    owner_type: OwnerType | None = None,
    owner_id: UUID | None = None,
    doc_type: DocType | None = None,
    doc_status: DocStatus | None = None,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentOut]:
    rows = await list_documents(
        db, owner_type=owner_type, owner_id=owner_id,
        doc_type=doc_type, status_filter=doc_status,
    )
    return [DocumentOut.of(d) for d in rows]


@router.get("/expiring", response_model=list[DocumentOut])
async def expiring(
    days: int = Query(default=60, ge=1, le=365),
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentOut]:
    return [DocumentOut.of(d) for d in await expiring_documents(db, days=days)]


@router.get("/checklists")
async def list_checklists(_: User = Depends(current_user)) -> list[dict]:
    """The named document packs HR collects for a given process."""
    return [
        {
            "name": key,
            "title": spec["title"],
            "description": spec["description"],
            "item_count": len(spec["items"]),
            "required_count": sum(1 for i in spec["items"] if i.get("required")),
        }
        for key, spec in CHECKLISTS.items()
    ]


@router.get("/checklist/{owner_type}/{owner_id}", response_model=ChecklistOut)
async def checklist(
    owner_type: OwnerType,
    owner_id: UUID,
    name: str | None = Query(default=None, description="A named pack from /documents/checklists"),
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ChecklistOut:
    return await checklist_for(db, owner_type=owner_type, owner_id=owner_id, name=name)


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_one(
    doc_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    return DocumentOut.of(await get_document(db, doc_id))


@router.get("/{doc_id}/download")
async def download(
    doc_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await get_document(db, doc_id)
    if not doc.file_path:
        raise NotFound(
            "No scan on file for this document. Its details were recorded from the "
            "HR register; upload the scan to attach it."
        )
    path = Path(doc.file_path)
    if not path.exists():
        raise NotFound("file missing from storage")
    return FileResponse(
        path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.filename,
    )


@router.post("/{doc_id}/verify", response_model=DocumentOut)
async def verify(
    doc_id: UUID,
    body: VerifyIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    doc = await verify_document(
        db, doc_id=doc_id, actor=user, approved=body.approved, notes=body.notes
    )
    return DocumentOut.of(doc)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    doc_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await soft_delete_document(db, doc_id=doc_id, actor=user)
