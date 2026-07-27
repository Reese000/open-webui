#!/usr/bin/env python3
"""
Idempotent script to ensure an admin user exists in webui.db.

When WEBUI_AUTH=false, Open WebUI's auto-create only fires when a browser
hits the signin endpoint — pure API access never triggers it.  This script
creates the admin user directly in the SQLite database, mirroring the
signup_handler logic in auths.py:

  - Email:  admin@localhost
  - Password: admin
  - Role: admin
  - Active: True

Idempotent: exits cleanly if the user already exists.

Usage:
    python scripts/ensure_admin_user.py           # from project root
    python scripts/ensure_admin_user.py <db_path> # custom DB path
"""

from __future__ import annotations

import getpass
import os
import sqlite3
import sys
import time
import uuid

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "data", "webui.db")
ADMIN_EMAIL = "admin@localhost"
ADMIN_PASSWORD = "admin"
ADMIN_NAME = "User"
ADMIN_ROLE = "admin"
PROFILE_IMAGE_URL = "/user.png"


def hash_password_bcrypt(password: str) -> str:
    """Hash a password using bcrypt, matching OWUI's default algorithm."""
    try:
        import bcrypt

        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    except ImportError:
        # Fallback: try using the venv's bcrypt via subprocess if running
        # outside the venv.  In practice the venv python is used, so this
        # path is rarely hit.
        raise SystemExit(
            "bcrypt is not installed. Run with: .venv/Scripts/python.exe scripts/ensure_admin_user.py"
        )


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(DB_PATH_DEFAULT)

    if not os.path.isfile(db_path):
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # -- Check if admin user already exists --
    cur.execute("SELECT id FROM [user] WHERE email = ?", (ADMIN_EMAIL.lower(),))
    existing = cur.fetchone()

    if existing:
        print(f"Admin user already exists (id={existing['id']}). Nothing to do.")
        conn.close()
        return

    # -- Check if there are any users at all (mirror has_users check) --
    cur.execute("SELECT COUNT(*) AS cnt FROM [user]")
    user_count = cur.fetchone()["cnt"]

    if user_count > 0:
        # Users exist but none with this email — create the admin user
        # This mirrors the WEBUI_AUTH=false path which creates the admin
        # user regardless (since it's the system auto-create).
        pass

    # -- Create user + auth pair (single transaction) --
    new_id = str(uuid.uuid4())
    now = int(time.time())
    hashed = hash_password_bcrypt(ADMIN_PASSWORD)

    try:
        # Insert auth record (mirrors Auth model)
        cur.execute(
            "INSERT INTO [auth] (id, email, password, active) VALUES (?, ?, ?, ?)",
            (new_id, ADMIN_EMAIL.lower(), hashed, True),
        )

        # Insert user record (mirrors User model)
        cur.execute(
            """INSERT INTO [user]
                (id, name, email, role, profile_image_url,
                 last_active_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id,
                ADMIN_NAME,
                ADMIN_EMAIL.lower(),
                ADMIN_ROLE,
                PROFILE_IMAGE_URL,
                now,
                now,
                now,
            ),
        )

        conn.commit()
        print(f"Created admin user: {ADMIN_EMAIL} (id={new_id})")
    except sqlite3.IntegrityError as e:
        conn.rollback()
        print(f"User already exists or constraint violation: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
