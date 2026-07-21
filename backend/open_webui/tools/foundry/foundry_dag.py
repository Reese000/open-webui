"""
Foundry Manager — DAG Visualization Tool

Reads a DAG YAML file from the foundry harness and renders it as a
Mermaid diagram in chat. Open WebUI natively renders ```mermaid code
blocks as SVG diagrams.

Usage: The LLM calls `get_foundry_dag(project_path)` to visualize
the dependency graph of a foundry project.
"""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Optional

# Base directory for foundry harness artifacts
FOUNDRY_BASE = Path(r"C:\Users\reese\Projects\Compartmentalized Software Development")

# Predefined project paths for quick access
PROJECT_PATHS = {
    "text_query": "foundry/results/text_query_proof8",
    "text_query_latest": "foundry/results/text_query_proof8",
    "string_utils": "projects/string_utils",
    "letter_frequency": "examples/letter_frequency",
    "cam4": "foundry/results",
    "root": ".",
}


class Tools:
    def get_foundry_dag(
        self,
        project_path: str = "text_query",
        include_status: bool = True,
    ) -> str:
        """Render a foundry project's DAG as a visual Mermaid dependency diagram.

        Reads the dag.yaml file and optionally overlays verification status
        from the manifest, coloring nodes green (verified), yellow (partial),
        orange (weak), or red (failed/missing).

        Args:
            project_path: Path relative to the foundry base directory, or a
                predefined shortcut: 'text_query', 'string_utils',
                'letter_frequency', 'root'.
            include_status: If True, overlay verification status from the
                manifest file (green=behavioral, red=failed). Default True.

        Use this when the user wants to see the dependency graph of a foundry
        project, understand unit relationships, or visualize build order.
        """
        try:
            # Resolve path
            rel_path = PROJECT_PATHS.get(project_path, project_path)
            dag_file = FOUNDRY_BASE / rel_path / "dag.yaml"

            if not dag_file.exists():
                # Try finding any dag.yaml in the directory
                candidates = list((FOUNDRY_BASE / rel_path).glob("**/dag.yaml"))
                if candidates:
                    dag_file = candidates[0]
                else:
                    return (
                        f"⚠️ No dag.yaml found at `{dag_file}`.\n\n"
                        f"Available shortcuts: {', '.join(PROJECT_PATHS.keys())}\n"
                        f"Or provide a relative path from:\n`{FOUNDRY_BASE}`"
                    )

            # Load DAG
            dag = yaml.safe_load(dag_file.read_text(encoding="utf-8"))
            units = dag.get("units", [])

            if not units:
                return f"⚠️ DAG file `{dag_file.name}` contains no units."

            # Load manifest if available and status requested
            status_map = {}
            if include_status:
                manifest = self._load_manifest(dag_file.parent)
                if manifest:
                    status_map = self._extract_status(manifest)

            # Build Mermaid diagram
            lines = ["# 🔷 Foundry DAG Visualization\n"]
            lines.append(f"**Project:** `{rel_path}`")
            lines.append(f"**Units:** {len(units)}")
            if status_map:
                verified = sum(
                    1 for s in status_map.values() if s == "behavioral"
                )
                lines.append(f"**Verified:** {verified}/{len(status_map)}")
            lines.append("")

            # Mermaid flowchart
            lines.append("```mermaid")
            lines.append("graph TD")

            # Node definitions with styling
            for unit in units:
                uid = unit["id"]
                node_label = uid.replace("_", "_<br>")
                status = status_map.get(uid, "pending")

                if status == "behavioral":
                    style = ":::verified"
                    node_label = f"✅ {uid}"
                elif status == "partial":
                    style = ":::partial"
                    node_label = f"🟡 {uid}"
                elif status == "weak":
                    style = ":::weak"
                    node_label = f"🟠 {uid}"
                elif status in ("failed", "escalation_exhausted"):
                    style = ":::failed"
                    node_label = f"❌ {uid}"
                else:
                    style = ":::pending"

                # Sanitize node ID for Mermaid (alphanumeric + underscore only)
                safe_id = uid.replace("-", "_")
                lines.append(f'    {safe_id}["{node_label}"]{style}')

            # Edge definitions (dependencies)
            for unit in units:
                uid = unit["id"]
                deps = unit.get("deps", [])
                safe_id = uid.replace("-", "_")
                for dep in deps:
                    safe_dep = dep.replace("-", "_")
                    lines.append(f"    {safe_dep} --> {safe_id}")

            # Styling classes
            lines.append("")
            lines.append("    classDef verified fill:#22c55e,stroke:#16a34a,color:#fff")
            lines.append("    classDef partial fill:#eab308,stroke:#ca8a04,color:#fff")
            lines.append("    classDef weak fill:#f97316,stroke:#ea580c,color:#fff")
            lines.append("    classDef failed fill:#ef4444,stroke:#dc2626,color:#fff")
            lines.append("    classDef pending fill:#6b7280,stroke:#4b5563,color:#fff")
            lines.append("```")
            lines.append("")

            # Legend
            lines.append("**Legend:**")
            lines.append("- ✅ Green = behavioral (fully verified)")
            lines.append("- 🟡 Yellow = partial verification")
            lines.append("- 🟠 Orange = weak verification")
            lines.append("- ❌ Red = failed")
            lines.append("- ⬜ Gray = pending/not run")
            lines.append("")
            lines.append(
                "_This diagram is generated from real `dag.yaml` + manifest "
                "artifacts on disk. No synthetic data._"
            )

            return "\n".join(lines)

        except yaml.YAMLError as e:
            return f"⚠️ Error parsing DAG YAML: {e}"
        except Exception as e:
            return f"⚠️ Error rendering DAG: {type(e).__name__}: {e}"

    def list_foundry_projects(self) -> str:
        """List available foundry projects and proof runs that have DAG files.

        Use this to discover what projects are available before calling
        get_foundry_dag().
        """
        try:
            lines = ["# 📁 Available Foundry Projects\n"]

            # Scan for dag.yaml files
            dag_files = list(FOUNDRY_BASE.glob("**/dag.yaml"))
            dag_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            if not dag_files:
                lines.append("_No DAG files found in the foundry directory._")
                return "\n".join(lines)

            lines.append(f"Found {len(dag_files)} projects with DAG definitions:\n")

            for dag_file in dag_files[:20]:  # Limit to 20 most recent
                rel = dag_file.relative_to(FOUNDRY_BASE)
                parent = rel.parent
                dag = yaml.safe_load(dag_file.read_text(encoding="utf-8"))
                unit_count = len(dag.get("units", []))

                # Check for manifest
                manifest = self._load_manifest(dag_file.parent)
                status_str = ""
                if manifest:
                    status_map = self._extract_status(manifest)
                    verified = sum(
                        1 for s in status_map.values() if s == "behavioral"
                    )
                    total = len(status_map)
                    status_str = f" — {verified}/{total} verified"

                lines.append(f"- **`{parent}`** — {unit_count} units{status_str}")

            lines.append("")
            lines.append(
                "Use `get_foundry_dag(project_path)` with the path (e.g. "
                "'text_query' or 'projects/string_utils')."
            )

            return "\n".join(lines)

        except Exception as e:
            return f"⚠️ Error listing projects: {type(e).__name__}: {e}"

    def _load_manifest(self, project_dir: Path) -> Optional[dict]:
        """Try to load a manifest from common locations.

        Handles two manifest formats:
        - cam4: {"units": {"name": {"status": ...}}}
        - text_query: {"verified": {"name": ...}, "failed": {"name": ...}}
        """
        candidates = [
            project_dir / "verified" / "manifest.json",
            project_dir / "manifest.json",
            FOUNDRY_BASE / "results" / "manifests" / f"{project_dir.name}.json",
        ]
        for c in candidates:
            if c.exists():
                import json

                return json.loads(c.read_text(encoding="utf-8"))
        return None

    def _extract_status(self, manifest: dict) -> dict:
        """Extract unit_id → status mapping from a manifest.

        Handles both cam4 format (units dict with status field) and
        text_query format (verified/failed/weak/existence top-level keys).
        """
        status_map = {}

        # Format 1: cam4-style — {"units": {"name": {"status": "behavioral"}}}
        units = manifest.get("units", {})
        if isinstance(units, dict) and units:
            for uid, info in units.items():
                status = info.get("status", "unknown")
                status_map[uid] = status
            return status_map

        # Format 1b: cam4-style list — {"units": [{"unit": "name", "tier": ...}]}
        if isinstance(units, list) and units:
            for unit in units:
                uid = unit.get("unit", unit.get("name", "unknown"))
                status = unit.get("tier", unit.get("status", "unknown"))
                status_map[uid] = status
            return status_map

        # Format 2: text_query-style — {"verified": {...}, "failed": {...}}
        for tier_key, tier_status in [
            ("verified", "behavioral"),
            ("partial", "partial"),
            ("weak", "weak"),
            ("existence", "existence"),
            ("failed", "failed"),
        ]:
            tier_units = manifest.get(tier_key, {})
            if isinstance(tier_units, dict):
                for uid in tier_units:
                    status_map[uid] = tier_status

        return status_map
