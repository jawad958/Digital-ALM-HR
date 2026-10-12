"""Quick diagnostic: what is actually in the database right now.

    python check_db.py
"""

import asyncio

from sqlalchemy import func, select

from alpago.core.config import settings
from alpago.core.database import db_session
from alpago.models.user import User
from alpago.modules.candidates import Candidate
from alpago.modules.documents import Document
from alpago.modules.employees import Employee
from alpago.modules.forms import FormSubmission
from alpago.modules.hiring import HiringRequest


async def main() -> None:
    print(f"database: {settings.database_url}\n")

    async with db_session() as s:
        async def count(model) -> int:
            return (await s.execute(select(func.count(model.id)))).scalar_one()

        rows = [
            ("users", await count(User)),
            ("employees", await count(Employee)),
            ("documents", await count(Document)),
            ("candidates", await count(Candidate)),
            ("hiring requests", await count(HiringRequest)),
            ("form submissions", await count(FormSubmission)),
        ]
        for label, n in rows:
            print(f"  {label:<20} {n}")

        emp_total = next(n for label, n in rows if label == "employees")
        if emp_total == 0:
            print("\n  No employees. Run:  python import_employees.py <path-to-xlsx>")
            return

        print("\n  employees by division:")
        by_div = (await s.execute(
            select(Employee.division, func.count(Employee.id)).group_by(Employee.division)
        )).all()
        for div, n in by_div:
            value = div.value if hasattr(div, "value") else div
            print(f"    {value:<22} {n}")

        print("\n  employees by status:")
        by_status = (await s.execute(
            select(Employee.status, func.count(Employee.id)).group_by(Employee.status)
        )).all()
        for st, n in by_status:
            value = st.value if hasattr(st, "value") else st
            print(f"    {value:<22} {n}")

        print("\n  soft-deleted employees (hidden from the list):")
        deleted = (await s.execute(
            select(func.count(Employee.id)).where(Employee.deleted_at.is_not(None))
        )).scalar_one()
        print(f"    {deleted}")

        print("\n  first 5 employees:")
        sample = (await s.execute(select(Employee).limit(5))).scalars().all()
        for e in sample:
            div = e.division.value if hasattr(e.division, "value") else e.division
            st = e.status.value if hasattr(e.status, "value") else e.status
            print(f"    {e.employee_code:<8} {e.full_name[:34]:<34} {div:<18} {st}")


if __name__ == "__main__":
    asyncio.run(main())
