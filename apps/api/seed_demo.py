"""Seed the database with demo data for every module.

Run from apps/api with the venv active:

    python seed_demo.py            # wipe demo data and reseed
    python seed_demo.py --keep     # add to what is already there

Creates a login for every role (all share one password, printed at the end),
plus hiring requests, candidates, interviews, offers, employees and documents
in a spread of states so every screen has something real on it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select

from alpago.core.database import db_session
from alpago.core.security import hash_password

# Importing the modules registers their tables on the shared Base.
from alpago.models.approval import (
    ApprovalChainTemplate,
    ApprovalRequest,
    ApprovalStep,
)
from alpago.models.audit import AuditLog
from alpago.models.department import Department
from alpago.models.role import Role, UserRole
from alpago.models.user import AuthProvider, User, UserStatus
from alpago.modules.candidates import Candidate, CandidateStage, Cv
from alpago.modules.documents import DocStatus, DocType, Document, OwnerType
from alpago.modules.forms import FormStatus, FormSubmission
from alpago.modules.employees import (
    DEFAULT_ONBOARDING,
    Division,
    Employee,
    EmploymentStatus,
    EmploymentType,
    OnboardingTask,
)
from alpago.modules.hiring import HiringRequest, HiringRequestStatus
from alpago.modules.interviews import (
    IEF_CRITERIA_KEYS,
    Interview,
    InterviewEvaluation,
    InterviewMode,
    InterviewStatus,
)
from alpago.modules.offers import Offer, OfferStatus


PASSWORD = "Alpago@2026"
NOW = datetime.now(tz=timezone.utc)
TODAY = date.today()


# ─────────────────── reference data ────────────────────────────────────────

ROLES: list[tuple[str, str, str]] = [
    ("admin", "Administrator", "Full access to every module and setting"),
    ("ceo", "Chief Executive Officer", "Final approver on hiring and offers"),
    ("gm", "General Manager", "Second-line approver"),
    ("agm", "Assistant General Manager", "First-line approver"),
    ("hr_lead", "Head of HR", "Owns the HR process end to end"),
    ("ta", "Talent Acquisition", "Sources and screens candidates"),
    ("pro", "PRO / Government Relations", "Visas, Emirates ID, labour cards"),
    ("it", "IT Administrator", "Accounts, equipment, system access"),
    ("initiating_manager", "Department Manager", "Raises hiring requests"),
    ("employee", "Employee", "Self-service access only"),
]

USERS: list[tuple[str, str, list[str]]] = [
    ("jawad@alpagomanufacturing.com", "Jawad", ["admin", "hr_lead"]),
    ("ceo@alpagomanufacturing.com", "Khalid Al Nuaimi", ["ceo"]),
    ("gm@alpagomanufacturing.com", "Marwan Haddad", ["gm"]),
    ("agm@alpagomanufacturing.com", "Rania Fakhoury", ["agm"]),
    ("hr@alpagomanufacturing.com", "Sarah Haddad", ["hr_lead"]),
    ("ta@alpagomanufacturing.com", "Omar Siddiqui", ["ta"]),
    ("pro@alpagomanufacturing.com", "Ahmed Mansoor", ["pro"]),
    ("it@alpagomanufacturing.com", "Vikram Rao", ["it"]),
    ("manager@alpagomanufacturing.com", "Layla Noor", ["initiating_manager"]),
    ("employee@alpagomanufacturing.com", "Yusuf Karim", ["employee"]),
]

# Alpago's own departments, as they appear on the official forms
DEPARTMENTS = [
    ("Joinery", "manufacturing"),
    ("MEP", "electro_mechanical"),
    ("Civil Works", "civil"),
    ("Quantity Surveying", "civil"),
    ("Estimation", "civil"),
    ("Procurement", "manufacturing"),
    ("Finance", "manufacturing"),
    ("Human Resources", "manufacturing"),
    ("Information Technology", "manufacturing"),
]

# Initiator → AGM → GM → CEO
CHAINS: list[tuple[str, str, list[dict]]] = [
    ("hiring_request", "Hiring request — standard", [
        {"role": "agm", "scope": "global", "sla_hours": 24},
        {"role": "gm", "scope": "global", "sla_hours": 24},
        {"role": "ceo", "scope": "global", "sla_hours": 48},
    ]),
    ("offer", "Offer approval — standard", [
        {"role": "hr_lead", "scope": "global", "sla_hours": 12},
        {"role": "agm", "scope": "global", "sla_hours": 24},
        {"role": "ceo", "scope": "global", "sla_hours": 24},
    ]),
]

# Each official form routes the way its own signature block does.
FORM_CHAINS: list[tuple[str, str, list[dict]]] = [
    ("wfh_request", "WFH request — LM, HoD, HR", [
        {"role": "initiating_manager", "scope": "global", "sla_hours": 24},
        {"role": "agm", "scope": "global", "sla_hours": 24},
        {"role": "hr_lead", "scope": "global", "sla_hours": 24},
    ]),
    ("salary_increment", "Salary increment — AGM, GM, CEO", [
        {"role": "agm", "scope": "global", "sla_hours": 48},
        {"role": "gm", "scope": "global", "sla_hours": 48},
        {"role": "ceo", "scope": "global", "sla_hours": 72},
    ]),
    ("it_asset_requisition", "IT asset — LM, HoD, IT", [
        {"role": "initiating_manager", "scope": "global", "sla_hours": 24},
        {"role": "agm", "scope": "global", "sla_hours": 24},
        {"role": "it", "scope": "global", "sla_hours": 48},
    ]),
    ("passport_release", "Passport release — LM verify, HoD approve", [
        {"role": "initiating_manager", "scope": "global", "sla_hours": 12},
        {"role": "agm", "scope": "global", "sla_hours": 24},
    ]),
    ("passport_safekeeping", "Passport safekeeping — HR receives", [
        {"role": "hr_lead", "scope": "global", "sla_hours": 24},
    ]),
    ("visa_renewal", "Visa renewal — HoD, AGM", [
        {"role": "initiating_manager", "scope": "global", "sla_hours": 72},
        {"role": "agm", "scope": "global", "sla_hours": 72},
    ]),
    ("visa_confirmation", "Visa confirmation — AGM, GM, CEO", [
        {"role": "agm", "scope": "global", "sla_hours": 48},
        {"role": "gm", "scope": "global", "sla_hours": 48},
        {"role": "ceo", "scope": "global", "sla_hours": 72},
    ]),
    ("verbal_warning", "Verbal warning — HoD", [
        {"role": "agm", "scope": "global", "sla_hours": 48},
    ]),
    ("written_warning", "Written warning — HoD, HR", [
        {"role": "agm", "scope": "global", "sla_hours": 48},
        {"role": "hr_lead", "scope": "global", "sla_hours": 24},
    ]),
    ("appreciation_letter", "Appreciation letter — HoD", [
        {"role": "agm", "scope": "global", "sla_hours": 48},
    ]),
    ("dues_acknowledgement", "Dues acknowledgement — HR verifies", [
        {"role": "hr_lead", "scope": "global", "sla_hours": 24},
    ]),
]


# ─────────────────── tiny PDF writer (no external deps) ────────────────────

def _pdf_bytes(title: str, lines: list[str]) -> bytes:
    """Build a minimal but valid single-page PDF."""
    def esc(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content = ["BT", "/F1 16 Tf", "60 760 Td", f"({esc(title)}) Tj", "/F1 11 Tf"]
    for ln in lines:
        content.append("0 -22 Td")
        content.append(f"({esc(ln)}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", "replace")

    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _write_doc_file(folder: Path, name: str, title: str, lines: list[str]) -> tuple[Path, int]:
    folder.mkdir(parents=True, exist_ok=True)
    data = _pdf_bytes(title, lines)
    path = folder / name
    path.write_bytes(data)
    return path, len(data)


# ─────────────────── wipe ──────────────────────────────────────────────────

async def guard_real_data(session, force: bool) -> None:
    """Refuse to wipe a database that looks like it holds the real register.

    seed_demo deletes everything. Once import_employees.py has run, that is
    184 real staff records, so make destroying them deliberate.
    """
    from sqlalchemy import func
    count = (await session.execute(select(func.count(Employee.id)))).scalar_one()
    if count > 20 and not force:
        print(
            f"\n  REFUSING TO WIPE: {count} employees are on file, which looks like\n"
            f"  the imported register rather than demo data.\n\n"
            f"  To reseed anyway:   python seed_demo.py --force\n"
            f"  To keep both:       python seed_demo.py --keep\n"
        )
        raise SystemExit(1)


async def wipe(session) -> None:
    """Clear transactional data. Users/roles are rebuilt from scratch too."""
    for model in (
        AuditLog, FormSubmission, Document, OnboardingTask, Employee,
        Offer, InterviewEvaluation, Interview, Cv, Candidate,
        ApprovalStep, ApprovalRequest, HiringRequest,
        ApprovalChainTemplate, UserRole, Department, Role,
    ):
        await session.execute(delete(model))
    await session.execute(delete(User))
    await session.flush()
    print("  cleared existing data")


# ─────────────────── seed ──────────────────────────────────────────────────

async def seed(keep: bool, force: bool = False) -> None:
    async with db_session() as s:
        if not keep:
            await guard_real_data(s, force)
            await wipe(s)

        # ── roles ──
        roles: dict[str, Role] = {}
        for key, name, desc in ROLES:
            existing = (
                await s.execute(select(Role).where(Role.key == key))
            ).scalar_one_or_none()
            if existing is None:
                existing = Role(key=key, name=name, description=desc)
                s.add(existing)
            roles[key] = existing
        await s.flush()
        print(f"  {len(roles)} roles")

        # ── users ──
        users: dict[str, User] = {}
        for email, name, role_keys in USERS:
            u = (
                await s.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if u is None:
                u = User(
                    email=email, name=name,
                    status=UserStatus.active,
                    auth_provider=AuthProvider.password,
                    password_hash=hash_password(PASSWORD),
                )
                s.add(u)
                await s.flush()
            else:
                u.password_hash = hash_password(PASSWORD)
            users[email] = u

            for rk in role_keys:
                link = (
                    await s.execute(
                        select(UserRole).where(
                            UserRole.user_id == u.id, UserRole.role_id == roles[rk].id
                        )
                    )
                ).scalar_one_or_none()
                if link is None:
                    s.add(UserRole(user_id=u.id, role_id=roles[rk].id, scope_key=None, scope={}))
        await s.flush()
        print(f"  {len(users)} users with role assignments")

        jawad = users["jawad@alpagomanufacturing.com"]
        hr = users["hr@alpagomanufacturing.com"]
        ta = users["ta@alpagomanufacturing.com"]
        agm = users["agm@alpagomanufacturing.com"]
        gm = users["gm@alpagomanufacturing.com"]
        ceo = users["ceo@alpagomanufacturing.com"]
        manager = users["manager@alpagomanufacturing.com"]

        # ── departments ──
        for dname, div in DEPARTMENTS:
            dkey = dname.lower().replace(" & ", "_").replace(" ", "_")
            exists = (
                await s.execute(select(Department).where(Department.key == dkey))
            ).scalar_one_or_none()
            if exists is None:
                s.add(Department(name=dname, key=dkey))
        await s.flush()
        print(f"  {len(DEPARTMENTS)} departments")

        # ── approval chain templates ──
        for req_type, cname, steps in CHAINS:
            exists = (
                await s.execute(
                    select(ApprovalChainTemplate).where(
                        ApprovalChainTemplate.request_type == req_type
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                s.add(ApprovalChainTemplate(
                    request_type=req_type, name=cname, steps=steps, active=True
                ))
        for req_type, cname, steps in FORM_CHAINS:
            exists = (
                await s.execute(
                    select(ApprovalChainTemplate).where(
                        ApprovalChainTemplate.request_type == req_type
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                s.add(ApprovalChainTemplate(
                    request_type=req_type, name=cname, steps=steps, active=True
                ))
        await s.flush()
        print(f"  {len(CHAINS) + len(FORM_CHAINS)} approval chains (incl. one per official form)")

        # ── hiring requests (via the service so chains fire for real) ──
        from alpago.modules.hiring import HiringRequestCreate, create_hiring_request

        hr_specs = [
            ("Senior Site Engineer", "Contracting", "senior", 2, 26000, 32000,
             "Two new towers starting in Q1; current team is at capacity.", manager),
            ("Procurement Officer", "Procurement", "mid", 1, 14000, 18000,
             "Replacing Fatima who resigned last month.", manager),
            ("Draughtsman (Revit)", "Design & Drawing Office", "mid", 1, 12000, 16000,
             "Drawing office backlog is pushing handover dates.", manager),
            ("HR Officer", "Human Resources", "junior", 1, 9000, 12000,
             "Support the new HR platform rollout.", hr),
        ]
        requests: list[HiringRequest] = []
        for title, dept, sen, pos, smin, smax, why, submitter in hr_specs:
            req = await create_hiring_request(
                s, submitter=submitter,
                body=HiringRequestCreate(
                    role_title=title, department=dept, seniority=sen, positions=pos,
                    salary_min=smin, salary_max=smax, justification=why,
                    target_start_date=NOW + timedelta(days=45),
                    generate_jd=False,
                ),
            )
            req.jd_markdown = _sample_jd(title, dept, sen)
            requests.append(req)
        await s.flush()
        print(f"  {len(requests)} hiring requests (approval chains fired)")

        # Walk the first request through AGM + GM so the chain shows real progress
        from alpago.domain.approvals import ApprovalDecision, decide_step
        from alpago.domain.approvals.service import DefaultStepResolver

        first = requests[0]
        apr = await s.get(ApprovalRequest, first.approval_request_id)
        if apr is not None:
            await s.refresh(apr, attribute_names=["steps"])
            for step in sorted(apr.steps, key=lambda x: x.step_index)[:2]:
                if step.approver_user_id:
                    await decide_step(
                        s, DefaultStepResolver(), step_id=step.id,
                        decision=ApprovalDecision.approve,
                        actor_user_id=step.approver_user_id,
                        comment="Approved — budget confirmed.",
                    )
            print("    request #1 approved through AGM and GM, now with the CEO")

        # Fully approve request #3 so it can carry a candidate pipeline
        third = requests[2]
        apr3 = await s.get(ApprovalRequest, third.approval_request_id)
        if apr3 is not None:
            await s.refresh(apr3, attribute_names=["steps"])
            for step in sorted(apr3.steps, key=lambda x: x.step_index):
                await s.refresh(apr3, attribute_names=["steps"])
                live = next((x for x in apr3.steps if x.id == step.id), None)
                if live and live.approver_user_id:
                    await decide_step(
                        s, DefaultStepResolver(), step_id=live.id,
                        decision=ApprovalDecision.approve,
                        actor_user_id=live.approver_user_id,
                        comment="Go ahead.",
                    )
            third.status = HiringRequestStatus.sourcing
            await s.flush()
            print("    request #3 fully approved → sourcing")

        # ── candidates ──
        cand_specs = [
            (requests[0], "Lina Nasser", "lina.nasser@example.com", "+971 50 112 3344",
             "Site Engineer, Emaar", 9, 31000, CandidateStage.interviewing, 82),
            (requests[0], "Rahul Menon", "rahul.menon@example.com", "+971 55 998 1122",
             "Senior Engineer, DAMAC", 11, 33000, CandidateStage.shortlisted, 76),
            (requests[0], "Tareq Bilal", "tareq.bilal@example.com", "+971 52 441 7788",
             "Project Engineer, Arabtec", 6, 27000, CandidateStage.screened, 61),
            (requests[2], "Priya Sharma", "priya.sharma@example.com", "+971 56 220 9090",
             "Revit Draughtsman, AECOM", 7, 15000, CandidateStage.offer, 88),
            (requests[1], "Hassan Noor", "hassan.noor@example.com", "+971 50 777 6655",
             "Buyer, Al Futtaim", 5, 16000, CandidateStage.sourced, None),
        ]
        candidates: list[Candidate] = []
        cand_scores: dict = {}
        for req, name, email, phone, role_now, yrs, expected, stage, score in cand_specs:
            c = Candidate(
                hiring_request_id=req.id, name=name, email=email, phone=phone,
                source="direct", current_role=role_now, years_experience=yrs,
                expected_salary=expected, stage=stage,
                visa_status="Employment visa (transferable)" if yrs > 7 else "Visit visa",
                joining_availability="Immediate" if yrs > 7 else "30 days notice",
                created_by=ta.id, updated_by=ta.id,
            )
            s.add(c)
            candidates.append(c)
            cand_scores[name] = score
        await s.flush()
        print(f"  {len(candidates)} candidates")

        # ── interviews + evaluations ──
        lina, rahul, _tareq, priya, _hassan = candidates
        iv_specs = [
            (lina, "Technical round", -5, InterviewStatus.completed, 4, "recommend"),
            (lina, "Panel with AGM", 3, InterviewStatus.scheduled, None, None),
            (rahul, "Technical round", 2, InterviewStatus.scheduled, None, None),
            (priya, "Portfolio review", -9, InterviewStatus.completed, 5, "recommend"),
        ]
        iv_count = 0
        for cand, round_name, day_offset, st, score, verdict in iv_specs:
            iv = Interview(
                candidate_id=cand.id,
                hiring_request_id=cand.hiring_request_id,
                round_name=round_name,
                scheduled_at=NOW + timedelta(days=day_offset),
                duration_minutes=60, mode=InterviewMode.video,
                location_or_link="https://meet.google.com/alpago-demo",
                interviewer_user_ids=[str(agm.id)],
                status=st, created_by=ta.id, updated_by=ta.id,
            )
            s.add(iv)
            await s.flush()
            iv_count += 1

            if score is not None:
                # IEF 1.2 agreement responses rather than ad-hoc numeric scores
                agreement = "strongly_agree" if score >= 5 else "agree"
                s.add(InterviewEvaluation(
                    interview_id=iv.id,
                    interviewer_user_id=agm.id,
                    scores={k: agreement for k in IEF_CRITERIA_KEYS},
                    relevant_industry_experience=True,
                    uae_work_experience=True,
                    strengths="Strong hands-on experience on comparable projects. "
                              "Communicates clearly and handled the technical questions well.",
                    areas_for_improvement="Limited exposure to our ERP; would need onboarding on reporting.",
                    additional_comments="Available at short notice.",
                    overall_score=5 if score >= 5 else 4,
                    verdict=verdict,
                    created_by=agm.id, updated_by=agm.id,
                ))
        await s.flush()
        print(f"  {iv_count} interviews with evaluations")

        # ── offers ──
        offer = Offer(
            candidate_id=priya.id,
            hiring_request_id=priya.hiring_request_id,
            role_title="Draughtsman (Revit)",
            base_salary=15000, currency="AED",
            allowances={"housing": 3500, "transport": 1000},
            start_date=NOW + timedelta(days=30),
            status=OfferStatus.accepted,
            responded_at=NOW - timedelta(days=3),
            sent_at=NOW - timedelta(days=6),
            created_by=hr.id, updated_by=hr.id,
        )
        s.add(offer)

        pending_offer = Offer(
            candidate_id=lina.id,
            hiring_request_id=lina.hiring_request_id,
            role_title="Senior Site Engineer",
            base_salary=30000, currency="AED",
            allowances={"housing": 6000, "transport": 1500},
            start_date=NOW + timedelta(days=45),
            status=OfferStatus.pending_approval,
            created_by=hr.id, updated_by=hr.id,
        )
        s.add(pending_offer)
        await s.flush()
        print("  2 offers (1 accepted, 1 pending approval)")

        # ── employees ──
        docs_dir = Path("uploads") / "documents"
        emp_specs = [
            ("Sarah Haddad", "Head of Human Resources", "Human Resources",
             Division.manufacturing, EmploymentStatus.active, -1200, 28000,
             {"housing": 7000, "transport": 1500}, "Lebanese", True),
            ("Ahmed Mansoor", "PRO / Government Relations", "Human Resources",
             Division.manufacturing, EmploymentStatus.active, -900, 14000,
             {"housing": 3500, "transport": 1200}, "Emirati", True),
            ("Vikram Rao", "IT Administrator", "Operations",
             Division.manufacturing, EmploymentStatus.active, -640, 16000,
             {"housing": 4000}, "Indian", True),
            ("Layla Noor", "Contracts Manager", "Contracting",
             Division.civil, EmploymentStatus.active, -1800, 34000,
             {"housing": 8000, "transport": 2000}, "Jordanian", True),
            ("Yusuf Karim", "Quantity Surveyor", "Contracting",
             Division.civil, EmploymentStatus.probation, -75, 19000,
             {"housing": 4500}, "Pakistani", True),
            ("Priya Sharma", "Draughtsman (Revit)", "Design & Drawing Office",
             Division.manufacturing, EmploymentStatus.onboarding, 30, 15000,
             {"housing": 3500, "transport": 1000}, "Indian", False),
        ]

        employees: list[Employee] = []
        for i, (name, title, dept, div, st, join_offset, salary, allow, nat, complete_docs) in enumerate(emp_specs, start=1):
            emp = Employee(
                employee_code=f"ALP-{i:04d}",
                full_name=name, job_title=title, department=dept, division=div,
                employment_type=EmploymentType.full_time, status=st,
                personal_email=f"{name.split()[0].lower()}@example.com",
                work_email=f"{name.split()[0].lower()}@alpagomanufacturing.com",
                phone=f"+971 5{i} {100 + i} {2000 + i}",
                nationality=nat,
                date_of_birth=TODAY - timedelta(days=365 * (28 + i)),
                join_date=TODAY + timedelta(days=join_offset),
                base_salary=salary, allowances=allow, currency="AED",
                passport_number=f"P{3000000 + i * 7}",
                emirates_id=f"784-{1985 + i}-{1000000 + i * 31}-{i}",
                visa_status="Employment visa — valid" if complete_docs else "In process",
                emergency_name="Family contact",
                emergency_relation="Spouse" if i % 2 else "Parent",
                emergency_phone=f"+971 5{i} 900 {1000 + i}",
                created_by=hr.id, updated_by=hr.id,
            )
            if name == "Priya Sharma":
                emp.candidate_id = priya.id
                emp.offer_id = offer.id
            s.add(emp)
            await s.flush()
            employees.append(emp)

            # onboarding checklist — completed for active staff, partial for the new joiner
            for order, (cat, t_title, t_desc, owner) in enumerate(DEFAULT_ONBOARDING):
                done = complete_docs or order < 3
                s.add(OnboardingTask(
                    employee_id=emp.id, category=cat, title=t_title,
                    description=t_desc, owner_role=owner, sort_order=order,
                    completed=done,
                    completed_at=NOW - timedelta(days=2) if done else None,
                    completed_by=hr.id if done else None,
                    created_by=hr.id, updated_by=hr.id,
                ))

            # documents — vary expiry so the watchlist has content
            doc_plan = [
                (DocType.passport, 400 + i * 30, f"P{3000000 + i * 7}"),
                (DocType.visa, [25, 48, 400, 180, -6, 300][i - 1], None),
                (DocType.emirates_id, [55, 700, 320, 12, 500, 240][i - 1], None),
                (DocType.contract, None, None),
                (DocType.photo, None, None),
                (DocType.medical_fitness, [900, 120, 640, 70, 365, 410][i - 1], None),
                (DocType.health_insurance, [95, 300, 33, 210, 150, 280][i - 1], None),
            ]
            if not complete_docs:
                doc_plan = doc_plan[:3]  # new joiner is mid-collection

            for dt, exp_days, number in doc_plan:
                fname = f"{emp.employee_code}-{dt.value}.pdf"
                path, size = _write_doc_file(
                    docs_dir, fname,
                    f"{dt.value.replace('_', ' ').title()} — {name}",
                    [
                        f"Employee: {name}  ({emp.employee_code})",
                        f"Document type: {dt.value.replace('_', ' ').title()}",
                        f"Reference: {number or 'N/A'}",
                        "",
                        "SAMPLE DOCUMENT — generated for demo purposes.",
                        "Not a real identity or legal document.",
                    ],
                )
                expiry = TODAY + timedelta(days=exp_days) if exp_days is not None else None
                d_status = DocStatus.verified if complete_docs else DocStatus.pending_review
                if expiry is not None and expiry < TODAY:
                    d_status = DocStatus.expired
                s.add(Document(
                    owner_type=OwnerType.employee, owner_id=emp.id, doc_type=dt,
                    status=d_status, filename=fname, file_path=str(path),
                    content_type="application/pdf", size_bytes=size,
                    document_number=number, expiry_date=expiry,
                    issue_date=TODAY - timedelta(days=500),
                    issuing_country=nat,
                    verified_by=hr.id if complete_docs else None,
                    verified_at=NOW - timedelta(days=10) if complete_docs else None,
                    created_by=hr.id, updated_by=hr.id,
                ))
        await s.flush()
        print(f"  {len(employees)} employees with onboarding checklists and documents")

        # ── candidate CVs (pipeline record + compliance document) ──
        cv_dir = Path("uploads") / "cvs"
        cv_count = 0
        for c in candidates[:4]:
            fname = f"CV-{c.name.replace(' ', '-')}.pdf"
            body = [
                f"{c.name}",
                f"{c.current_role}",
                f"{c.years_experience} years experience",
                "",
                "EXPERIENCE",
                f"  {c.current_role} (current)",
                "  Delivered multiple high-rise projects across the UAE.",
                "  Coordinated drawing office, procurement and site teams.",
                "",
                "EDUCATION",
                "  BSc Civil Engineering",
                "",
                "SAMPLE DOCUMENT — generated for demo purposes.",
            ]
            cv_path, cv_size = _write_doc_file(cv_dir, fname, f"Curriculum Vitae — {c.name}", body)

            score = cand_scores.get(c.name)
            # Cv has no Auditable mixin — no created_by/updated_by columns
            cv_row = Cv(
                candidate_id=c.id, filename=fname, file_path=str(cv_path),
                parsed_text="\n".join(body),
            )
            if score is not None:
                cv_row.ai_score = {
                    "score": score,
                    "verdict": "strong_match" if score >= 80 else "possible_match",
                    "summary": (
                        f"{c.years_experience} years in the GCC market with directly relevant "
                        f"experience. Salary expectation sits inside the approved band."
                    ),
                    "strengths": [
                        "Comparable project scale",
                        "GCC market experience",
                        "Relevant technical qualification",
                    ],
                    "gaps": [] if score >= 80 else ["Less exposure to high-rise projects"],
                }
            s.add(cv_row)

            # Same file also registered as a compliance document
            doc_path, doc_size = _write_doc_file(docs_dir, fname, f"Curriculum Vitae — {c.name}", body)
            s.add(Document(
                owner_type=OwnerType.candidate, owner_id=c.id, doc_type=DocType.cv,
                status=DocStatus.verified, filename=fname, file_path=str(doc_path),
                content_type="application/pdf", size_bytes=doc_size,
                verified_by=ta.id, verified_at=NOW - timedelta(days=4),
                created_by=ta.id, updated_by=ta.id,
            ))
            cv_count += 1
        await s.flush()
        print(f"  {cv_count} candidate CVs with AI screening results")

        # ── a little audit history so the activity feed isn't empty ──
        from alpago.core.audit import record_audit
        await record_audit(
            s, actor=jawad, action="user.logged_in",
            subject_type="user", subject_id=jawad.id,
        )
        await s.flush()

    print_credentials()


def _sample_jd(title: str, dept: str, seniority: str) -> str:
    return f"""# {title}

## About the role
Alpago is hiring a {seniority}-level {title} into the {dept} team. You will work
alongside the drawing office and site teams to deliver projects to programme and
to the standard our clients expect.

## Responsibilities
- Own day-to-day delivery for your assigned packages
- Coordinate between the drawing office, procurement and site teams
- Maintain accurate records, drawings and progress reporting
- Flag risks to the programme early and propose mitigations

## Requirements
- Relevant degree or trade qualification
- GCC experience on comparable projects
- Strong written and spoken English
- Valid UAE driving licence preferred

## What we offer
- Competitive salary with housing and transport allowances
- Medical insurance and annual flight allowance
- Clear progression within a growing contracting business
"""


def print_credentials() -> None:
    print()
    print("=" * 66)
    print("  LOGIN CREDENTIALS — every account uses the same password")
    print("=" * 66)
    print(f"  Password for all accounts:  {PASSWORD}")
    print()
    print(f"  {'Email':<42} {'Role'}")
    print("  " + "-" * 62)
    labels = {k: n for k, n, _ in ROLES}
    for email, name, role_keys in USERS:
        role_names = ", ".join(labels[r] for r in role_keys)
        print(f"  {email:<42} {role_names}")
    print()
    print("  Start here:  jawad@alpagomanufacturing.com  (Admin + Head of HR)")
    print("  To demo the approval chain, sign in as AGM then GM then CEO.")
    print("=" * 66)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Alpago HR demo data")
    parser.add_argument("--keep", action="store_true", help="keep existing rows")
    parser.add_argument("--force", action="store_true",
                        help="wipe even when the database holds the real employee register")
    args = parser.parse_args()

    print("Seeding Alpago HR demo data…")
    try:
        asyncio.run(seed(keep=args.keep, force=args.force))
    except Exception as exc:  # noqa: BLE001
        print(f"\nSeed failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
    print("\nDone. Restart the API if it is running.")
