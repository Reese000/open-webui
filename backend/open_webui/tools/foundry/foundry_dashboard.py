"""
Foundry Manager — Monitoring Dashboard Tool

Fetches the real-time monitoring dashboard from the Foundry Manager API
and renders it as formatted text inside the chat.

Usage: The LLM calls `get_foundry_dashboard()` to display current system status.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

FOUNDRY_API_BASE = "http://127.0.0.1:8000"


class Tools:
    def get_foundry_dashboard(self) -> str:
        """Fetch the Foundry Manager monitoring dashboard showing all active tasks,
        executor status, and system health. Returns a formatted summary of the
        current foundry system state.

        Use this when the user asks about system status, active tasks, or
        wants to see what the foundry is currently doing.
        """
        try:
            # Health check first
            with httpx.Client(timeout=10) as client:
                health = client.get(f"{FOUNDRY_API_BASE}/api/health")
                if health.status_code != 200:
                    return f"⚠️ Foundry Manager is not responding (HTTP {health.status_code}). Is the server running on {FOUNDRY_API_BASE}?"

                # Get monitoring dashboard
                dashboard = client.get(f"{FOUNDRY_API_BASE}/api/monitoring/dashboard")
                summary = client.get(f"{FOUNDRY_API_BASE}/api/monitoring/summary")
                active = client.get(f"{FOUNDRY_API_BASE}/api/monitoring/tasks/active")

            lines = ["# 🏭 Foundry Manager Dashboard\n"]

            # Health
            health_data = health.json()
            lines.append(f"**Status:** {health_data.get('status', 'unknown')} | **Version:** {health_data.get('version', '?')}\n")

            # Summary
            if summary.status_code == 200:
                s = summary.json()
                lines.append("## System Summary")
                for key, val in s.items():
                    if isinstance(val, dict):
                        lines.append(f"- **{key}:** {json.dumps(val, indent=2)[:200]}")
                    else:
                        lines.append(f"- **{key}:** {val}")
                lines.append("")

            # Active tasks
            if active.status_code == 200:
                tasks = active.json().get("tasks", [])
                lines.append(f"## Active Tasks ({len(tasks)})")
                if tasks:
                    for t in tasks:
                        name = t.get("name", t.get("task_id", "unnamed"))
                        status = t.get("status", "unknown")
                        phase = t.get("phase", "")
                        lines.append(f"- **{name}** — {status} ({phase})")
                else:
                    lines.append("_No active tasks._")
                lines.append("")

            # Dashboard detail
            if dashboard.status_code == 200:
                d = dashboard.json()
                if isinstance(d, dict) and d:
                    lines.append("## Dashboard Detail")
                    for key, val in d.items():
                        if isinstance(val, (dict, list)):
                            lines.append(f"- **{key}:** `{json.dumps(val)[:150]}`")
                        else:
                            lines.append(f"- **{key}:** {val}")

            return "\n".join(lines)

        except httpx.ConnectError:
            return f"⚠️ Cannot connect to Foundry Manager at {FOUNDRY_API_BASE}. Is the server running?"
        except Exception as e:
            return f"⚠️ Error fetching dashboard: {type(e).__name__}: {e}"

    def get_foundry_stats(self) -> str:
        """Fetch comprehensive system statistics from the Foundry Manager,
        including executor info, task counts, and memory/history stats.

        Use this when the user wants detailed system metrics.
        """
        try:
            with httpx.Client(timeout=10) as client:
                stats = client.get(f"{FOUNDRY_API_BASE}/api/stats")
                executors = client.get(f"{FOUNDRY_API_BASE}/api/executors")

            lines = ["# 📊 Foundry Manager Stats\n"]

            if stats.status_code == 200:
                s = stats.json()
                for key, val in s.items():
                    if isinstance(val, dict):
                        lines.append(f"## {key}")
                        for k2, v2 in val.items():
                            lines.append(f"- **{k2}:** {v2}")
                    else:
                        lines.append(f"- **{key}:** {val}")
                lines.append("")

            if executors.status_code == 200:
                execs = executors.json().get("executors", [])
                lines.append("## Executors")
                for e in execs:
                    lines.append(f"- **{e['name']}:** {e.get('description', '')}")
                    caps = e.get("capabilities", [])
                    if caps:
                        lines.append(f"  Capabilities: {', '.join(caps)}")

            return "\n".join(lines)

        except httpx.ConnectError:
            return f"⚠️ Cannot connect to Foundry Manager at {FOUNDRY_API_BASE}."
        except Exception as e:
            return f"⚠️ Error fetching stats: {type(e).__name__}: {e}"
