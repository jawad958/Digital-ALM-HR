"""Import Alpago's employee register from the HR Excel export.

    python import_employees.py "C:\\path\\to\\Employee_Detailed_Report.xlsx"
    python import_employees.py <file> --dry-run     # report, change nothing

Each sheet is a division. Expected columns (header row 1):

    SNO · Emp Code · Employe Name · Reporting Manager · Department · Designation
    Nationality · Date of Joining · Email · Contact No Office · ID No
    ID Issued Dt · ID Expiry Dt · Passport No · Visa No · Visa Issued Dt
    Visa Expiry Dt · Labour Card Expiry Date

Employees are matched on Emp Code, so re-running updates rather than duplicates.
The identity columns become Document records with their real expiry dates, which
is what puts the whole workforce onto the expiry watchlist. No scan is attached —
those records carry the detail and wait for the file.

Reporting lines are resolved on a second pass by matching the manager's full name.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select

from alpago.core.database import db_session
from alpago.modules.documents import DocStatus, DocType, Document, OwnerType
from alpago.modules.employees import (
    Division,
    Employee,
    EmploymentStatus,
    EmploymentType,
)

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl is required:  pip install openpyxl")


COLUMNS = {
    "sno": 1, "emp_code": 2, "name": 3, "reporting_manager": 4,
    "department": 5, "designation": 6, "nationality": 7, "join_date": 8,
    "email": 9, "phone": 10,
    "emirates_id": 11, "eid_issued": 12, "eid_expiry": 13,
    "passport_no": 14,
    "visa_no": 15, "visa_issued": 16, "visa_expiry": 17,
    "labour_card_expiry": 18,
}

# The register's department text decides the division, not the sheet name —
# the Joinery sheet carries a few Civil rows.
DEPARTMENT_TO_DIVISION = {
    "JOINERY DEPARTMENT": Division.manufacturing,
    "CIVIL DEPARTMENT": Division.civil,
    "MEP DEPARTMENT": Division.electro_mechanical,
    "OPERATIONS – CONTRACTING": Division.operations,
    "OPERATIONS - CONTRACTING": Division.operations,
}

NATIONALITY_FIXES = {
    "NEPAL": "Nepalese",
    "BANGLADESH": "Bangladeshi",
    "FILIPINOS": "Filipino",
    "GHANAIAN": "Ghanaian",
}


def clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "-", "--", "N/A", "n/a", "None"):
        return None
    return text


def as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = clean(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def first_phone(value) -> str | None:
    """The register often lists two numbers separated by / or a comma."""
    text = clean(value)
    if not text:
        return None
    for sep in ("/", ","):
        if sep in text:
            text = text.split(sep)[0]
    return text.strip()[:40] or None


def nationality_of(value) -> str | None:
    text = clean(value)
    if not text:
        return None
    return NATIONALITY_FIXES.get(text.upper(), text.title())


def read_rows(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, data_only=True)
    rows: list[dict] = []
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        for r in range(2, ws.max_row + 1):
            name = clean(ws.cell(r, COLUMNS["name"]).value)
            code = clean(ws.cell(r, COLUMNS["emp_code"]).value)
            if not name or not code:
                continue
            rows.append({
                "sheet": sheet,
                "emp_code": code,
                "name": name,
                "reporting_manager": clean(ws.cell(r, COLUMNS["reporting_manager"]).value),
                "department": clean(ws.cell(r, COLUMNS["department"]).value),
                "designation": clean(ws.cell(r, COLUMNS["designation"]).value),
                "nationality": nationality_of(ws.cell(r, COLUMNS["nationality"]).value),
                "join_date": as_date(ws.cell(r, COLUMNS["join_date"]).value),
                "email": clean(ws.cell(r, COLUMNS["email"]).value),
                "phone": first_phone(ws.cell(r, COLUMNS["phone"]).value),
                "emirates_id": clean(ws.cell(r, COLUMNS["emirates_id"]).value),
                "eid_issued": as_date(ws.cell(r, COLUMNS["eid_issued"]).value),
                "eid_expiry": as_date(ws.cell(r, COLUMNS["eid_expiry"]).value),
                "passport_no": clean(ws.cell(r, COLUMNS["passport_no"]).value),
                "visa_no": clean(ws.cell(r, COLUMNS["visa_no"]).value),
                "visa_issued": as_date(ws.cell(r, COLUMNS["visa_issued"]).value),
                "visa_expiry": as_date(ws.cell(r, COLUMNS["visa_expiry"]).value),
                "labour_card_expiry": as_date(ws.cell(r, COLUMNS["labour_card_expiry"]).value),
            })
    return rows


async def sync_document(
    session, *, employee: Employee, doc_type: DocType, number: str | None,
    issue_date: date | None, expiry_date: date | None, nationality: str | None,
) -> str:
    """Create or refresh the record for one identity document. Returns created|updated|skipped."""
    if not number and not expiry_date:
        return "skipped"

    existing = (await session.execute(
        select(Document).where(
            Document.owner_type == OwnerType.employee,
            Document.owner_id == employee.id,
            Document.doc_type == doc_type,
            Document.deleted_at.is_(None),
        )
    )).scalars().first()

    status = DocStatus.expired if (expiry_date and expiry_date < date.today()) else DocStatus.pending_review

    if existing:
        existing.document_number = number or existing.document_number
        existing.issue_date = issue_date or existing.issue_date
        existing.expiry_date = expiry_date or existing.expiry_date
        if not existing.file_path:
            existing.status = status
        return "updated"

    session.add(Document(
        owner_type=OwnerType.employee,
        owner_id=employee.id,
        doc_type=doc_type,
        status=status,
        filename=f"{employee.employee_code}-{doc_type.value}",
        file_path=None,                       # detail on record, scan still to come
        content_type=None,
        size_bytes=0,
        document_number=number,
        issue_date=issue_date,
        expiry_date=expiry_date,
        issuing_country=nationality,
        notes="Imported from the HR employee register. Scan not yet uploaded.",
    ))
    return "created"


async def run(path: Path, dry_run: bool) -> None:
    rows = read_rows(path)
    print(f"Read {len(rows)} employees from {path.name}")
    if dry_run:
        print("\n-- dry run, nothing will be written --")

    by_division: dict[str, int] = {}
    stats = {"created": 0, "updated": 0, "docs_created": 0, "docs_updated": 0, "managers_linked": 0}
    unmapped_departments: set[str] = set()

    async with db_session() as s:
        name_to_employee: dict[str, Employee] = {}

        for row in rows:
            dept = (row["department"] or "").strip()
            division = DEPARTMENT_TO_DIVISION.get(dept)
            if division is None:
                unmapped_departments.add(dept)
                division = Division.operations
            by_division[division.value] = by_division.get(division.value, 0) + 1

            emp = (await s.execute(
                select(Employee).where(Employee.employee_code == row["emp_code"])
            )).scalar_one_or_none()

            if emp is None:
                emp = Employee(
                    employee_code=row["emp_code"],
                    full_name=row["name"],
                    job_title=row["designation"] or "Not specified",
                    department=dept.replace(" DEPARTMENT", "").title() or "Unassigned",
                    division=division,
                    employment_type=EmploymentType.full_time,
                    status=EmploymentStatus.active,
                    created_by=None, updated_by=None,
                )
                if not dry_run:
                    s.add(emp)
                stats["created"] += 1
            else:
                stats["updated"] += 1

            # Refresh from the register — it is the source of truth for these
            emp.full_name = row["name"]
            emp.job_title = row["designation"] or emp.job_title
            emp.department = dept.replace(" DEPARTMENT", "").title() or emp.department
            emp.division = division
            emp.nationality = row["nationality"] or emp.nationality
            emp.join_date = row["join_date"] or emp.join_date
            emp.work_email = row["email"] or emp.work_email
            emp.phone = row["phone"] or emp.phone
            emp.passport_number = row["passport_no"] or emp.passport_number
            emp.emirates_id = row["emirates_id"] or emp.emirates_id
            if row["visa_expiry"]:
                emp.visa_status = (
                    "Employment visa — expired"
                    if row["visa_expiry"] < date.today()
                    else "Employment visa — valid"
                )

            if not dry_run:
                await s.flush()

                for doc_type, number, issued, expiry in [
                    (DocType.passport, row["passport_no"], None, None),
                    (DocType.emirates_id, row["emirates_id"], row["eid_issued"], row["eid_expiry"]),
                    (DocType.visa, row["visa_no"], row["visa_issued"], row["visa_expiry"]),
                    (DocType.labour_card, None, None, row["labour_card_expiry"]),
                ]:
                    result = await sync_document(
                        s, employee=emp, doc_type=doc_type, number=number,
                        issue_date=issued, expiry_date=expiry,
                        nationality=row["nationality"],
                    )
                    if result == "created":
                        stats["docs_created"] += 1
                    elif result == "updated":
                        stats["docs_updated"] += 1

            name_to_employee[row["name"].strip().upper()] = emp

        # Second pass — reporting lines, matched on the manager's full name
        if not dry_run:
            await s.flush()
            for row in rows:
                manager_name = (row["reporting_manager"] or "").strip().upper()
                if not manager_name:
                    continue
                manager = name_to_employee.get(manager_name)
                employee = name_to_employee.get(row["name"].strip().upper())
                if manager and employee and manager.id != employee.id:
                    employee.reports_to_id = manager.id
                    stats["managers_linked"] += 1
            await s.flush()

    print(f"\n  employees created : {stats['created']}")
    print(f"  employees updated : {stats['updated']}")
    print(f"  documents created : {stats['docs_created']}")
    print(f"  documents updated : {stats['docs_updated']}")
    print(f"  reporting lines   : {stats['managers_linked']}")
    print(f"\n  by division: {by_division}")
    if unmapped_departments:
        print(f"\n  ! unmapped departments (filed under operations): {sorted(unmapped_departments)}")

    # What the expiry watchlist will now show
    if not dry_run:
        today = date.today()
        soon = [r for r in rows for d in
                (r["eid_expiry"], r["visa_expiry"], r["labour_card_expiry"])
                if d and (d - today).days <= 60]
        expired = [r for r in rows for d in
                   (r["eid_expiry"], r["visa_expiry"], r["labour_card_expiry"])
                   if d and d < today]
        print(f"\n  Expiry watchlist: {len(expired)} already expired, "
              f"{len(soon) - len(expired)} expiring within 60 days")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Alpago's employee register")
    parser.add_argument("path", help="Path to the Employee Detailed Report .xlsx")
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args()

    xlsx = Path(args.path)
    if not xlsx.exists():
        sys.exit(f"File not found: {xlsx}")

    try:
        asyncio.run(run(xlsx, args.dry_run))
    except Exception as exc:  # noqa: BLE001
        print(f"\nImport failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
    print("\nDone." + ("" if args.dry_run else " Restart the API if it is running."))
