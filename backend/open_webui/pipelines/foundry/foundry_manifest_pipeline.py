"""
Foundry Manager — Manifest Viewer Filter

OWUI Filter that renders the Foundry Manager manifest as structured tables
when the user sends /manifest or "show manifest".

Triggers on: /manifest, show manifest, show verification, show results
Fetches: GET http://127.0.0.1:8000/api/monitoring/dashboard
         GET http://127.0.0.1:8000/api/monitoring/summary
Renders: Structured Markdown table with task verification status
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

TRIGGER_PHRASES = [
    "/manifest",
    "show manifest",
    "show me the manifest",
    "show verification",
    "show me the verification",
    "show results",
    "show me the results",
    "verification status",
    "verify results",
]


def _render_manifest(dashboard: dict, summary: dict) -> str:
    """Render manifest data as structured Markdown tables."""
    lines = ["", "---", "## 📋 Foundry Manifest", ""]

    # Executive summary
    total_active = dashboard.get("total_active", 0)
    total_completed = dashboard.get("total_completed", 0)
    total_failed = dashboard.get("total_failed", 0)
    total_all = total_active + total_completed + total_failed

    lines.append("### Summary")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Total tasks | {total_all} |")
    lines.append(f"| Active | {total_active} |")
    lines.append(f"| Completed | {total_completed} |")
    lines.append(f"| Failed | {total_failed} |")
    if total_all > 0:
        pass_rate = (total_completed / total_all) * 100
        lines.append(f"| Pass rate | {pass_rate:.1f}% |")
    lines.append("")

    # Per-executor breakdown
    executors = dashboard.get("executors", {})
    if executors:
        lines.append("### Executor Breakdown")
        lines.append("| Executor | Active | Completed | Failed | Total | Uptime |")
        lines.append("|----------|--------|-----------|--------|-------|--------|")
        for name, ex in executors.items():
            active = len(ex.get("active_tasks", []))
            completed = len(ex.get("completed_tasks", []))
            failed = len(ex.get("failed_tasks", []))
            total = ex.get("total_tasks_all_time", 0)
            uptime = ex.get("uptime_seconds", 0)
            uptime_str = f"{uptime / 3600:.1f}h" if uptime >= 3600 else f"{uptime / 60:.1f}m"
            lines.append(f"| {name} | {active} | {completed} | {failed} | {total} | {uptime_str} |")
        lines.append("")

    # Active tasks detail
    pending = dashboard.get("pending_tasks", [])
    if pending:
        lines.append("### Active Tasks")
        lines.append("| Task | Phase | Elapsed | Verified | Pass Rate |")
        lines.append("|------|-------|---------|----------|-----------|")
        for t in pending:
            desc = t.get("description", t.get("task_id", "?"))[:40]
            phase = t.get("phase", "?")
            elapsed = t.get("elapsed_seconds", 0)
            elapsed_str = f"{elapsed:.0f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"
            progress = t.get("progress", {})
            verified = progress.get("verified", "-")
            pass_rate = progress.get("pass_rate", "-")
            lines.append(f"| {desc} | `{phase}` | {elapsed_str} | {verified} | {pass_rate} |")
        lines.append("")

    # Completed tasks (last 10)
    completed_tasks = []
    for ex_data in executors.values():
        completed_tasks.extend(ex_data.get("completed_tasks", []))
    completed_tasks.sort(key=lambda t: t.get("last_updated", 0), reverse=True)

    if completed_tasks:
        lines.append("### Recent Completions")
        lines.append("| Task | Description | Verified | Pass Rate | Duration |")
        lines.append("|------|-------------|----------|-----------|----------|")
        for t in completed_tasks[:10]:
            task_id = t.get("task_id", "?")[:12]
            desc = t.get("description", "?")[:35]
            progress = t.get("progress", {})
            verified = progress.get("verified", "-")
            pass_rate = progress.get("pass_rate", "-")
            elapsed = t.get("elapsed_seconds", 0)
            elapsed_str = f"{elapsed:.0f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"
            lines.append(f"| `{task_id}` | {desc} | {verified} | {pass_rate} | {elapsed_str} |")
        lines.append("")

    # Failed tasks
    failed_tasks = []
    for ex_data in executors.values():
        failed_tasks.extend(ex_data.get("failed_tasks", []))

    if failed_tasks:
        lines.append("### ⚠️ Failed Tasks")
        lines.append("| Task | Error |")
        lines.append("|------|-------|")
        for t in failed_tasks[:5]:
            task_id = t.get("task_id", "?")[:12]
            error = t.get("error", "unknown")[:60]
            lines.append(f"| `{task_id}` | {error} |")
        lines.append("")

    # History stats from summary
    history = summary.get("history", {})
    if history:
        lines.append("### History")
        by_type = history.get("by_type", {})
        if by_type:
            lines.append("| Type | Count |")
            lines.append("|------|-------|")
            for htype, count in by_type.items():
                lines.append(f"| {htype} | {count} |")
        lines.append("")

    # Memory stats
    memory = summary.get("memory", {})
    if memory:
        lines.append("### Memory")
        lines.append(f"- Sessions: {memory.get('session_count', 0)}")
        lines.append(f"- Long-term entries: {memory.get('long_term_count', 0)}")
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
        break
    return False


def _find_last_assistant_message(messages: list) -> dict | None:
    """Find the last assistant message in the conversation."""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            return msg
    return None


def _fetch_manifest(api_url: str) -> str | None:
    """Fetch manifest data from FM API and render it."""
    try:
        with httpx.Client(timeout=10) as client:
            health = client.get(f"{api_url}/api/health")
            if health.status_code != 200:
                return f"\n\n> ⚠️ Foundry Manager not responding (HTTP {health.status_code})"

            dashboard_resp = client.get(f"{api_url}/api/monitoring/dashboard")
            summary_resp = client.get(f"{api_url}/api/monitoring/summary")

            dashboard = dashboard_resp.json() if dashboard_resp.status_code == 200 else {}
            summary = summary_resp.json() if summary_resp.status_code == 200 else {}

            return _render_manifest(dashboard, summary)

    except httpx.ConnectError:
        return f"\n\n> ⚠️ Cannot connect to Foundry Manager at {api_url}"
    except Exception as e:
        return f"\n\n> ⚠️ Manifest error: {type(e).__name__}: {e}"


class Filter:
    """OWUI Filter — intercepts /manifest triggers and renders FM verification data."""

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
        """Passthrough — detection happens in outlet."""
        return body

    def outlet(self, body: dict, __user__: dict = None) -> dict:
        """If manifest was triggered, fetch and render the manifest."""
        messages = body.get("messages", [])
        if not _check_trigger_in_messages(messages):
            return body

        api_url = self.valves.foundry_api_url
        rendered = _fetch_manifest(api_url)
        if not rendered:
            return body

        assistant_msg = _find_last_assistant_message(messages)
        if assistant_msg:
            existing = assistant_msg.get("content", "")
            assistant_msg["content"] = existing + rendered

        return body


def test_manifest(api_url: str = "http://127.0.0.1:8000") -> str:
    """Standalone test — fetch and render manifest."""
    result = _fetch_manifest(api_url)
    return result or "No data"
