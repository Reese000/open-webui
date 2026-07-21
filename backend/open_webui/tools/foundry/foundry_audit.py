"""
Foundry Manager — Audit Ledger Tool

Reads a run manifest from the Foundry harness and prints the honest ledger
with tier-separated verification (behavioral / partial / weak / existence).

Usage: The LLM calls `get_foundry_audit(run_id)` to display the audit report.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx

FOUNDRY_API_BASE = "http://127.0.0.1:8000"


# ─── Tier definitions (matching foundry audit semantics) ──────────────────────

TIER_ICONS = {
    "behavioral": "🟢",
    "partial": "🟡",
    "weak": "🟠",
    "existence": "🔴",
}

TIER_DESCRIPTIONS = {
    "behavioral": "Full behavioral verification — oracle passed all assertions",
    "partial": "Partial verification — some assertions passed, not all",
    "weak": "Weak verification — structural/syntax check only",
    "existence": "Existence only — file exists but NOT verified (never counts as verified)",
}


class Tools:
    def get_foundry_audit(self, run_id: str) -> str:
        """Read a foundry run manifest and display the honest audit ledger.
        Shows each unit's verification tier (behavioral/partial/weak/existence)
        separately, with honest counting — existence-only items are never
        counted as verified.

        Args:
            run_id: The run ID to audit (e.g. 'cam4-proof-001').

        Use this when the user wants to audit a foundry run's results,
        verify what was actually proven, or see the honest ledger.
        """
        try:
            # Try to find the manifest via the monitoring system
            # First, check if there's a task with this ID
            with httpx.Client(timeout=10) as client:
                task_resp = client.get(f"{FOUNDRY_API_BASE}/api/tasks/{run_id}")
                artifacts_resp = client.get(f"{FOUNDRY_API_BASE}/api/tasks/{run_id}/artifacts")

            lines = [f"# 🔍 Foundry Audit: `{run_id}`\n"]

            # Try to find manifest file from artifacts
            manifest_path = None
            if artifacts_resp.status_code == 200:
                arts = artifacts_resp.json().get("artifacts", [])
                for a in arts:
                    if "manifest" in a.get("artifact_type", "").lower() or "manifest" in a.get("path", "").lower():
                        manifest_path = a.get("path")
                        break

            if not manifest_path:
                # Try common manifest locations
                candidates = [
                    Path(f"results/manifests/{run_id}.json"),
                    Path(f"output/{run_id}/manifest.json"),
                    Path(f".foundry/results/manifests/{run_id}.json"),
                ]
                for c in candidates:
                    if c.exists():
                        manifest_path = str(c)
                        break

            if not manifest_path:
                lines.append(f"⚠️ No manifest found for run `{run_id}`.")
                lines.append("\nSearched:")
                lines.append("- Foundry Manager task artifacts")
                lines.append("- `results/manifests/{run_id}.json`")
                lines.append("- `output/{run_id}/manifest.json`")
                lines.append("- `.foundry/results/manifests/{run_id}.json`")
                return "\n".join(lines)

            # Read the manifest
            manifest_file = Path(manifest_path)
            if not manifest_file.exists():
                return f"⚠️ Manifest file not found at `{manifest_path}`"

            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

            # Parse the manifest
            units = manifest.get("units", manifest.get("results", []))
            if not units:
                # Try flat structure
                units = [manifest] if "unit" in manifest else []

            lines.append(f"**Manifest:** `{manifest_path}`")
            lines.append(f"**Units:** {len(units)}\n")

            # Categorize by tier
            tier_counts = {tier: [] for tier in TIER_ICONS}
            verified_count = 0
            total_count = 0

            for unit in units:
                total_count += 1
                name = unit.get("unit", unit.get("name", "unknown"))
                tier = unit.get("tier", unit.get("verification_tier", "existence")).lower()
                status = unit.get("status", "unknown")
                attempts = unit.get("attempts", unit.get("rung_attempted", "?"))
                failure_stage = unit.get("failure_stage", "")

                if tier not in tier_counts:
                    tier = "existence"

                tier_counts[tier].append({
                    "name": name,
                    "status": status,
                    "attempts": attempts,
                    "failure_stage": failure_stage,
                })

                # Only behavioral counts as verified (§7 honest ledger)
                if tier == "behavioral":
                    verified_count += 1

            # Render tier by tier
            for tier, items in tier_counts.items():
                if not items:
                    continue
                icon = TIER_ICONS[tier]
                desc = TIER_DESCRIPTIONS[tier]
                lines.append(f"## {icon} {tier.title()} ({len(items)})")
                lines.append(f"_{desc}_\n")

                for item in items:
                    status_icon = "✅" if item["status"] == "completed" else "❌"
                    line = f"  {status_icon} **{item['name']}** — {item['status']}"
                    if item["attempts"] != "?":
                        line += f" (attempts: {item['attempts']})"
                    lines.append(line)
                    if item["failure_stage"]:
                        lines.append(f"    ↳ Failed at: {item['failure_stage']}")
                lines.append("")

            # Honest summary
            lines.append("---")
            lines.append(f"## 📊 Honest Ledger")
            lines.append(f"- **Total units:** {total_count}")
            lines.append(f"- **Behaviorally verified:** {verified_count} 🟢")
            lines.append(f"- **Partial:** {len(tier_counts['partial'])} 🟡")
            lines.append(f"- **Weak:** {len(tier_counts['weak'])} 🟠")
            lines.append(f"- **Existence only (NOT verified):** {len(tier_counts['existence'])} 🔴")

            if total_count > 0:
                pct = (verified_count / total_count) * 100
                lines.append(f"\n**Honest verification rate:** {verified_count}/{total_count} ({pct:.1f}%)")

            return "\n".join(lines)

        except httpx.ConnectError:
            return f"⚠️ Cannot connect to Foundry Manager at {FOUNDRY_API_BASE}."
        except json.JSONDecodeError as e:
            return f"⚠️ Invalid manifest JSON: {e}"
        except Exception as e:
            return f"⚠️ Error during audit: {type(e).__name__}: {e}"
