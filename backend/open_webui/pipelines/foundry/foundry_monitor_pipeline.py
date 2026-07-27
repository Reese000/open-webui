"""
Foundry Manager — Monitor Dashboard Filter

OWUI Filter that renders the Foundry Manager monitoring dashboard
when the user sends /dashboard or "show dashboard".

Triggers on: /dashboard, show dashboard, system status, foundry status
Fetches: GET http://127.0.0.1:8000/api/monitoring/dashboard
         GET http://127.0.0.1:8000/api/monitoring/summary
         GET http://127.0.0.1:8000/api/monitoring/tasks/active
Renders: Formatted Markdown card with health badge, task counts, executor breakdown
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

TRIGGER_PHRASES = [
    "/dashboard",
    "show dashboard",
    "system status",
    "foundry status",
    "show status",
]


def _fmt_uptime(seconds: float) -> str:
    """Format seconds into human-readable uptime."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    hours = seconds / 3600
    if hours < 24:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


def _render_dashboard(dashboard: dict, summary: dict, active: dict) -> str:
    """Render the FM monitoring data as a Markdown card."""
    lines = ["", "---", "## 🏭 Foundry Manager Dashboard", ""]

    # System health badge
    agent_status = dashboard.get("agent_status", {})
    manager_status = agent_status.get("manager_status", "unknown")
    status_icon = "🟢" if manager_status == "idle" else "🟡" if manager_status == "busy" else "🔴"
    lines.append(f"**System:** {status_icon} `{manager_status}` | **Uptime:** {_fmt_uptime(dashboard.get('uptime_seconds', 0))}")
    lines.append("")

    # Task counts
    total_active = dashboard.get("total_active", 0)
    total_completed = dashboard.get("total_completed", 0)
    total_failed = dashboard.get("total_failed", 0)
    lines.append(f"**Tasks:** 🟢 {total_active} active · ✅ {total_completed} completed · ❌ {total_failed} failed")
    lines.append("")

    # Pending tasks
    pending = dashboard.get("pending_tasks", [])
    if pending:
        lines.append("### Active Tasks")
        for t in pending:
            name = t.get("description", t.get("task_id", "unnamed"))
            phase = t.get("phase", "unknown")
            elapsed = t.get("elapsed_seconds", 0)
            progress = t.get("progress", {})
            progress_str = ""
            if progress:
                verified = progress.get("verified", 0)
                total = progress.get("total", 0)
                pass_rate = progress.get("pass_rate", "")
                if total > 0:
                    progress_str = f" ({verified}/{total} — {pass_rate})"
            lines.append(f"- **{name[:60]}** — `{phase}` {_fmt_uptime(elapsed)}{progress_str}")
        lines.append("")

    # Per-executor breakdown
    executors = dashboard.get("executors", {})
    if executors:
        lines.append("### Executors")
        for name, ex in executors.items():
            active_count = len(ex.get("active_tasks", []))
            completed = len(ex.get("completed_tasks", []))
            failed = len(ex.get("failed_tasks", []))
            total_all = ex.get("total_tasks_all_time", 0)
            lines.append(f"- **{name}**: {active_count} running · {completed} done · {failed} failed · {total_all} total")
        lines.append("")

    # Memory / history from summary
    memory = summary.get("memory", {})
    history = summary.get("history", {})
    if memory or history:
        lines.append("### System Info")
        if memory:
            lines.append(f"- Memory: {memory.get('session_count', 0)} sessions · {memory.get('long_term_count', 0)} long-term entries")
        if history:
            lines.append(f"- History: {history.get('total_entries', 0)} entries")
        lines.append("")

    # Active tasks list (from tasks/active endpoint)
    tasks = active.get("tasks", [])
    if tasks:
        lines.append("### Task Details")
        for t in tasks:
            name = t.get("description", t.get("task_id", "unnamed"))
            phase = t.get("phase", "unknown")
            events = t.get("recent_events", [])
            last_event = events[-1] if events else ""
            lines.append(f"- **{name[:50]}** — `{phase}`")
            if last_event:
                lines.append(f"  _{last_event}_")
        lines.append("")

    lines.append("---")
    return "\n".join(lines)


def _check_trigger_in_messages(messages: list) -> bool:
    """Check if any recent user message contains a trigger phrase."""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        content_lower = content.lower().strip()
        if any(phrase in content_lower for phrase in TRIGGER_PHRASES):
            return True
        break  # Only check the last user message
    return False


def _find_last_assistant_message(messages: list) -> dict | None:
    """Find the last assistant message in the conversation."""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            return msg
    return None


def _fetch_dashboard(api_url: str) -> str | None:
    """Fetch all dashboard data from FM API and render it."""
    try:
        with httpx.Client(timeout=10) as client:
            health = client.get(f"{api_url}/api/health")
            if health.status_code != 200:
                return f"\n\n> ⚠️ Foundry Manager not responding (HTTP {health.status_code})"

            dashboard_resp = client.get(f"{api_url}/api/monitoring/dashboard")
            summary_resp = client.get(f"{api_url}/api/monitoring/summary")
            active_resp = client.get(f"{api_url}/api/monitoring/tasks/active")

            dashboard = dashboard_resp.json() if dashboard_resp.status_code == 200 else {}
            summary = summary_resp.json() if summary_resp.status_code == 200 else {}
            active = active_resp.json() if active_resp.status_code == 200 else {}

            return _render_dashboard(dashboard, summary, active)

    except httpx.ConnectError:
        return f"\n\n> ⚠️ Cannot connect to Foundry Manager at {api_url}"
    except Exception as e:
        return f"\n\n> ⚠️ Dashboard error: {type(e).__name__}: {e}"


class Filter:
    """OWUI Filter — intercepts /dashboard triggers and renders FM monitoring data."""

    class Valves(BaseModel):
        foundry_api_url: str = Field(
            default="http://127.0.0.1:8000",
            description="Foundry Manager API base URL",
        )
        priority: int = Field(
            default=10,
            description="Filter priority (lower = runs first)",
        )

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict, __user__: dict = None) -> dict:
        """Passthrough — detection happens in outlet where we have the response context."""
        return body

    def outlet(self, body: dict, __user__: dict = None) -> dict:
        """If dashboard was triggered, fetch FM data and append to assistant response."""
        messages = body.get("messages", [])
        if not _check_trigger_in_messages(messages):
            return body

        api_url = self.valves.foundry_api_url
        rendered = _fetch_dashboard(api_url)
        if not rendered:
            return body

        # Append to the last assistant message
        assistant_msg = _find_last_assistant_message(messages)
        if assistant_msg:
            existing = assistant_msg.get("content", "")
            assistant_msg["content"] = existing + rendered

        return body


# Also export standalone function for testing
def test_dashboard(api_url: str = "http://127.0.0.1:8000") -> str:
    """Standalone test — fetch and render dashboard."""
    result = _fetch_dashboard(api_url)
    return result or "No data"
