#!/usr/bin/env python3
"""
Register all 5 Foundry Manager tools into Open WebUI's tool table.

Idempotent — skips tools that already exist by ID.
Creates an admin user if the DB has no users (WEBUI_AUTH=false mode).

Usage:
    .venv/Scripts/python.exe scripts/register_foundry_tools.py
"""
from __future__ import annotations

import bcrypt
import json
import sqlite3
import sys
import time
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "webui.db"
TOOLS_DIR = (
    Path(__file__).resolve().parent.parent
    / "backend" / "open_webui" / "tools" / "foundry"
)

ADMIN_ID = "admin-001"
ADMIN_EMAIL = "admin@localhost"
ADMIN_PASSWORD = "admin"
ADMIN_NAME = "Admin"

# ─── Tool definitions ────────────────────────────────────────────────────────
# Each entry: (tool_id, source_filename, meta_description, specs)
# Specs are manually built OpenAI function-calling schemas.

TOOL_DEFS = [
    {
        "id": "foundry_dashboard",
        "name": "Foundry Dashboard",
        "source_file": "foundry_dashboard.py",
        "description": "Fetches the real-time monitoring dashboard from the Foundry Manager API and renders it as formatted text inside the chat.",
        "specs": [
            {
                "type": "function",
                "function": {
                    "name": "get_foundry_dashboard",
                    "description": "Fetch the Foundry Manager monitoring dashboard showing all active tasks, executor status, and system health.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_foundry_stats",
                    "description": "Fetch comprehensive system statistics from the Foundry Manager, including executor info, task counts, and memory/history stats.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ],
    },
    {
        "id": "foundry_artifacts",
        "name": "Foundry Artifacts",
        "source_file": "foundry_artifacts.py",
        "description": "Fetches and pretty-prints task artifacts and status from the Foundry Manager API.",
        "specs": [
            {
                "type": "function",
                "function": {
                    "name": "get_foundry_artifacts",
                    "description": "Fetch and display all artifacts produced by a specific foundry task.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "The task ID to fetch artifacts for.",
                            }
                        },
                        "required": ["task_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_foundry_task",
                    "description": "Get detailed status of a specific foundry task including progress and event count.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "The task ID to check.",
                            }
                        },
                        "required": ["task_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_foundry_tasks",
                    "description": "List all tasks in the Foundry Manager with their current status.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ],
    },
    {
        "id": "foundry_audit",
        "name": "Foundry Audit",
        "source_file": "foundry_audit.py",
        "description": "Reads a run manifest from the Foundry harness and prints the honest ledger with tier-separated verification (behavioral / partial / weak / existence).",
        "specs": [
            {
                "type": "function",
                "function": {
                    "name": "get_foundry_audit",
                    "description": "Read a foundry run manifest and display the honest audit ledger with verification tiers.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "run_id": {
                                "type": "string",
                                "description": "The run ID to audit (e.g. 'cam4-proof-001').",
                            }
                        },
                        "required": ["run_id"],
                    },
                },
            },
        ],
    },
    {
        "id": "foundry_dag",
        "name": "Foundry DAG Visualizer",
        "source_file": "foundry_dag.py",
        "description": "Reads a DAG YAML file from the foundry harness and renders it as a Mermaid diagram in chat.",
        "specs": [
            {
                "type": "function",
                "function": {
                    "name": "get_foundry_dag",
                    "description": "Render a foundry project's DAG as a visual Mermaid dependency diagram with optional verification status overlay.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_path": {
                                "type": "string",
                                "description": "Path relative to the foundry base directory, or a predefined shortcut: 'text_query', 'string_utils', 'letter_frequency', 'root'.",
                                "default": "text_query",
                            },
                            "include_status": {
                                "type": "boolean",
                                "description": "If True, overlay verification status from the manifest file.",
                                "default": True,
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_foundry_projects",
                    "description": "List available foundry projects and proof runs that have DAG files.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ],
    },
    {
        "id": "foundry_manifest",
        "name": "Foundry Manifest Viewer",
        "source_file": "foundry_manifest.py",
        "description": "Reads foundry run manifests and renders them as structured markdown tables with honest-tier verification and Mermaid charts.",
        "specs": [
            {
                "type": "function",
                "function": {
                    "name": "get_foundry_manifest",
                    "description": "Render a foundry run manifest as a structured audit report with a Mermaid pie chart of verification tiers.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "run_id": {
                                "type": "string",
                                "description": "The run ID to display (e.g. 'cam4_proof14', 'text_query_proof8').",
                                "default": "cam4_proof14",
                            },
                            "include_chart": {
                                "type": "boolean",
                                "description": "If True, include a Mermaid pie chart.",
                                "default": True,
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_foundry_manifests",
                    "description": "List all available foundry run manifests with dates and verification summaries.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ],
    },
]


def hash_password(password: str) -> str:
    """Hash a password using bcrypt (OWUI's default algorithm)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def ensure_admin_user(conn: sqlite3.Connection) -> str:
    """Create an admin user if none exists. Returns the admin user ID."""
    cur = conn.execute("SELECT COUNT(*) FROM user")
    user_count = cur.fetchone()[0]

    if user_count > 0:
        # Find existing admin user
        cur = conn.execute("SELECT id FROM user WHERE role = 'admin' LIMIT 1")
        row = cur.fetchone()
        if row:
            print(f"  ✓ Admin user already exists: {row[0]}")
            return row[0]
        # No admin found — take first user
        cur = conn.execute("SELECT id FROM user LIMIT 1")
        row = cur.fetchone()
        if row:
            print(f"  ℹ Using existing user: {row[0]}")
            return row[0]

    # Create new admin user
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO user (id, name, email, role, profile_image_url, last_active_at, updated_at, created_at, username, bio, gender, date_of_birth, profile_banner_image_url, timezone, presence_state, status_emoji, status_message, status_expires_at, oauth, info, settings, scim)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ADMIN_ID,
            ADMIN_NAME,
            ADMIN_EMAIL,
            "admin",
            "",  # profile_image_url
            now,  # last_active_at
            now,  # updated_at
            now,  # created_at
            "admin",  # username
            "",  # bio
            "",  # gender
            None,  # date_of_birth
            "",  # profile_banner_image_url
            "",  # timezone
            "online",  # presence_state
            "",  # status_emoji
            "",  # status_message
            0,  # status_expires_at
            json.dumps({}),  # oauth
            json.dumps({}),  # info
            json.dumps({}),  # settings
            json.dumps({}),  # scim
        ),
    )

    # Create auth entry with bcrypt password
    pw_hash = hash_password(ADMIN_PASSWORD)
    conn.execute(
        "INSERT INTO auth (id, email, password, active) VALUES (?, ?, ?, ?)",
        (ADMIN_ID, ADMIN_EMAIL, pw_hash, True),
    )

    print(f"  ✓ Created admin user: {ADMIN_ID} ({ADMIN_EMAIL})")
    return ADMIN_ID


def register_tools(conn: sqlite3.Connection, user_id: str) -> int:
    """Register all foundry tools. Returns count of tools inserted."""
    now = int(time.time())
    inserted = 0
    skipped = 0

    for tool_def in TOOL_DEFS:
        tool_id = tool_def["id"]

        # Check if already exists
        cur = conn.execute("SELECT id FROM tool WHERE id = ?", (tool_id,))
        if cur.fetchone():
            print(f"  ⏭  {tool_id} — already registered, skipping")
            skipped += 1
            continue

        # Read source code from file
        source_path = TOOLS_DIR / tool_def["source_file"]
        if not source_path.exists():
            print(f"  ✗ {tool_id} — source file not found: {source_path}")
            continue

        source_code = source_path.read_text(encoding="utf-8")

        # Build meta
        meta = {
            "description": tool_def["description"],
            "manifest": {},
            "has_user_valves": False,
        }

        # Insert
        conn.execute(
            """
            INSERT INTO tool (id, user_id, name, content, specs, meta, valves, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_id,
                user_id,
                tool_def["name"],
                source_code,
                json.dumps(tool_def["specs"]),
                json.dumps(meta),
                None,  # valves
                now,
                now,
            ),
        )
        inserted += 1
        func_names = [s["function"]["name"] for s in tool_def["specs"]]
        print(f"  ✓ {tool_id} — {tool_def['name']} ({', '.join(func_names)})")

    return inserted


def main():
    print("=" * 60)
    print("  Foundry Tool Registration Script")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"  ✗ Database not found: {DB_PATH}")
        sys.exit(1)

    print(f"  Database: {DB_PATH}")
    print(f"  Tools dir: {TOOLS_DIR}")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        # Step 1: Ensure admin user
        print("[1/2] Ensuring admin user...")
        user_id = ensure_admin_user(conn)
        conn.commit()
        print()

        # Step 2: Register tools
        print("[2/2] Registering foundry tools...")
        inserted = register_tools(conn, user_id)
        conn.commit()
        print()

        # Step 3: Verify
        cur = conn.execute("SELECT COUNT(*) FROM tool")
        total = cur.fetchone()[0]
        cur = conn.execute("SELECT id, name FROM tool ORDER BY name")
        tools = cur.fetchall()

        print("=" * 60)
        print(f"  Results: {inserted} new tool(s) inserted")
        print(f"  Total tools in DB: {total}")
        print()
        for t in tools:
            print(f"    • {t['id']}: {t['name']}")
        print("=" * 60)

        return 0 if total == len(TOOL_DEFS) else 1

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
