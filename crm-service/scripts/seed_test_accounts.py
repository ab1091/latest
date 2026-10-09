"""
Creates/resets the three role-tier test logins used for local QA:
super_admin, staff, and customer. Idempotent — safe to re-run any time
a password needs resetting or the row was dropped from a DB rebuild.

These are dev/test-only accounts (@allzonetech.local) and are separate
from real accounts like admin@allzonetech.com — this script never
touches those.

Run: crm-service/venv/bin/python scripts/seed_test_accounts.py
"""
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import bcrypt  # noqa: E402
from core.db import get_conn, dict_cursor  # noqa: E402

# Keep in sync with the "Test accounts" table in RUNNING.md if changed.
TEST_ACCOUNTS = [
    {
        "email": "superadmin.test@allzonetech.local",
        "password": "SuperAdmin!2026Test",
        "role": "super_admin",
        "business_id": None,
        "first_name": "Super",
        "last_name": "AdminTest",
    },
    {
        "email": "staff.test@allzonetech.local",
        "password": "StaffUser!2026Test",
        "role": "staff",
        "business_id": "bus_001",
        "first_name": "Staff",
        "last_name": "Test",
    },
    {
        "email": "customer.test@allzonetech.local",
        "password": "Customer!2026Test",
        "role": "customer",
        "business_id": "bus_001",
        "first_name": "Cust",
        "last_name": "Test",
    },
]


def main():
    conn = get_conn()
    cur = dict_cursor(conn)
    for acct in TEST_ACCOUNTS:
        password_hash = bcrypt.hashpw(acct["password"].encode(), bcrypt.gensalt()).decode()
        cur.execute("SELECT id FROM users WHERE email = %s", (acct["email"],))
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE users SET password_hash=%s, role=%s, business_id=%s, is_active=1 WHERE email=%s",
                (password_hash, acct["role"], acct["business_id"], acct["email"]),
            )
            print(f"updated  {acct['email']}")
        else:
            cur.execute(
                """
                INSERT INTO users (id, business_id, email, password_hash, first_name, last_name, role, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
                """,
                (
                    f"usr_{uuid.uuid4().hex[:20]}",
                    acct["business_id"],
                    acct["email"],
                    password_hash,
                    acct["first_name"],
                    acct["last_name"],
                    acct["role"],
                ),
            )
            print(f"created  {acct['email']}")
    conn.commit()
    cur.close()
    conn.close()
    print("\nDone. See RUNNING.md 'Test accounts' table for the current passwords.")


if __name__ == "__main__":
    main()
