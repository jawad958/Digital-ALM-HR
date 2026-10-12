"""Employees module — models, schemas, service, routes in one file.

An employee is created either directly (existing staff) or promoted from an
accepted Offer, which carries the candidate's details across. Each employee
gets an onboarding checklist (IT setup, assets, PRO tasks) that mirrors the
joining flow.

  POST /employees                      create directly
  POST /employees/from-offer/{id}      promote an accepted offer to an employee
  GET  /employees[?status=&department=] list
  GET  /employees/{id}                 detail (+ document completeness)
  PATCH /employees/{id}                update profile
  POST /employees/{id}/status          change employment status
  GET  /employees/{id}/onboarding      checklist
  POST /employees/{id}/onboarding      add a task
  POST /employees/onboarding/{task_id}/complete
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import JSON, Enum as SAEnum, ForeignKey, Integer, String, Uuid, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from alpago.api.deps import current_user, get_db
from alpago.core.audit import record_audit, snapshot
from alpago.core.exceptions import Conflict, NotFound
from alpago.models.base import Auditable, Base, Timestamps, UUIDPK
from alpago.models.user import User


# ─────────────────── MODELS ────────────────────────────────────────────────

class EmploymentStatus(str, Enum):
    onboarding = "onboarding"
    active = "active"
    probation = "probation"
    on_leave = "on_leave"
    notice_period = "notice_period"
    exited = "exited"


class EmploymentType(str, Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    intern = "intern"


class Division(str, Enum):
    """Alpago's own divisions, as printed on the official forms."""
    manufacturing = "manufacturing"
    civil = "civil"
    electro_mechanical = "electro_mechanical"
    operations = "operations"


class OnboardingCategory(str, Enum):
    it = "it"
    assets = "assets"
    hr = "hr"
    pro = "pro"
    finance = "finance"


class Employee(Base, UUIDPK, Timestamps, Auditable):
    __tablename__ = "employees"

    employee_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)

    # Links back into the pipeline (null for staff added directly)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(), ForeignKey("users.id"), nullable=True)
    candidate_id: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True, index=True)
    offer_id: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True, index=True)

    # Personal
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    personal_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    work_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(40), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Job
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    division: Mapped[Division] = mapped_column(
        SAEnum(Division, native_enum=False, length=20),
        default=Division.manufacturing, nullable=False, index=True,
    )
    reports_to_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("employees.id"), nullable=True
    )
    employment_type: Mapped[EmploymentType] = mapped_column(
        SAEnum(EmploymentType, native_enum=False, length=20),
        default=EmploymentType.full_time, nullable=False,
    )
    status: Mapped[EmploymentStatus] = mapped_column(
        SAEnum(EmploymentStatus, native_enum=False, length=20),
        default=EmploymentStatus.onboarding, nullable=False, index=True,
    )

    join_date: Mapped[date | None] = mapped_column(nullable=True)
    probation_end_date: Mapped[date | None] = mapped_column(nullable=True)
    contract_end_date: Mapped[date | None] = mapped_column(nullable=True)
    exit_date: Mapped[date | None] = mapped_column(nullable=True)

    # Compensation
    base_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allowances: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="AED", nullable=False)

    # Compliance identifiers (the documents themselves live in the documents table)
    passport_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    emirates_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    visa_status: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Addresses — the joining form captures both UAE and home country
    uae_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    home_country_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    home_country_mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    work_location: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Dependents and family sponsorship
    dependent_members: Mapped[int | None] = mapped_column(Integer, nullable=True)
    family_visa_status: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Bank details — required to pay through WPS
    bank_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Emergency contact — UAE
    emergency_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emergency_relation: Mapped[str | None] = mapped_column(String(60), nullable=True)
    emergency_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    emergency_address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Emergency contact — home country
    emergency_home_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emergency_home_relation: Mapped[str | None] = mapped_column(String(60), nullable=True)
    emergency_home_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    emergency_home_address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    onboarding_tasks: Mapped[list["OnboardingTask"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan",
        order_by="OnboardingTask.sort_order",
    )

    @property
    def total_package(self) -> int | None:
        if self.base_salary is None:
            return None
        extras = sum(v for v in (self.allowances or {}).values() if isinstance(v, (int, float)))
        return int(self.base_salary + extras)


class OnboardingTask(Base, UUIDPK, Timestamps, Auditable):
    __tablename__ = "onboarding_tasks"

    employee_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[OnboardingCategory] = mapped_column(
        SAEnum(OnboardingCategory, native_enum=False, length=20), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    owner_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    due_date: Mapped[date | None] = mapped_column(nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    completed: Mapped[bool] = mapped_column(default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_by: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="onboarding_tasks")


# The standard joining flow, created automatically for every new employee.
DEFAULT_ONBOARDING: list[tuple[OnboardingCategory, str, str, str]] = [
    (OnboardingCategory.hr, "Signed contract on file", "Collect the countersigned employment contract", "hr_lead"),
    (OnboardingCategory.hr, "Collect personal documents", "Passport, photo, certificates, previous experience letters", "hr_lead"),
    (OnboardingCategory.pro, "Visa application submitted", "Submit entry permit / visa application", "pro"),
    (OnboardingCategory.pro, "Medical fitness test booked", "Book and complete the medical fitness test", "pro"),
    (OnboardingCategory.pro, "Emirates ID application", "Apply for Emirates ID and record the number", "pro"),
    (OnboardingCategory.it, "Create email account", "Provision the @alpagomanufacturing.com mailbox", "it"),
    (OnboardingCategory.it, "System access & accounts", "ERP, shared drive, and project tool access", "it"),
    (OnboardingCategory.assets, "Issue laptop", "Allocate and record the laptop asset tag", "it"),
    (OnboardingCategory.assets, "Issue phone / SIM", "Allocate company phone and SIM if the role requires it", "it"),
    (OnboardingCategory.assets, "Access card & parking", "Issue office access card and parking permit", "hr_lead"),
    (OnboardingCategory.finance, "Bank account & payroll setup", "Register the employee on payroll with bank details", "hr_lead"),
    (OnboardingCategory.hr, "Day-one orientation scheduled", "Book the orientation session and introductions", "hr_lead"),
]


# ─────────────────── SCHEMAS ───────────────────────────────────────────────

class EmployeeCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    job_title: str = Field(min_length=2, max_length=200)
    department: str = Field(min_length=1, max_length=100)
    division: Division = Division.manufacturing
    employment_type: EmploymentType = EmploymentType.full_time
    personal_email: EmailStr | None = None
    work_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    nationality: str | None = Field(default=None, max_length=80)
    date_of_birth: date | None = None
    join_date: date | None = None
    base_salary: int | None = Field(default=None, ge=0)
    allowances: dict = Field(default_factory=dict)
    currency: str = Field(default="AED", max_length=10)
    passport_number: str | None = Field(default=None, max_length=60)
    emirates_id: str | None = Field(default=None, max_length=60)
    emergency_name: str | None = Field(default=None, max_length=200)
    emergency_relation: str | None = Field(default=None, max_length=60)
    emergency_phone: str | None = Field(default=None, max_length=40)
    uae_address: str | None = Field(default=None, max_length=500)
    work_location: str | None = Field(default=None, max_length=200)
    bank_name: str | None = Field(default=None, max_length=200)
    iban: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=2000)
    seed_onboarding: bool = Field(default=True, description="Create the standard joining checklist")


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=100)
    division: Division | None = None
    employment_type: EmploymentType | None = None
    personal_email: EmailStr | None = None
    work_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    whatsapp: str | None = Field(default=None, max_length=40)
    nationality: str | None = Field(default=None, max_length=80)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=20)
    marital_status: str | None = Field(default=None, max_length=20)
    join_date: date | None = None
    probation_end_date: date | None = None
    contract_end_date: date | None = None
    base_salary: int | None = Field(default=None, ge=0)
    allowances: dict | None = None
    passport_number: str | None = Field(default=None, max_length=60)
    emirates_id: str | None = Field(default=None, max_length=60)
    visa_status: str | None = Field(default=None, max_length=60)
    emergency_name: str | None = Field(default=None, max_length=200)
    emergency_relation: str | None = Field(default=None, max_length=60)
    emergency_phone: str | None = Field(default=None, max_length=40)
    uae_address: str | None = None
    home_country_address: str | None = None
    home_country_mobile: str | None = None
    work_location: str | None = None
    dependent_members: int | None = None
    family_visa_status: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    iban: str | None = None
    emergency_address: str | None = None
    emergency_home_name: str | None = None
    emergency_home_relation: str | None = None
    emergency_home_phone: str | None = None
    emergency_home_address: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class StatusChangeIn(BaseModel):
    status: EmploymentStatus
    effective_date: date | None = None
    reason: str | None = Field(default=None, max_length=500)


class OnboardingTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    category: str
    title: str
    description: str | None
    owner_role: str | None
    due_date: date | None
    completed: bool
    completed_at: datetime | None
    sort_order: int


class OnboardingTaskCreate(BaseModel):
    category: OnboardingCategory
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    owner_role: str | None = Field(default=None, max_length=40)
    due_date: date | None = None


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    employee_code: str
    full_name: str
    job_title: str
    department: str
    division: str
    employment_type: str
    status: str
    personal_email: str | None
    work_email: str | None
    phone: str | None
    nationality: str | None
    date_of_birth: date | None
    join_date: date | None
    probation_end_date: date | None
    contract_end_date: date | None
    base_salary: int | None
    allowances: dict
    currency: str
    total_package: int | None = None
    passport_number: str | None
    emirates_id: str | None
    visa_status: str | None
    emergency_name: str | None
    emergency_relation: str | None
    emergency_phone: str | None
    uae_address: str | None = None
    home_country_address: str | None = None
    home_country_mobile: str | None = None
    work_location: str | None = None
    dependent_members: int | None = None
    family_visa_status: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    iban: str | None = None
    emergency_address: str | None = None
    emergency_home_name: str | None = None
    emergency_home_relation: str | None = None
    emergency_home_phone: str | None = None
    emergency_home_address: str | None = None
    candidate_id: UUID | None
    offer_id: UUID | None
    notes: str | None
    created_at: datetime


class EmployeeDetailOut(EmployeeOut):
    onboarding_tasks: list[OnboardingTaskOut] = []
    onboarding_percent: int = 0
    documents_percent: int = 0
    documents_missing: list[str] = []


# ─────────────────── SERVICE ───────────────────────────────────────────────

async def _next_employee_code(session: AsyncSession) -> str:
    count = (await session.execute(select(func.count(Employee.id)))).scalar_one()
    return f"ALP-{count + 1:04d}"


def _seed_tasks(employee_id: UUID, actor_id: UUID | None) -> list[OnboardingTask]:
    return [
        OnboardingTask(
            employee_id=employee_id, category=cat, title=title,
            description=desc, owner_role=owner, sort_order=i,
            created_by=actor_id, updated_by=actor_id,
        )
        for i, (cat, title, desc, owner) in enumerate(DEFAULT_ONBOARDING)
    ]


async def create_employee(
    session: AsyncSession, *, actor: User | None, body: EmployeeCreate
) -> Employee:
    actor_id = getattr(actor, "id", None)
    emp = Employee(
        employee_code=await _next_employee_code(session),
        full_name=body.full_name,
        job_title=body.job_title,
        department=body.department,
        division=body.division,
        employment_type=body.employment_type,
        personal_email=body.personal_email,
        work_email=body.work_email,
        phone=body.phone,
        nationality=body.nationality,
        date_of_birth=body.date_of_birth,
        join_date=body.join_date,
        base_salary=body.base_salary,
        allowances=body.allowances or {},
        currency=body.currency,
        passport_number=body.passport_number,
        emirates_id=body.emirates_id,
        emergency_name=body.emergency_name,
        emergency_relation=body.emergency_relation,
        emergency_phone=body.emergency_phone,
        uae_address=body.uae_address,
        work_location=body.work_location,
        bank_name=body.bank_name,
        iban=body.iban,
        notes=body.notes,
        status=EmploymentStatus.onboarding,
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(emp)
    await session.flush()

    if body.seed_onboarding:
        session.add_all(_seed_tasks(emp.id, actor_id))
        await session.flush()

    await record_audit(
        session, actor=actor, action="employee.created",
        subject_type="employee", subject_id=emp.id,
        after=snapshot(emp, ["employee_code", "full_name", "job_title", "department", "status"]),
    )
    return emp


async def create_from_offer(
    session: AsyncSession, *, actor: User | None, offer_id: UUID
) -> Employee:
    """Promote an accepted offer into an employee record."""
    from alpago.modules.candidates import Candidate
    from alpago.modules.offers import Offer, OfferStatus

    offer = await session.get(Offer, offer_id)
    if offer is None:
        raise NotFound(f"offer {offer_id} not found")
    if offer.status != OfferStatus.accepted:
        raise Conflict("offer must be accepted before creating an employee")

    existing = (
        await session.execute(select(Employee).where(Employee.offer_id == offer_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict(f"employee {existing.employee_code} already exists for this offer")

    from alpago.modules.hiring import HiringRequest

    cand = await session.get(Candidate, offer.candidate_id)
    actor_id = getattr(actor, "id", None)

    # Department lives on the hiring request, not the candidate
    req = await session.get(HiringRequest, offer.hiring_request_id)
    department = getattr(req, "department", None) or "Unassigned"

    emp = Employee(
        employee_code=await _next_employee_code(session),
        candidate_id=offer.candidate_id,
        offer_id=offer.id,
        full_name=getattr(cand, "name", None) or "New joiner",
        personal_email=getattr(cand, "email", None),
        phone=getattr(cand, "phone", None),
        job_title=offer.role_title,
        department=department,
        base_salary=offer.base_salary,
        allowances=offer.allowances or {},
        currency=offer.currency,
        join_date=offer.start_date.date() if isinstance(offer.start_date, datetime) else offer.start_date,
        status=EmploymentStatus.onboarding,
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(emp)
    await session.flush()

    session.add_all(_seed_tasks(emp.id, actor_id))
    await session.flush()

    await record_audit(
        session, actor=actor, action="employee.created_from_offer",
        subject_type="employee", subject_id=emp.id,
        after=snapshot(emp, ["employee_code", "full_name", "job_title"]),
        context={"offer_id": str(offer_id), "candidate_id": str(offer.candidate_id)},
    )
    return emp


async def list_employees(
    session: AsyncSession,
    *,
    status_filter: str | None = None,
    department: str | None = None,
    division: str | None = None,
    q: str | None = None,
) -> list[Employee]:
    stmt = select(Employee).where(Employee.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(Employee.status == status_filter)
    if department:
        stmt = stmt.where(Employee.department == department)
    if division:
        stmt = stmt.where(Employee.division == division)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Employee.full_name).like(like)
            | func.lower(Employee.employee_code).like(like)
            | func.lower(Employee.job_title).like(like)
        )
    stmt = stmt.order_by(Employee.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def get_employee(session: AsyncSession, employee_id: UUID) -> Employee:
    stmt = (
        select(Employee)
        .where(Employee.id == employee_id)
        .options(selectinload(Employee.onboarding_tasks))
    )
    emp = (await session.execute(stmt)).scalar_one_or_none()
    if emp is None or emp.deleted_at is not None:
        raise NotFound(f"employee {employee_id} not found")
    return emp


async def build_detail(session: AsyncSession, emp: Employee) -> EmployeeDetailOut:
    from alpago.modules.documents import OwnerType, checklist_for

    tasks = emp.onboarding_tasks or []
    done = sum(1 for t in tasks if t.completed)
    onboarding_pct = int(round(100 * done / len(tasks))) if tasks else 0

    chk = await checklist_for(session, owner_type=OwnerType.employee, owner_id=emp.id)

    base = EmployeeOut.model_validate(emp).model_dump()
    base["total_package"] = emp.total_package
    return EmployeeDetailOut(
        **base,
        onboarding_tasks=[OnboardingTaskOut.model_validate(t) for t in tasks],
        onboarding_percent=onboarding_pct,
        documents_percent=chk.percent_complete,
        documents_missing=chk.missing,
    )


async def update_employee(
    session: AsyncSession, *, employee_id: UUID, actor: User, body: EmployeeUpdate
) -> Employee:
    emp = await get_employee(session, employee_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return emp

    before = snapshot(emp, list(changes.keys()))
    for field, value in changes.items():
        setattr(emp, field, value)
    emp.updated_by = actor.id
    await session.flush()

    await record_audit(
        session, actor=actor, action="employee.updated",
        subject_type="employee", subject_id=emp.id,
        before=before, after=snapshot(emp, list(changes.keys())),
    )
    return emp


async def change_status(
    session: AsyncSession, *, employee_id: UUID, actor: User, body: StatusChangeIn
) -> Employee:
    emp = await get_employee(session, employee_id)
    before = snapshot(emp, ["status"])
    emp.status = body.status
    if body.status == EmploymentStatus.exited:
        emp.exit_date = body.effective_date or date.today()
    emp.updated_by = actor.id
    await session.flush()

    await record_audit(
        session, actor=actor, action="employee.status_changed",
        subject_type="employee", subject_id=emp.id,
        before=before, after=snapshot(emp, ["status", "exit_date"]),
        context={"reason": body.reason} if body.reason else {},
    )
    return emp


async def add_task(
    session: AsyncSession, *, employee_id: UUID, actor: User, body: OnboardingTaskCreate
) -> OnboardingTask:
    emp = await get_employee(session, employee_id)
    task = OnboardingTask(
        employee_id=emp.id,
        category=body.category,
        title=body.title,
        description=body.description,
        owner_role=body.owner_role,
        due_date=body.due_date,
        sort_order=len(emp.onboarding_tasks or []),
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(task)
    await session.flush()
    await record_audit(
        session, actor=actor, action="onboarding_task.added",
        subject_type="employee", subject_id=emp.id,
        after={"title": task.title, "category": task.category.value},
    )
    return task


async def complete_task(
    session: AsyncSession, *, task_id: UUID, actor: User, done: bool = True
) -> OnboardingTask:
    task = await session.get(OnboardingTask, task_id)
    if task is None:
        raise NotFound(f"onboarding task {task_id} not found")
    task.completed = done
    task.completed_at = datetime.now(tz=timezone.utc) if done else None
    task.completed_by = actor.id if done else None
    task.updated_by = actor.id
    await session.flush()

    await record_audit(
        session, actor=actor,
        action="onboarding_task.completed" if done else "onboarding_task.reopened",
        subject_type="employee", subject_id=task.employee_id,
        after={"title": task.title, "completed": done},
    )

    # When every task is done, move the employee out of onboarding
    if done:
        emp = await get_employee(session, task.employee_id)
        if emp.status == EmploymentStatus.onboarding and all(
            t.completed for t in emp.onboarding_tasks
        ):
            emp.status = EmploymentStatus.active
            await session.flush()
            await record_audit(
                session, actor=actor, action="employee.status_changed",
                subject_type="employee", subject_id=emp.id,
                before={"status": "onboarding"}, after={"status": "active"},
                context={"reason": "onboarding checklist complete"},
            )
    return task


# ─────────────────── ROUTES ────────────────────────────────────────────────

router = APIRouter(prefix="/employees", tags=["employees"])


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create(
    body: EmployeeCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Employee:
    return await create_employee(db, actor=user, body=body)


@router.post("/from-offer/{offer_id}", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def promote_offer(
    offer_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Employee:
    return await create_from_offer(db, actor=user, offer_id=offer_id)


@router.get("", response_model=list[EmployeeOut])
async def list_all(
    status_filter: str | None = None,
    department: str | None = None,
    division: str | None = None,
    q: str | None = None,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EmployeeOut]:
    rows = await list_employees(
        db, status_filter=status_filter, department=department, division=division, q=q
    )
    out = []
    for e in rows:
        item = EmployeeOut.model_validate(e)
        item.total_package = e.total_package
        out.append(item)
    return out


@router.get("/{employee_id}", response_model=EmployeeDetailOut)
async def get_one(
    employee_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> EmployeeDetailOut:
    emp = await get_employee(db, employee_id)
    return await build_detail(db, emp)


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def patch(
    employee_id: UUID,
    body: EmployeeUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Employee:
    return await update_employee(db, employee_id=employee_id, actor=user, body=body)


@router.post("/{employee_id}/status", response_model=EmployeeOut)
async def set_status(
    employee_id: UUID,
    body: StatusChangeIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Employee:
    return await change_status(db, employee_id=employee_id, actor=user, body=body)


@router.get("/{employee_id}/onboarding", response_model=list[OnboardingTaskOut])
async def onboarding(
    employee_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OnboardingTask]:
    emp = await get_employee(db, employee_id)
    return list(emp.onboarding_tasks or [])


@router.post("/{employee_id}/onboarding", response_model=OnboardingTaskOut, status_code=status.HTTP_201_CREATED)
async def add_onboarding_task(
    employee_id: UUID,
    body: OnboardingTaskCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingTask:
    return await add_task(db, employee_id=employee_id, actor=user, body=body)


@router.post("/onboarding/{task_id}/complete", response_model=OnboardingTaskOut)
async def finish_task(
    task_id: UUID,
    done: bool = True,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingTask:
    return await complete_task(db, task_id=task_id, actor=user, done=done)
