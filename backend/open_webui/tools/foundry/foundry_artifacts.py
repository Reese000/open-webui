"""
Foundry Manager — Task Artifacts Tool

Fetches and pretty-prints a task's artifacts from the Foundry Manager API.
Shows file paths, types, descriptions, and existence status.

Usage: The LLM calls `get_foundry_artifacts(task_id)` to display task artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx

FOUNDRY_API_BASE = "http://127.0.0.1:8000"


class Tools:
    def get_foundry_artifacts(self, task_id: str) -> str:
        """Fetch and display all artifacts produced by a specific foundry task.
        Shows file paths, artifact types, descriptions, and whether each file
        exists on disk.

        Args:
            task_id: The task ID to fetch artifacts for.

        Use this when the user wants to see what files a task produced or
        verify that task outputs exist.
        """
        try:
            with httpx.Client(timeout=10) as client:
                # Get task status first
                task_resp = client.get(f"{FOUNDRY_API_BASE}/api/tasks/{task_id}")
                if task_resp.status_code == 404:
                    return f"⚠️ Task `{task_id}` not found in the Foundry Manager."

                task_data = task_resp.json()

                # Get artifacts
                artifacts_resp = client.get(f"{FOUNDRY_API_BASE}/api/tasks/{task_id}/artifacts")

            lines = [f"# 📦 Task Artifacts: `{task_id}`\n"]

            # Task status
            status = task_data.get("status", "unknown")
            desc = task_data.get("description", "")
            lines.append(f"**Status:** {status}")
            if desc:
                lines.append(f"**Description:** {desc}")
            lines.append("")

            # Artifacts
            if artifacts_resp.status_code == 200:
                arts = artifacts_resp.json().get("artifacts", [])
                lines.append(f"## Artifacts ({len(arts)})\n")

                if arts:
                    for a in arts:
                        exists = "✅" if a.get("exists", False) else "❌"
                        art_type = a.get("artifact_type", "unknown")
                        path = a.get("path", "?")
                        desc = a.get("description", "")

                        lines.append(f"{exists} **[{art_type}]** `{path}`")
                        if desc:
                            lines.append(f"   _{desc}_")
                        lines.append("")

                    # Summary
                    total = len(arts)
                    existing = sum(1 for a in arts if a.get("exists", False))
                    lines.append(f"---\n**{existing}/{total}** artifacts exist on disk.")
                else:
                    lines.append("_No artifacts recorded for this task._")
            else:
                lines.append(f"⚠️ Could not fetch artifacts (HTTP {artifacts_resp.status_code})")

            return "\n".join(lines)

        except httpx.ConnectError:
            return f"⚠️ Cannot connect to Foundry Manager at {FOUNDRY_API_BASE}."
        except Exception as e:
            return f"⚠️ Error fetching artifacts: {type(e).__name__}: {e}"

    def get_foundry_task(self, task_id: str) -> str:
        """Get detailed status of a specific foundry task including progress
        and event count.

        Args:
            task_id: The task ID to check.

        Use this when the user wants to know the status of a specific task.
        """
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{FOUNDRY_API_BASE}/api/tasks/{task_id}")

            if resp.status_code == 404:
                return f"⚠️ Task `{task_id}` not found."

            data = resp.json()
            lines = [f"# 🔍 Task: `{task_id}`\n"]
            for key, val in data.items():
                if isinstance(val, dict):
                    lines.append(f"- **{key}:**\n```json\n{json.dumps(val, indent=2)[:500]}\n```")
                else:
                    lines.append(f"- **{key}:** {val}")

            return "\n".join(lines)

        except httpx.ConnectError:
            return f"⚠️ Cannot connect to Foundry Manager at {FOUNDRY_API_BASE}."
        except Exception as e:
            return f"⚠️ Error: {type(e).__name__}: {e}"

    def list_foundry_tasks(self) -> str:
        """List all tasks in the Foundry Manager with their current status.

        Use this when the user wants an overview of all tasks.
        """
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{FOUNDRY_API_BASE}/api/tasks")

            if resp.status_code != 200:
                return f"⚠️ Could not list tasks (HTTP {resp.status_code})"

            tasks = resp.json().get("tasks", [])
            lines = [f"# 📋 Foundry Tasks ({len(tasks)})\n"]

            if tasks:
                for t in tasks:
                    tid = t.get("task_id", "?")[:8]
                    status = t.get("status", "?")
                    desc = t.get("description", "")[:60]
                    lines.append(f"- `{tid}...` **{status}** — {desc}")
            else:
                lines.append("_No tasks found._")

            return "\n".join(lines)

        except httpx.ConnectError:
            return f"⚠️ Cannot connect to Foundry Manager at {FOUNDRY_API_BASE}."
        except Exception as e:
            return f"⚠️ Error: {type(e).__name__}: {e}"
