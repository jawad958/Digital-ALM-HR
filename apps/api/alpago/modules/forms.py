"""Forms module — Alpago's official HR forms as one engine.

Every paper form HR uses is a FormSubmission: one table, one approval path per
form type, one generic renderer on the front end. Adding a thirteenth form is a
FORM_REGISTRY entry, not new code.

Field schemas are data so the UI can render any form without knowing it exists.
Approval chains mirror the signature blocks on the real documents.

  GET  /forms/definitions            the registry (what the UI renders from)
  GET  /forms/definitions/{key}      one definition
  POST /forms                        submit a form, firing its approval chain
  GET  /forms[?form_type=&status=]   list
  GET  /forms/{id}                   detail
  POST /forms/{id}/acknowledge       employee acknowledgement (warnings, undertakings)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Enum as SAEnum, ForeignKey, String, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from alpago.api.deps import current_user, get_db
from alpago.core.audit import record_audit, snapshot
from alpago.core.exceptions import NotFound, ValidationFailed
from alpago.models.base import Auditable, Base, Timestamps, UUIDPK
from alpago.models.user import User


# ─────────────────── MODELS ────────────────────────────────────────────────

class FormStatus(str, Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    acknowledged = "acknowledged"   # letters the employee has signed off
    completed = "completed"
    cancelled = "cancelled"


class FormCategory(str, Enum):
    request = "request"   # employee or manager asks for something
    letter = "letter"     # HR issues it; the employee acknowledges
    record = "record"     # a record of fact, e.g. dues received


class FormSubmission(Base, UUIDPK, Timestamps, Auditable):
    __tablename__ = "form_submissions"

    form_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    form_code: Mapped[str] = mapped_column(String(60), nullable=False)
    reference: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)

    # Who the form is about (not necessarily who submitted it)
    employee_id: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True, index=True)
    employee_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    status: Mapped[FormStatus] = mapped_column(
        SAEnum(FormStatus, native_enum=False, length=25),
        default=FormStatus.pending_approval, nullable=False, index=True,
    )

    data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    approval_request_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("approval_requests.id"), nullable=True
    )

    acknowledged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    acknowledged_by: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True)
    acknowledgement_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)


# ─────────────────── FORM REGISTRY ─────────────────────────────────────────
# Field types the renderer understands:
#   text · textarea · date · number · currency · select · multiselect
#   checkbox · rating_grid · yesno_grid · table

def _f(key, label, ftype="text", **kw):
    return {"key": key, "label": label, "type": ftype, **kw}


RATING_SCALE = [
    {"value": 5, "label": "5 — Excellent"},
    {"value": 4, "label": "4 — Good"},
    {"value": 3, "label": "3 — Satisfactory"},
    {"value": 2, "label": "2 — Needs improvement"},
    {"value": 1, "label": "1 — Unsatisfactory"},
]

VISA_RENEWAL_CRITERIA = [
    "Attendance & punctuality",
    "Quality of work",
    "Productivity",
    "Technical skills",
    "Compliance with company policies",
    "Teamwork & cooperation",
    "Communication skills",
    "Initiative & problem solving",
    "Safety awareness",
    "Overall performance",
]

INTERVIEW_CRITERIA = [
    "Has the knowledge, skills and abilities to perform the duties of this position",
    "Has the appropriate level of education for this position",
    "Views this position with excitement and enthusiasm",
    "Has the appropriate level of experience necessary for this position",
    "Displayed the ability to communicate well",
    "Should be included in the final list of recommended applicants",
]

AGREEMENT_SCALE = [
    {"value": "strongly_agree", "label": "Strongly agree"},
    {"value": "agree", "label": "Agree"},
    {"value": "disagree", "label": "Disagree"},
    {"value": "undetermined", "label": "Could not determine"},
]

DIVISIONS = [
    {"value": "manufacturing", "label": "Manufacturing"},
    {"value": "civil", "label": "Civil"},
    {"value": "electro_mechanical", "label": "Electro Mechanical"},
]


FORM_REGISTRY: dict[str, dict] = {

    # ── Work from home ────────────────────────────────────────────────────
    "wfh_request": {
        "code": "AG/2025-08/HR/WFH-23",
        "title": "Work From Home Request",
        "category": FormCategory.request,
        "description": "Ad-hoc or recurring remote working arrangement.",
        "raised_by": "Employee",
        "chain": [
            {"role": "initiating_manager", "label": "Line Manager", "scope": "global", "sla_hours": 24},
            {"role": "agm", "label": "Head of Department", "scope": "global", "sla_hours": 24},
            {"role": "hr_lead", "label": "HR Manager", "scope": "global", "sla_hours": 24},
        ],
        "sections": [
            {"title": "Request details", "fields": [
                _f("request_type", "Type of request", "select", required=True, options=[
                    {"value": "adhoc", "label": "Ad-hoc (one-time or short-term)"},
                    {"value": "recurring", "label": "Regular / recurring arrangement"},
                ]),
                _f("reason", "Reason for request", "select", required=True, options=[
                    {"value": "medical", "label": "Medical / personal"},
                    {"value": "operational", "label": "Operational flexibility"},
                    {"value": "caregiving", "label": "Caregiving responsibilities"},
                    {"value": "transport", "label": "Transport / weather disruption"},
                    {"value": "other", "label": "Other"},
                ]),
                _f("reason_other", "If other, please specify"),
                _f("explanation", "Brief explanation", "textarea", required=True),
            ]},
            {"title": "Schedule and work plan", "fields": [
                _f("start_date", "Start date", "date", required=True),
                _f("end_date", "End date", "date", required=True),
                _f("working_hours", "Working hours", placeholder="e.g. 08:00 – 17:00"),
                _f("remarks", "Remarks"),
                _f("task_plan", "Tasks to be carried out during the WFH period", "textarea", required=True),
                _f("reachability", "How you will remain reachable", "textarea", required=True),
            ]},
            {"title": "Declaration", "fields": [
                _f("declaration", "I confirm I have read and understood the company's Work From Home Policy, "
                                  "and will remain available and accessible during official working hours.",
                   "checkbox", required=True),
            ]},
        ],
    },

    # ── Salary increment ──────────────────────────────────────────────────
    "salary_increment": {
        "code": "2025-AG/HR/ER-11",
        "title": "Salary Increment Request",
        "category": FormCategory.request,
        "description": "Employee retention — increment proposal routed to the CEO.",
        "raised_by": "Line Manager",
        "chain": [
            {"role": "agm", "label": "HoD / AGM", "scope": "global", "sla_hours": 48},
            {"role": "gm", "label": "GM Contracting", "scope": "global", "sla_hours": 48},
            {"role": "ceo", "label": "CEO", "scope": "global", "sla_hours": 72},
        ],
        "sections": [
            {"title": "Current position", "fields": [
                _f("date_of_joining", "Date of joining", "date"),
                _f("designation", "Designation", required=True),
                _f("current_salary", "Current salary", "currency", required=True),
                _f("proposed_salary", "Proposed new salary", "currency", required=True),
            ]},
            {"title": "Justification", "fields": [
                _f("case_summary", "Case summary", "textarea", required=True,
                   help="Why this increment, and what happens if it is not approved."),
                _f("line_manager_recommendation", "Line manager recommendation", "textarea", required=True),
            ]},
        ],
    },

    # ── IT asset requisition ──────────────────────────────────────────────
    "it_asset_requisition": {
        "code": "2024-Alpago/IT/AR-001",
        "title": "IT Asset Requisition",
        "category": FormCategory.request,
        "description": "Request a laptop, phone, SIM or other IT equipment.",
        "raised_by": "Employee",
        "chain": [
            {"role": "initiating_manager", "label": "Supervisor / Line Manager", "scope": "global", "sla_hours": 24},
            {"role": "agm", "label": "Head of Department", "scope": "global", "sla_hours": 24},
            {"role": "it", "label": "IT Team", "scope": "global", "sla_hours": 48},
        ],
        "sections": [
            {"title": "Requestor information", "fields": [
                _f("position", "Position", required=True),
                _f("department", "Department", required=True),
                _f("project", "Project", placeholder="ALL"),
                _f("date_required", "Date required by", "date"),
            ]},
            {"title": "Asset requested", "fields": [
                _f("asset_type", "Asset type", "select", required=True, options=[
                    {"value": "laptop", "label": "Laptop / computer"},
                    {"value": "desktop", "label": "Desktop workstation"},
                    {"value": "mobile", "label": "Company mobile"},
                    {"value": "sim", "label": "Company SIM"},
                    {"value": "monitor", "label": "Monitor"},
                    {"value": "printer", "label": "Printer / scanner"},
                    {"value": "software", "label": "Software licence"},
                    {"value": "other", "label": "Other"},
                ]),
                _f("specification", "Specification required", "textarea"),
                _f("justification", "Justification", "textarea", required=True),
            ]},
        ],
    },

    # ── Passport release ──────────────────────────────────────────────────
    "passport_release": {
        "code": "AG/HR/PR-01",
        "title": "Passport Release Request",
        "category": FormCategory.request,
        "description": "Temporary release of a passport held in company safekeeping.",
        "raised_by": "Employee",
        "chain": [
            {"role": "initiating_manager", "label": "Line Manager (verify)", "scope": "global", "sla_hours": 12},
            {"role": "agm", "label": "Head of Department (approve)", "scope": "global", "sla_hours": 24},
        ],
        "sections": [
            {"title": "Passport details", "fields": [
                _f("designation", "Designation"),
                _f("department", "Department"),
                _f("passport_number", "Passport number", required=True),
                _f("passport_code", "Passport code"),
            ]},
            {"title": "Release", "fields": [
                _f("reason", "Reason for release", "textarea", required=True),
                _f("release_date", "Release date", "date", required=True),
                _f("expected_return", "Expected return date", "date", required=True),
                _f("days", "Number of days", "number"),
            ]},
        ],
    },

    # ── Passport safekeeping undertaking ──────────────────────────────────
    "passport_safekeeping": {
        "code": "AG/HR/PS-01",
        "title": "Voluntary Undertaking for Safekeeping of Passport",
        "category": FormCategory.record,
        "description": "Employee voluntarily asks the company to hold their passport. "
                       "Compliant with UAE Federal Decree-Law No. 33 of 2021.",
        "raised_by": "Employee",
        "chain": [
            {"role": "hr_lead", "label": "HR (receive and acknowledge)", "scope": "global", "sla_hours": 24},
        ],
        "sections": [
            {"title": "Employee details", "fields": [
                _f("designation", "Designation"),
                _f("division", "Division", "select", options=DIVISIONS),
                _f("passport_number", "Passport number", required=True),
                _f("nationality", "Nationality", required=True),
            ]},
            {"title": "Undertaking", "fields": [
                _f("voluntary", "I am voluntarily requesting that my passport be held for safekeeping, "
                                "of my own free will and without any coercion.", "checkbox", required=True),
                _f("no_obligation", "I understand I am under no obligation to hand over my passport and that "
                                    "this arrangement is entirely optional.", "checkbox", required=True),
                _f("free_movement", "I confirm this does not restrict my freedom of movement, my right to travel, "
                                    "or my right to resign at any time.", "checkbox", required=True),
                _f("return_on_request", "I understand I may request its return at any time, without justification, "
                                        "ordinarily within one working day.", "checkbox", required=True),
            ]},
        ],
    },

    # ── Visa renewal (doubles as the annual performance review) ───────────
    "visa_renewal": {
        "code": "AG/HR/VR-01",
        "title": "Visa Renewal & Performance Review",
        "category": FormCategory.request,
        "description": "Performance and conduct review that gates visa renewal.",
        "raised_by": "HR",
        "chain": [
            {"role": "initiating_manager", "label": "Head of Department review", "scope": "global", "sla_hours": 72},
            {"role": "agm", "label": "AGM review", "scope": "global", "sla_hours": 72},
        ],
        "sections": [
            {"title": "Employee details", "fields": [
                _f("department", "Department"),
                _f("joining_date", "Joining date", "date"),
                _f("designation", "Designation"),
                _f("visa_expiry_date", "Visa expiry date", "date", required=True),
            ]},
            {"title": "Performance evaluation", "fields": [
                _f("performance", "Rate each criterion", "rating_grid", required=True,
                   rows=VISA_RENEWAL_CRITERIA, scale=RATING_SCALE),
            ]},
            {"title": "Disciplinary & HR record", "fields": [
                _f("discipline", "Conduct during the review period", "yesno_grid", rows=[
                    "Any disciplinary actions during the review period?",
                    "Any written warnings issued?",
                    "Any unauthorised absences?",
                ]),
                _f("discipline_comments", "Comments", "textarea"),
            ]},
            {"title": "Recommendation", "fields": [
                _f("hod_decision", "Head of Department decision", "select", required=True, options=[
                    {"value": "renew", "label": "Renew visa"},
                    {"value": "do_not_renew", "label": "Do not renew visa"},
                ]),
                _f("hod_comments", "Comments", "textarea"),
            ]},
        ],
    },

    # ── Visa confirmation ─────────────────────────────────────────────────
    "visa_confirmation": {
        "code": "2025-AG/HR/VC-15",
        "title": "Visa Confirmation",
        "category": FormCategory.request,
        "description": "Confirm visa type and sponsorship for a new or transferring employee.",
        "raised_by": "HR",
        "chain": [
            {"role": "agm", "label": "Assistant GM", "scope": "global", "sla_hours": 48},
            {"role": "gm", "label": "GM", "scope": "global", "sla_hours": 48},
            {"role": "ceo", "label": "CEO (if required)", "scope": "global", "sla_hours": 72},
        ],
        "sections": [
            {"title": "Employee details", "fields": [
                _f("title", "Title / position", required=True),
                _f("department", "Department / entity", required=True),
                _f("date_of_joining", "Date of joining", "date"),
            ]},
            {"title": "Current visa status", "fields": [
                _f("current_visa_status", "Current status", "select", required=True, options=[
                    {"value": "visit", "label": "Visit visa"},
                    {"value": "cancelled", "label": "Cancelled visa"},
                    {"value": "sponsored", "label": "Sponsored visa"},
                    {"value": "outside_uae", "label": "Outside UAE"},
                ]),
                _f("cancellation_date", "Visa cancellation date (if applicable)", "date"),
            ]},
            {"title": "Visa to be issued", "fields": [
                _f("skill_level", "Classification", "select", required=True, options=[
                    {"value": "skilled", "label": "Skilled"},
                    {"value": "unskilled", "label": "Unskilled"},
                ]),
                _f("visa_type", "Type of visa", "select", required=True, options=[
                    {"value": "resident", "label": "Resident visa"},
                    {"value": "labour_card", "label": "Labour card"},
                ]),
            ]},
        ],
    },

    # ── Disciplinary: verbal warning ──────────────────────────────────────
    "verbal_warning": {
        "code": "AG/HR/VW-01",
        "title": "Verbal Warning Record",
        "category": FormCategory.letter,
        "description": "Formal record that a verbal warning was issued.",
        "raised_by": "HR / Line Manager",
        "requires_acknowledgement": True,
        "chain": [
            {"role": "agm", "label": "Head of Department", "scope": "global", "sla_hours": 48},
        ],
        "sections": [
            {"title": "Employee details", "fields": [
                _f("designation", "Designation"),
                _f("department", "Department / division"),
                _f("employee_code", "Employee code"),
            ]},
            {"title": "Incident", "fields": [
                _f("warning_date", "Date verbal warning issued", "date", required=True),
                _f("incident_date", "Date of incident", "date", required=True),
                _f("project_site", "Project / site"),
                _f("misconduct", "Factual description of the misconduct", "textarea", required=True),
                _f("discussion_date", "Date of discussion held", "date"),
                _f("improvement_required", "Improvement required", "textarea"),
            ]},
        ],
    },

    # ── Disciplinary: written warning ─────────────────────────────────────
    "written_warning": {
        "code": "AG/HR/WW-01",
        "title": "Written Warning Letter",
        "category": FormCategory.letter,
        "description": "Formal written warning. Escalates from a verbal warning.",
        "raised_by": "HR",
        "requires_acknowledgement": True,
        "chain": [
            {"role": "agm", "label": "Head of Department", "scope": "global", "sla_hours": 48},
            {"role": "hr_lead", "label": "HR Manager", "scope": "global", "sla_hours": 24},
        ],
        "sections": [
            {"title": "Employee details", "fields": [
                _f("employee_code", "Employee ID"),
                _f("designation", "Designation"),
                _f("department", "Department"),
            ]},
            {"title": "Warning", "fields": [
                _f("subject", "Subject", required=True,
                   placeholder="Official Warning – Performance Improvement Required"),
                _f("warning_level", "Level", "select", required=True, options=[
                    {"value": "first", "label": "First written warning"},
                    {"value": "second", "label": "Second written warning"},
                    {"value": "final", "label": "Final warning"},
                ]),
                _f("issues", "Issues (one per line)", "textarea", required=True,
                   help="Each line becomes a bullet on the letter."),
                _f("impact", "Impact on the business", "textarea"),
                _f("required_improvement", "Required improvement and timeframe", "textarea", required=True),
            ]},
        ],
    },

    # ── Appreciation letter ───────────────────────────────────────────────
    "appreciation_letter": {
        "code": "AG/HR/AL-01",
        "title": "Appreciation Letter",
        "category": FormCategory.letter,
        "description": "Formal recognition of conduct or performance.",
        "raised_by": "Line Manager / HR",
        "chain": [
            {"role": "agm", "label": "Head of Department", "scope": "global", "sla_hours": 48},
        ],
        "sections": [
            {"title": "Employee details", "fields": [
                _f("designation", "Designation"),
                _f("employee_code", "Employee code"),
                _f("department", "Department"),
            ]},
            {"title": "Recognition", "fields": [
                _f("subject", "Subject", required=True,
                   placeholder="Appreciation for Accountability and Professionalism"),
                _f("occasion_date", "Date of the incident or achievement", "date"),
                _f("body", "What they did and why it matters", "textarea", required=True),
            ]},
        ],
    },

    # ── Dues acknowledgement ──────────────────────────────────────────────
    "dues_acknowledgement": {
        "code": "AG/HR/DA-01",
        "title": "Acknowledgement of Dues Received",
        "category": FormCategory.record,
        "description": "Employee confirms receipt of final settlement or other dues.",
        "raised_by": "HR / Finance",
        "requires_acknowledgement": True,
        "chain": [
            {"role": "hr_lead", "label": "Verified by HR", "scope": "global", "sla_hours": 24},
        ],
        "sections": [
            {"title": "Employee details", "fields": [
                _f("employee_code", "Employee ID"),
                _f("designation", "Designation"),
                _f("division", "Division", "select", options=DIVISIONS),
            ]},
            {"title": "Nature of dues", "fields": [
                _f("nature", "Nature of dues", "multiselect", required=True, options=[
                    {"value": "final_settlement", "label": "Final settlement / end of service dues"},
                    {"value": "salary_arrears", "label": "Salary arrears"},
                    {"value": "expense_reimbursement", "label": "Expense reimbursement"},
                    {"value": "overtime", "label": "Overtime payment"},
                    {"value": "advance_settlement", "label": "Advance settlement"},
                    {"value": "other", "label": "Other"},
                ]),
                _f("nature_other", "If other, please specify"),
            ]},
            {"title": "Breakdown", "fields": [
                _f("breakdown", "Amounts received", "table", required=True,
                   columns=[
                       {"key": "description", "label": "Description", "type": "text"},
                       {"key": "amount", "label": "Amount (AED)", "type": "number"},
                   ],
                   total_column="amount"),
            ]},
            {"title": "Payment", "fields": [
                _f("mode_of_payment", "Mode of payment", "select", required=True, options=[
                    {"value": "bank_transfer", "label": "Bank transfer"},
                    {"value": "cheque", "label": "Cheque"},
                    {"value": "cash", "label": "Cash"},
                    {"value": "wps", "label": "WPS"},
                ]),
                _f("transaction_ref", "Cheque / transaction reference"),
            ]},
        ],
    },
}


ACKNOWLEDGEMENT_TEXT: dict[str, str] = {
    "verbal_warning": "I confirm that I have received and understood this verbal warning record.",
    "written_warning": "I acknowledge receipt and understanding of this warning letter and its consequences.",
    "dues_acknowledgement": (
        "I acknowledge that I have received the above amount in full. I confirm this represents full and "
        "final settlement of the dues stated, and I have no further claim against the Company in respect of the same."
    ),
    "passport_safekeeping": "I sign this undertaking voluntarily in acknowledgement of the above terms.",
}


# ─────────────────── SCHEMAS ───────────────────────────────────────────────

class FormDefinitionOut(BaseModel):
    key: str
    code: str
    title: str
    category: str
    description: str
    raised_by: str
    requires_acknowledgement: bool = False
    acknowledgement_text: str | None = None
    chain: list[dict]
    sections: list[dict]


class FormCreate(BaseModel):
    form_type: str
    employee_id: UUID | None = None
    employee_name: str | None = Field(default=None, max_length=200)
    data: dict = Field(default_factory=dict)


class AcknowledgeIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class FormOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    form_type: str
    form_code: str
    reference: str
    title: str = ""
    category: str = ""
    employee_id: UUID | None
    employee_name: str | None
    status: str
    data: dict
    approval_request_id: UUID | None
    acknowledged_at: datetime | None
    acknowledgement_note: str | None
    created_at: datetime
    created_by: UUID | None

    @classmethod
    def of(cls, s: FormSubmission) -> "FormOut":
        out = cls.model_validate(s)
        definition = FORM_REGISTRY.get(s.form_type, {})
        out.title = definition.get("title", s.form_type)
        cat = definition.get("category")
        out.category = cat.value if isinstance(cat, FormCategory) else str(cat or "")
        return out


# ─────────────────── SERVICE ───────────────────────────────────────────────

def get_definition(key: str) -> dict:
    definition = FORM_REGISTRY.get(key)
    if definition is None:
        raise NotFound(f"unknown form type: {key}")
    return definition


def definition_out(key: str, definition: dict) -> FormDefinitionOut:
    cat = definition["category"]
    return FormDefinitionOut(
        key=key,
        code=definition["code"],
        title=definition["title"],
        category=cat.value if isinstance(cat, FormCategory) else str(cat),
        description=definition.get("description", ""),
        raised_by=definition.get("raised_by", ""),
        requires_acknowledgement=definition.get("requires_acknowledgement", False),
        acknowledgement_text=ACKNOWLEDGEMENT_TEXT.get(key),
        chain=definition.get("chain", []),
        sections=definition.get("sections", []),
    )


def _validate(definition: dict, data: dict) -> None:
    """Check required fields are present. Keeps the paper form's own rules."""
    missing: list[str] = []
    for section in definition.get("sections", []):
        for field in section.get("fields", []):
            if not field.get("required"):
                continue
            value = data.get(field["key"])
            empty = (
                value is None
                or (isinstance(value, str) and not value.strip())
                or (isinstance(value, (list, dict)) and len(value) == 0)
                or (field["type"] == "checkbox" and value is not True)
            )
            if empty:
                missing.append(field["label"])
    if missing:
        raise ValidationFailed("Required fields missing: " + "; ".join(missing[:6]))


async def _next_reference(session: AsyncSession, form_type: str) -> str:
    """ALP-WFH-0007 style reference, unique per form type."""
    prefix = "".join(w[0] for w in form_type.split("_"))[:4].upper()
    count = len((await session.execute(
        select(FormSubmission.id).where(FormSubmission.form_type == form_type)
    )).all())
    return f"ALP-{prefix}-{count + 1:04d}"


async def submit_form(
    session: AsyncSession, *, actor: User, body: FormCreate
) -> FormSubmission:
    definition = get_definition(body.form_type)
    _validate(definition, body.data)

    submission = FormSubmission(
        form_type=body.form_type,
        form_code=definition["code"],
        reference=await _next_reference(session, body.form_type),
        employee_id=body.employee_id,
        employee_name=body.employee_name,
        data=body.data,
        status=FormStatus.pending_approval,
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(submission)
    await session.flush()

    # Fire the form's own approval chain
    if definition.get("chain"):
        from alpago.domain.approvals import create_approval_request
        from alpago.domain.approvals.service import DefaultStepResolver
        try:
            approval = await create_approval_request(
                session,
                DefaultStepResolver(),
                request_type=body.form_type,
                subject_type="form_submission",
                subject_id=submission.id,
                submitter_user_id=actor.id,
                context={
                    "title": definition["title"],
                    "form_code": definition["code"],
                    "reference": submission.reference,
                    "employee_name": body.employee_name,
                },
            )
            submission.approval_request_id = approval.id
            await session.flush()
        except Exception:
            # No chain template seeded for this form yet — keep the submission,
            # it will show under "no approval route" rather than being lost.
            submission.status = FormStatus.draft

    await record_audit(
        session, actor=actor, action="form.submitted",
        subject_type="form_submission", subject_id=submission.id,
        after=snapshot(submission, ["form_type", "reference", "status", "employee_name"]),
        context={"form_code": definition["code"]},
    )
    return submission


async def list_forms(
    session: AsyncSession,
    *,
    form_type: str | None = None,
    status_filter: str | None = None,
    employee_id: UUID | None = None,
) -> list[FormSubmission]:
    stmt = select(FormSubmission).where(FormSubmission.deleted_at.is_(None))
    if form_type:
        stmt = stmt.where(FormSubmission.form_type == form_type)
    if status_filter:
        stmt = stmt.where(FormSubmission.status == status_filter)
    if employee_id:
        stmt = stmt.where(FormSubmission.employee_id == employee_id)
    stmt = stmt.order_by(FormSubmission.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def get_form(session: AsyncSession, form_id: UUID) -> FormSubmission:
    row = await session.get(FormSubmission, form_id)
    if row is None or row.deleted_at is not None:
        raise NotFound(f"form {form_id} not found")

    # Reflect approval completion back onto the form
    if row.approval_request_id and row.status == FormStatus.pending_approval:
        from alpago.modules._approval_sync import sync_status_from_approval
        await sync_status_from_approval(
            session, subject=row,
            pending_value=FormStatus.pending_approval,
            approved_value=FormStatus.approved,
            rejected_value=FormStatus.rejected,
        )
    return row


async def acknowledge_form(
    session: AsyncSession, *, form_id: UUID, actor: User, note: str | None
) -> FormSubmission:
    row = await get_form(session, form_id)
    before = snapshot(row, ["status", "acknowledged_at"])
    row.acknowledged_at = datetime.now(tz=timezone.utc)
    row.acknowledged_by = actor.id
    row.acknowledgement_note = note
    if row.status in (FormStatus.approved, FormStatus.pending_approval):
        row.status = FormStatus.acknowledged
    await session.flush()

    await record_audit(
        session, actor=actor, action="form.acknowledged",
        subject_type="form_submission", subject_id=row.id,
        before=before, after=snapshot(row, ["status", "acknowledged_at"]),
    )
    return row


# ─────────────────── ROUTES ────────────────────────────────────────────────

router = APIRouter(prefix="/forms", tags=["forms"])


@router.get("/definitions", response_model=list[FormDefinitionOut])
async def list_definitions(
    _: User = Depends(current_user),
) -> list[FormDefinitionOut]:
    return [definition_out(k, d) for k, d in FORM_REGISTRY.items()]


@router.get("/definitions/{key}", response_model=FormDefinitionOut)
async def get_one_definition(
    key: str,
    _: User = Depends(current_user),
) -> FormDefinitionOut:
    return definition_out(key, get_definition(key))


@router.post("", response_model=FormOut, status_code=status.HTTP_201_CREATED)
async def create(
    body: FormCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FormOut:
    return FormOut.of(await submit_form(db, actor=user, body=body))


@router.get("", response_model=list[FormOut])
async def list_all(
    form_type: str | None = None,
    form_status: str | None = None,
    employee_id: UUID | None = None,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FormOut]:
    rows = await list_forms(
        db, form_type=form_type, status_filter=form_status, employee_id=employee_id
    )
    return [FormOut.of(r) for r in rows]


@router.get("/{form_id}", response_model=FormOut)
async def get_one(
    form_id: UUID,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FormOut:
    return FormOut.of(await get_form(db, form_id))


@router.post("/{form_id}/acknowledge", response_model=FormOut)
async def acknowledge(
    form_id: UUID,
    body: AcknowledgeIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FormOut:
    return FormOut.of(await acknowledge_form(db, form_id=form_id, actor=user, note=body.note))
