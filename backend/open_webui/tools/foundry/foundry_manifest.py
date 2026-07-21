"""
Foundry Manager — Manifest Viewer Tool

Reads foundry run manifests and renders them as structured markdown tables
with honest-tier verification (behavioral / partial / weak / existence).
Includes a Mermaid summary chart.

Usage: The LLM calls `get_foundry_manifest(run_id)` to display the
manifest as a visual report.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

FOUNDRY_BASE = Path(r"C:\Users\reese\Projects\Compartmentalized Software Development")
MANIFESTS_DIR = FOUNDRY_BASE / "results" / "manifests"

# Tier definitions (matching foundry §7 honest ledger)
TIER_ICONS = {
    "behavioral": "🟢",
    "partial": "🟡",
    "weak": "🟠",
    "existence": "🔴",
    "failed": "❌",
}

TIER_DESCRIPTIONS = {
    "behavioral": "Full behavioral verification — oracle passed all assertions",
    "partial": "Partial verification — some assertions passed",
    "weak": "Weak verification — structural/syntax check only",
    "existence": "Existence only — NOT verified",
    "failed": "Failed — all attempts exhausted",
}


class Tools:
    def get_foundry_manifest(
        self,
        run_id: str = "cam4_proof14",
        include_chart: bool = True,
    ) -> str:
        """Render a foundry run manifest as a structured audit report with
        a Mermaid pie chart of verification tiers.

        Reads the real manifest JSON from disk and displays:
        - Run metadata (date, models, pipeline config)
        - Per-unit verification table with status, oracle, rung, attempts
        - Mermaid pie chart of tier distribution
        - Honest ledger summary (§7 compliant)

        Args:
            run_id: The run ID to display (e.g. 'cam4_proof14',
                'text_query_proof8'). Use list_foundry_manifests() to see
                available runs.
            include_chart: If True, include a Mermaid pie chart. Default True.

        Use this when the user wants to audit a foundry run, see verification
        results, or inspect the honest ledger.
        """
        try:
            manifest = self._load_manifest(run_id)
            if not manifest:
                return (
                    f"⚠️ No manifest found for run `{run_id}`.\n\n"
                    f"Use `list_foundry_manifests()` to see available runs."
                )

            lines = [f"# 🔍 Foundry Manifest: `{run_id}`\n"]

            # ── Run metadata ──────────────────────────────────────────
            pipeline = manifest.get("pipeline", {})
            if pipeline:
                lines.append("## Pipeline Configuration\n")
                for key, val in pipeline.items():
                    lines.append(f"- **{key}:** `{val}`")
                lines.append("")

            total = manifest.get("total", 0)
            behavioral = manifest.get("behavioral_verified", 0)
            failed = manifest.get("failed", 0)
            date = manifest.get("date", "unknown")

            lines.append(f"**Date:** {date}")
            lines.append(f"**Total units:** {total}")
            lines.append(f"**Behaviorally verified:** {behavioral}/{total}")
            if failed:
                lines.append(f"**Failed:** {failed}")
            lines.append("")

            # ── Per-unit status table ─────────────────────────────────
            units = self._normalize_units(manifest)
            if units:
                lines.append("## Unit Verification Table\n")
                lines.append("| Unit | Status | Oracle | Rung | Attempts | Failure |")
                lines.append("|------|--------|--------|------|----------|---------|")

                tier_counts = {
                    "behavioral": 0,
                    "partial": 0,
                    "weak": 0,
                    "existence": 0,
                    "failed": 0,
                }

                for uid, info in sorted(units.items()):
                    status = info.get("status", "unknown")
                    oracle = info.get("oracle_source", "-")
                    oracle_hash = info.get("oracle_hash", "")[:8]
                    rung = info.get("rung_attempted", "-")
                    attempts = info.get("attempts", "-")
                    failure = info.get("failure_stage") or "-"

                    icon = TIER_ICONS.get(status, "❓")
                    oracle_str = f"{oracle}"
                    if oracle_hash:
                        oracle_str += f" `{oracle_hash}`"

                    lines.append(
                        f"| {uid} | {icon} {status} | {oracle_str} "
                        f"| {rung} | {attempts} | {failure} |"
                    )

                    tier = status if status in tier_counts else "existence"
                    tier_counts[tier] = tier_counts.get(tier, 0) + 1

                lines.append("")

                # ── Mermaid pie chart ─────────────────────────────────
                if include_chart:
                    chart_data = {
                        k: v
                        for k, v in tier_counts.items()
                        if v > 0
                    }
                    if chart_data:
                        lines.append("## Verification Distribution\n")
                        lines.append("```mermaid")
                        lines.append("pie title Verification Tiers")
                        for tier, count in chart_data.items():
                            lines.append(f'    "{tier}" : {count}')
                        lines.append("```")
                        lines.append("")

                # ── Honest Ledger (§7) ────────────────────────────────
                lines.append("---")
                lines.append("## 📊 Honest Ledger (§7 Compliant)\n")
                lines.append(
                    f"- **🟢 Behavioral (fully verified):** "
                    f"{tier_counts['behavioral']}"
                )
                lines.append(
                    f"- **🟡 Partial:** {tier_counts['partial']}"
                )
                lines.append(
                    f"- **🟠 Weak:** {tier_counts['weak']}"
                )
                lines.append(
                    f"- **🔴 Existence only (NOT verified):** "
                    f"{tier_counts['existence']}"
                )
                if tier_counts["failed"]:
                    lines.append(
                        f"- **❌ Failed:** {tier_counts['failed']}"
                    )
                lines.append("")

                if total > 0:
                    pct = (behavioral / total) * 100
                    lines.append(
                        f"**Honest verification rate:** "
                        f"{behavioral}/{total} ({pct:.1f}%)"
                    )

            lines.append("")
            lines.append(
                "_Generated from real manifest artifact on disk. "
                "No synthetic data._"
            )

            return "\n".join(lines)

        except json.JSONDecodeError as e:
            return f"⚠️ Invalid manifest JSON for `{run_id}`: {e}"
        except Exception as e:
            return f"⚠️ Error reading manifest: {type(e).__name__}: {e}"

    def list_foundry_manifests(self) -> str:
        """List all available foundry run manifests.

        Shows run IDs, dates, and verification summaries so you can
        pick one to inspect with get_foundry_manifest().
        """
        try:
            lines = ["# 📋 Available Foundry Manifests\n"]

            manifests = []
            # Check primary manifests directory
            if MANIFESTS_DIR.exists():
                for f in sorted(MANIFESTS_DIR.glob("*.json")):
                    manifests.append(f)

            # Check proof run directories
            proof_dirs = list(
                (FOUNDRY_BASE / "foundry" / "results").glob(
                    "*/verified/manifest.json"
                )
            )
            for f in proof_dirs:
                if f not in manifests:
                    manifests.append(f)

            if not manifests:
                lines.append("_No manifest files found._")
                return "\n".join(lines)

            lines.append(f"Found {len(manifests)} manifests:\n")
            lines.append("| Run ID | Date | Total | Verified | Rate |")
            lines.append("|--------|------|-------|----------|------|")

            for manifest_path in sorted(manifests, reverse=True):
                try:
                    data = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    run_id = data.get(
                        "run_id", manifest_path.stem
                    )
                    date = data.get("date", "?")
                    total = data.get("total", 0)
                    behavioral = data.get("behavioral_verified", 0)
                    rate = (
                        f"{behavioral/total*100:.0f}%"
                        if total > 0
                        else "?"
                    )
                    lines.append(
                        f"| `{run_id}` | {date} | {total} "
                        f"| {behavioral} | {rate} |"
                    )
                except Exception:
                    lines.append(
                        f"| `{manifest_path.stem}` | ? | ? | ? | ? |"
                    )

            lines.append("")
            lines.append(
                "Use `get_foundry_manifest(run_id)` to inspect a specific run."
            )

            return "\n".join(lines)

        except Exception as e:
            return f"⚠️ Error listing manifests: {type(e).__name__}: {e}"

    def _load_manifest(self, run_id: str) -> Optional[dict]:
        """Load a manifest by run ID from known locations.

        Handles two formats:
        - cam4: results/manifests/<run_id>.json ({"units": {...}})
        - text_query: foundry/results/<run_id>/verified/manifest.json
          ({"verified": {...}, "failed": {...}})
        """
        candidates = [
            MANIFESTS_DIR / f"{run_id}.json",
            FOUNDRY_BASE / "foundry" / "results" / run_id / "verified" / "manifest.json",
            FOUNDRY_BASE / "foundry" / "results" / run_id / "manifest.json",
        ]
        for c in candidates:
            if c.exists():
                return json.loads(c.read_text(encoding="utf-8"))

        # Fuzzy search: find any manifest with this ID as substring
        if MANIFESTS_DIR.exists():
            for f in MANIFESTS_DIR.glob("*.json"):
                if run_id.lower() in f.stem.lower():
                    return json.loads(f.read_text(encoding="utf-8"))

        # Search proof run directories
        proof_dirs = list(
            (FOUNDRY_BASE / "foundry" / "results").glob("*/verified/manifest.json")
        )
        for f in proof_dirs:
            if run_id.lower() in f.parent.parent.name.lower():
                return json.loads(f.read_text(encoding="utf-8"))

        return None

    def _normalize_units(self, manifest: dict) -> dict:
        """Normalize manifest to {unit_name: {status, ...}} format.

        Handles both cam4 and text_query manifest structures.
        """
        # Format 1: cam4-style — {"units": {"name": {"status": "behavioral"}}}
        units = manifest.get("units", {})
        if isinstance(units, dict) and units:
            return units

        # Format 1b: cam4-style list
        if isinstance(units, list) and units:
            result = {}
            for unit in units:
                uid = unit.get("unit", unit.get("name", "unknown"))
                result[uid] = unit
            return result

        # Format 2: text_query-style — {"verified": {...}, "failed": {...}}
        result = {}
        for tier_key, tier_status in [
            ("verified", "behavioral"),
            ("partial", "partial"),
            ("weak", "weak"),
            ("existence", "existence"),
            ("failed", "failed"),
        ]:
            tier_units = manifest.get(tier_key, {})
            if isinstance(tier_units, dict):
                for uid, info in tier_units.items():
                    if isinstance(info, dict):
                        info["status"] = tier_status
                    else:
                        info = {"status": tier_status, "detail": str(info)}
                    result[uid] = info

        return result
