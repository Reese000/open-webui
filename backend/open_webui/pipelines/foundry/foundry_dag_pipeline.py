"""
Foundry Manager — DAG Visualizer Filter

OWUI Filter that renders the Foundry Manager DAG as a Mermaid diagram
when the user sends /dag or "show dag".

Triggers on: /dag, show dag, show dependency graph
Fetches: GET http://127.0.0.1:8000/api/foundry/dag
Renders: Mermaid flowchart diagram of the task dependency graph
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

TRIGGER_PHRASES = [
    "/dag",
    "show dag",
    "show me the dag",
    "show dependency",
    "show me the dependency",
    "dependency graph",
    "dag diagram",
    "dag visualiz",
]


def _render_dag_mermaid(dag_data: dict) -> str:
    """Render DAG data as a Mermaid flowchart diagram.

    Handles both generic {nodes, edges} and FM-specific {units, edges, status_map} formats.
    """
    if not dag_data:
        return "_No DAG data available._"

    # Handle FM-specific format: {units: [{id, deps}], edges: [{from, to}], status_map: {id: status}}
    units = dag_data.get("units", [])
    nodes = dag_data.get("nodes", [])
    edges = dag_data.get("edges", dag_data.get("dependencies", []))
    status_map = dag_data.get("status_map", {})
    name = dag_data.get("name", dag_data.get("project", dag_data.get("project_path", "foundry-dag")))

    # Merge units into nodes if FM format
    if units and not nodes:
        nodes = [{"id": u["id"], "path": u.get("path", ""), "deps": u.get("deps", [])} for u in units]
        # Derive edges from deps if not provided
        if not edges:
            edges = []
            for u in units:
                for dep in u.get("deps", []):
                    edges.append({"from": dep, "to": u["id"]})

    if not nodes and not edges:
        # Try flat structure: {"unit_name": {"depends_on": [...]}, ...}
        flat_nodes = []
        flat_edges = []
        for key, val in dag_data.items():
            if isinstance(val, dict) and "depends_on" in val:
                flat_nodes.append(key)
                for dep in val["depends_on"]:
                    flat_edges.append((dep, key))
            elif isinstance(val, dict) and "dependencies" in val:
                flat_nodes.append(key)
                for dep in val["dependencies"]:
                    flat_edges.append((dep, key))

        if flat_nodes:
            nodes = flat_nodes
            edges = [{"from": f, "to": t} for f, t in flat_edges]

    if not nodes:
        return "_No nodes found in DAG._"

    lines = ["", "---", f"## 📊 Foundry DAG: `{name}`", ""]

    def safe_id(name: str) -> str:
        return name.replace("-", "_").replace(".", "_").replace(" ", "_").replace("/", "_")

    # Status-to-style mapping
    STATUS_STYLES = {
        "behavioral": "verified",
        "partial": "partial",
        "weak": "failed",
        "existence": "partial",
        "verified": "verified",
        "failed": "failed",
    }

    lines.append("```mermaid")
    lines.append("graph TD")

    for node in nodes:
        if isinstance(node, dict):
            node_id = safe_id(node.get("id", node.get("name", "unknown")))
            node_label = node.get("name", node.get("id", "unknown"))
            # Check status_map for verification status
            status = status_map.get(node.get("id", ""), "")
            style_class = STATUS_STYLES.get(status, "")
            style = f"::{style_class}" if style_class else ""
            lines.append(f"    {node_id}[\"{node_label}\"]{style}")
        else:
            lines.append(f"    {safe_id(node)}[\"{node}\"]")

    for edge in edges:
        if isinstance(edge, dict):
            src = safe_id(edge.get("from", edge.get("source", edge.get("upstream", ""))))
            dst = safe_id(edge.get("to", edge.get("target", edge.get("downstream", ""))))
            lines.append(f"    {src} --> {dst}")
        elif isinstance(edge, (list, tuple)) and len(edge) == 2:
            lines.append(f"    {safe_id(edge[0])} --> {safe_id(edge[1])}")

    lines.append("    classDef verified fill:#2d6a4f,color:#fff")
    lines.append("    classDef partial fill:#e9c46a,color:#000")
    lines.append("    classDef failed fill:#d00000,color:#fff")
    lines.append("```")
    lines.append("")
    lines.append(f"**Nodes:** {len(nodes)} | **Edges:** {len(edges)}")

    # Status summary from status_map
    if status_map:
        from collections import Counter
        counts = Counter(status_map.values())
        status_parts = [f"{s}: {c}" for s, c in counts.most_common()]
        lines.append(f"**Status:** {' · '.join(status_parts)}")

    lines.append("---")

    return "\n".join(lines)


def _render_dag_text_tree(dag_data: dict) -> str:
    """Render DAG as a text tree fallback.

    Handles both generic {nodes, edges} and FM-specific {units, edges, status_map} formats.
    """
    if not dag_data:
        return "_No DAG data available._"

    # Handle FM-specific format
    units = dag_data.get("units", [])
    nodes = dag_data.get("nodes", [])
    edges = dag_data.get("edges", dag_data.get("dependencies", []))
    status_map = dag_data.get("status_map", {})
    name = dag_data.get("name", dag_data.get("project", dag_data.get("project_path", "foundry-dag")))

    if units and not nodes:
        nodes = [{"id": u["id"], "path": u.get("path", ""), "deps": u.get("deps", [])} for u in units]
        if not edges:
            edges = []
            for u in units:
                for dep in u.get("deps", []):
                    edges.append({"from": dep, "to": u["id"]})

    lines = ["", "---", f"## 📊 Foundry DAG: `{name}` (text view)", ""]

    if not nodes:
        return "\n".join(lines) + "_No nodes found._"

    children = {}
    for edge in edges:
        if isinstance(edge, dict):
            src = edge.get("from", edge.get("source", ""))
            dst = edge.get("to", edge.get("target", ""))
        elif isinstance(edge, (list, tuple)) and len(edge) == 2:
            src, dst = edge
        else:
            continue
        children.setdefault(src, []).append(dst)

    targets = {
        e.get("to", e.get("target", "")) if isinstance(e, dict) else (e[1] if isinstance(e, (list, tuple)) else "")
        for e in edges
    }
    node_names = [n if isinstance(n, str) else n.get("id", n.get("name", "")) for n in nodes]
    roots = [n for n in node_names if n not in targets]

    def render_node(node_name: str, prefix: str, is_last: bool):
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{node_name}")
        child_prefix = prefix + ("    " if is_last else "│   ")
        child_list = children.get(node_name, [])
        for i, child in enumerate(child_list):
            render_node(child, child_prefix, i == len(child_list) - 1)

    for i, root in enumerate(roots):
        render_node(root, "", i == len(roots) - 1)

    connected = set(targets) | set(children.keys())
    orphans = [n for n in node_names if n not in connected]
    if orphans:
        lines.append("")
        lines.append("**Disconnected:**")
        for o in orphans:
            lines.append(f"  - {o}")

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


def _fetch_dag(api_url: str, render_mode: str = "mermaid", project_path: str = "text_query") -> str | None:
    """Fetch DAG data from FM API and render it."""
    try:
        with httpx.Client(timeout=10) as client:
            health = client.get(f"{api_url}/api/health")
            if health.status_code != 200:
                return f"\n\n> ⚠️ Foundry Manager not responding (HTTP {health.status_code})"

            # Try the DAG endpoint with project_path
            dag_resp = client.get(f"{api_url}/api/foundry/dag", params={"project_path": project_path})
            if dag_resp.status_code == 200:
                dag_data = dag_resp.json()
            else:
                # Fallback: try without project_path
                dag_resp = client.get(f"{api_url}/api/foundry/dag")
                dag_data = dag_resp.json() if dag_resp.status_code == 200 else {}

            if render_mode == "text":
                return _render_dag_text_tree(dag_data)
            elif render_mode == "both":
                return _render_dag_mermaid(dag_data) + "\n\n" + _render_dag_text_tree(dag_data)
            else:
                return _render_dag_mermaid(dag_data)

    except httpx.ConnectError:
        return f"\n\n> ⚠️ Cannot connect to Foundry Manager at {api_url}"
    except Exception as e:
        return f"\n\n> ⚠️ DAG error: {type(e).__name__}: {e}"


class Filter:
    """OWUI Filter — intercepts /dag triggers and renders FM DAG as Mermaid."""

    class Valves(BaseModel):
        foundry_api_url: str = Field(
            default="http://127.0.0.1:8000",
            description="Foundry Manager API base URL",
        )
        priority: int = Field(
            default=10,
            description="Filter priority (lower = runs first)",
        )
        render_mode: str = Field(
            default="mermaid",
            description="Render mode: 'mermaid', 'text', or 'both'",
        )

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict, __user__: dict = None) -> dict:
        """Passthrough — detection happens in outlet."""
        return body

    def outlet(self, body: dict, __user__: dict = None) -> dict:
        """If DAG was triggered, fetch and render the DAG."""
        messages = body.get("messages", [])
        if not _check_trigger_in_messages(messages):
            return body

        api_url = self.valves.foundry_api_url
        render_mode = self.valves.render_mode
        rendered = _fetch_dag(api_url, render_mode)
        if not rendered:
            return body

        assistant_msg = _find_last_assistant_message(messages)
        if assistant_msg:
            existing = assistant_msg.get("content", "")
            assistant_msg["content"] = existing + rendered

        return body


def test_dag(api_url: str = "http://127.0.0.1:8000") -> str:
    """Standalone test — fetch and render DAG."""
    result = _fetch_dag(api_url)
    return result or "No data"
