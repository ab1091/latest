"""
Bootstraps a default business + admin login on a completely fresh database —
run automatically by docker-compose's `seed` service after migrations, so
`docker compose up` on a brand-new clone ends with a working login instead
of an empty, unusable database.

Idempotent: does nothing if `bus_001` (or its admin) already exists, so it's
always safe to run again after a rebuild.

Prints the credentials to stdout (visible in `docker compose logs seed`) —
this is a local-dev bootstrap only, not meant for real production accounts.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import bcrypt  # noqa: E402
from core.db import get_conn, dict_cursor  # noqa: E402

DEFAULT_EMAIL = "admin@aischeduler.com"
DEFAULT_PASSWORD = "Test1234!"


def main():
    conn = get_conn()
    cur = dict_cursor(conn)

    cur.execute("SELECT id FROM businesses WHERE id = 'bus_001'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO businesses (id, name, email) VALUES ('bus_001', %s, %s)",
            ("Default Business", "admin@aischeduler.com"),
        )
        print("created  business bus_001")
    else:
        print("exists   business bus_001")

    cur.execute("SELECT id FROM users WHERE email = %s", (DEFAULT_EMAIL,))
    if not cur.fetchone():
        password_hash = bcrypt.hashpw(DEFAULT_PASSWORD.encode(), bcrypt.gensalt()).decode()
        cur.execute(
            """
            INSERT INTO users (id, business_id, email, password_hash, first_name, last_name, role)
            VALUES ('usr_admin', 'bus_001', %s, %s, 'Admin', 'User', 'admin')
            """,
            (DEFAULT_EMAIL, password_hash),
        )
        print(f"created  admin login {DEFAULT_EMAIL}")
    else:
        print(f"exists   admin login {DEFAULT_EMAIL}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nLogin with: {DEFAULT_EMAIL} / {DEFAULT_PASSWORD}")
    print("Change this password after first login — it's a fixed local-dev default, not a real credential.")


if __name__ == "__main__":
    main()
