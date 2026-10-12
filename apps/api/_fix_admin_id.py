"""One-shot: strip hyphens from the seeded admin user's id so SQLAlchemy
can match it. Safe to re-run; it's a no-op after the first run."""

import sqlite3

DB = "alpago_dev.db"
EMAIL = "jawad@alpagomanufacturing.com"

con = sqlite3.connect(DB)
try:
    cur = con.execute("SELECT id FROM users WHERE email = ?", (EMAIL,))
    row = cur.fetchone()
    if row is None:
        print(f"no row for {EMAIL} — nothing to do")
    else:
        old_id = row[0]
        new_id = old_id.replace("-", "")
        if old_id == new_id:
            print(f"id already clean: {old_id}")
        else:
            con.execute("UPDATE users SET id = ? WHERE email = ?", (new_id, EMAIL))
            con.commit()
            print(f"fixed: {old_id} -> {new_id}")
finally:
    con.close()
