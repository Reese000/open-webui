#!/usr/bin/env python3
"""
Register all 3 Foundry Manager pipeline filters into Open WebUI's function table.

These are OWUI Filter-type functions that intercept trigger phrases
(/dashboard, /dag, /manifest) and render Foundry Manager data in chat.

Idempotent — skips functions that already exist by ID.

Usage:
    .venv/Scripts/python.exe scripts/register_foundry_pipelines.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "webui.db"
PIPELINES_DIR = (
    Path(__file__).resolve().parent.parent
    / "backend" / "open_webui" / "pipelines" / "foundry"
)

ADMIN_ID = "admin-001"

# ─── Pipeline definitions ────────────────────────────────────────────────────
# Each entry: (function_id, source_filename, display_name, description)
PIPELINE_DEFS = [
    {
        "id": "foundry_monitor",
        "source_file": "foundry_monitor_pipeline.py",
        "name": "Foundry Monitor Dashboard",
        "description": "Renders the Foundry Manager monitoring dashboard when /dashboard is sent. Shows system health, active tasks, executor breakdown, and uptime.",
    },
    {
        "id": "foundry_dag",
        "source_file": "foundry_dag_pipeline.py",
        "name": "Foundry DAG Visualizer",
        "description": "Renders the Foundry Manager DAG as a Mermaid diagram when /dag is sent. Shows task dependency graph with verification status.",
    },
    {
        "id": "foundry_manifest",
        "source_file": "foundry_manifest_pipeline.py",
        "name": "Foundry Manifest Viewer",
        "description": "Renders the Foundry Manager manifest as structured tables when /manifest is sent. Shows verification status, pass rates, and history.",
    },
]


def get_admin_user_id(conn: sqlite3.Connection) -> str:
    """Get the admin user ID from the database."""
    cur = conn.execute("SELECT id FROM user WHERE role = 'admin' LIMIT 1")
    row = cur.fetchone()
    if row:
        return row[0]
    # Fall back to any user
    cur = conn.execute("SELECT id FROM user LIMIT 1")
    row = cur.fetchone()
    if row:
        return row[0]
    return ADMIN_ID


def register_pipelines(conn: sqlite3.Connection, user_id: str) -> int:
    """Register all foundry pipeline filters. Returns count inserted."""
    now = int(time.time())
    inserted = 0
    skipped = 0

    for pdef in PIPELINE_DEFS:
        func_id = pdef["id"]

        # Check if already exists
        cur = conn.execute("SELECT id FROM function WHERE id = ?", (func_id,))
        if cur.fetchone():
            print(f"  ⏭  {func_id} — already registered, skipping")
            skipped += 1
            continue

        # Read source code
        source_path = PIPELINES_DIR / pdef["source_file"]
        if not source_path.exists():
            print(f"  ✗ {func_id} — source file not found: {source_path}")
            continue

        source_code = source_path.read_text(encoding="utf-8")

        # Build meta (matches OWUI FunctionMeta schema)
        meta = json.dumps({
            "description": pdef["description"],
            "manifest": {},
        })

        # Insert as 'filter' type function
        # is_global=True makes it active for all models
        conn.execute(
            """
            INSERT INTO function (id, user_id, name, type, content, meta, valves, is_active, is_global, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                func_id,
                user_id,
                pdef["name"],
                "filter",       # type: filter → has inlet/outlet
                source_code,
                meta,
                None,           # valves (runtime config, set by Filter.__init__)
                True,           # is_active
                True,           # is_global (active for all models)
                now,
                now,
            ),
        )
        inserted += 1
        print(f"  ✓ {func_id} — {pdef['name']} (filter, global)")

    return inserted


def verify(conn: sqlite3.Connection) -> None:
    """Print verification summary."""
    cur = conn.execute("SELECT COUNT(*) FROM function")
    total = cur.fetchone()[0]

    cur = conn.execute(
        "SELECT id, name, type, is_active, is_global FROM function WHERE id LIKE 'foundry_%' ORDER BY name"
    )
    funcs = cur.fetchall()

    print()
    print("=" * 60)
    print(f"  Total functions in DB: {total}")
    print(f"  Foundry pipeline filters: {len(funcs)}")
    print()
    for f in funcs:
        active = "🟢" if f[3] else "🔴"
        global_ = " (global)" if f[4] else ""
        print(f"    {active} {f[0]}: {f[1]} [{f[2]}]{global_}")
    print("=" * 60)


def main():
    print("=" * 60)
    print("  Foundry Pipeline Registration Script")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"  ✗ Database not found: {DB_PATH}")
        sys.exit(1)

    print(f"  Database: {DB_PATH}")
    print(f"  Pipelines dir: {PIPELINES_DIR}")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        user_id = get_admin_user_id(conn)
        print(f"  Admin user: {user_id}")
        print()

        print("[1/1] Registering foundry pipeline filters...")
        inserted = register_pipelines(conn, user_id)
        conn.commit()
        print()

        verify(conn)

        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
