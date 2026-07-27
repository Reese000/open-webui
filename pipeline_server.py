"""
Foundry Manager Pipeline Server — lightweight OWUI-compatible pipeline host.
Intercepts /dashboard, /dag, /manifest triggers and returns formatted
Foundry Manager data BEFORE the LLM sees the message.

Run: .venv/Scripts/python.exe pipeline_server.py
"""
import logging, httpx
from collections import Counter
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

FM_API = "http://127.0.0.1:8000"
PORT = 9090
log = logging.getLogger("pipeline_server")

# ── Trigger phrases ─────────────────────────────────────────────────────────

TRIGGERS = {
    "dashboard": ["/dashboard","show dashboard","system status","foundry status","show status"],
    "dag": ["/dag","show dag","show me the dag","show dependency","dependency graph","dag diagram","dag visualiz"],
    "manifest": ["/manifest","show manifest","show verification","show results","verification status","verify results"],
}

# ── Message inspection ──────────────────────────────────────────────────────

def _get_user_text(messages: list) -> str | None:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            c = msg.get("content", "")
            if isinstance(c, list):
                c = " ".join(p.get("text","") for p in c if isinstance(p,dict) and p.get("type")=="text")
            return c.lower().strip()
    return None

def _detect_pipeline(user_text: str) -> str | None:
    if not user_text: return None
    for pid, phrases in TRIGGERS.items():
        for p in phrases:
            if p in user_text: return pid
    return None

def _uptime(s: float) -> str:
    if s < 60: return f"{s:.0f}s"
    if s < 3600: return f"{s/60:.1f}m"
    h = s / 3600
    return f"{h:.1f}h" if h < 24 else f"{h/24:.1f}d"

# ── FM API helpers ──────────────────────────────────────────────────────────

def _fm(path: str, **params):
    """GET from Foundry Manager API, return JSON or {}."""
    try:
        r = httpx.get(f"{FM_API}{path}", params=params, timeout=10)
        return r.json() if r.status_code == 200 else {}
    except Exception: return {}

def _health_ok() -> bool:
    try: return httpx.get(f"{FM_API}/api/health", timeout=5).status_code == 200
    except Exception: return False

# ── Renderers ───────────────────────────────────────────────────────────────

def _render_dashboard(d, s, a):
    """Render dashboard as Markdown card."""
    st = d.get("agent_status", {}).get("manager_status", "unknown")
    icon = {"idle": "🟢", "busy": "🟡"}.get(st, "🔴")
    L = ["", "---", "## 🏭 Foundry Manager Dashboard", "",
         f"**System:** {icon} `{st}` | **Uptime:** {_uptime(d.get('uptime_seconds',0))}",
         "", f"**Tasks:** 🟢 {d.get('total_active',0)} active · ✅ {d.get('total_completed',0)} completed · ❌ {d.get('total_failed',0)} failed", ""]
    for t in d.get("pending_tasks", []):
        pr = t.get("progress", {})
        ps = f" ({pr.get('verified',0)}/{pr.get('total',0)} — {pr.get('pass_rate','')})" if pr.get("total") else ""
        L.append(f"- **{t.get('description',t.get('task_id','?'))[:60]}** — `{t.get('phase','?')}` {_uptime(t.get('elapsed_seconds',0))}{ps}")
    if d.get("pending_tasks"): L.append("")
    for n, ex in d.get("executors", {}).items():
        L.append(f"- **{n}**: {len(ex.get('active_tasks',[]))} running · {len(ex.get('completed_tasks',[]))} done · {len(ex.get('failed_tasks',[]))} failed · {ex.get('total_tasks_all_time',0)} total")
    if d.get("executors"): L.append("")
    m = s.get("memory", {}); h = s.get("history", {})
    if m or h:
        L.append("### System Info")
        if m: L.append(f"- Memory: {m.get('session_count',0)} sessions · {m.get('long_term_count',0)} long-term")
        if h: L.append(f"- History: {h.get('total_entries',0)} entries")
        L.append("")
    L.append("---")
    return "\n".join(L)

def _render_dag(dag):
    """Render DAG as Mermaid diagram."""
    if not dag: return "_No DAG data._"
    units = dag.get("units", [])
    nodes = dag.get("nodes", [])
    edges = dag.get("edges", dag.get("dependencies", []))
    sm = dag.get("status_map", {})
    name = dag.get("name", dag.get("project", dag.get("project_path", "foundry-dag")))
    if units and not nodes:
        nodes = [{"id": u["id"], "deps": u.get("deps", [])} for u in units]
        if not edges: edges = [{"from": d, "to": u["id"]} for u in units for d in u.get("deps", [])]
    if not nodes: return "_No DAG nodes._"

    def sid(n): return n.replace("-","_").replace(".","_").replace(" ","_").replace("/","_")
    SS = {"behavioral":"verified","verified":"verified","failed":"failed","partial":"partial","weak":"failed"}

    L = ["", "---", f"## 📊 Foundry DAG: `{name}`", "", "```mermaid", "graph TD"]
    for n in nodes:
        ni = n if isinstance(n, str) else n.get("id", n.get("name", "?"))
        nl = ni if isinstance(n, str) else n.get("name", ni)
        s = sm.get(ni, "")
        L.append(f"    {sid(ni)}[\"{nl}\"]{':'+SS[s] if s in SS else ''}")
    for e in edges:
        if isinstance(e, dict): L.append(f"    {sid(e.get('from',e.get('source','')))} --> {sid(e.get('to',e.get('target','')))}")
        elif isinstance(e, (list, tuple)) and len(e) == 2: L.append(f"    {sid(e[0])} --> {sid(e[1])}")
    L += ["    classDef verified fill:#2d6a4f,color:#fff",
          "    classDef partial fill:#e9c46a,color:#000",
          "    classDef failed fill:#d00000,color:#fff", "```",
          f"\n**Nodes:** {len(nodes)} | **Edges:** {len(edges)}"]
    if sm: L.append(f"**Status:** {' · '.join(f'{s}:{c}' for s,c in Counter(sm.values()).most_common())}")
    L.append("---")
    return "\n".join(L)

def _render_manifest(d, s):
    """Render manifest as Markdown tables."""
    L = ["", "---", "## 📋 Foundry Manifest", "", "### Summary",
         "| Metric | Count |", "|--------|-------|"]
    ta, tc, tf = d.get("total_active",0), d.get("total_completed",0), d.get("total_failed",0)
    total = ta + tc + tf
    L += [f"| Total tasks | {total} |", f"| Active | {ta} |", f"| Completed | {tc} |", f"| Failed | {tf} |"]
    if total: L.append(f"| Pass rate | {tc/total*100:.1f}% |")
    L.append("")
    exs = d.get("executors", {})
    if exs:
        L += ["### Executor Breakdown", "| Executor | Active | Completed | Failed | Total |", "|----------|--------|-----------|--------|-------|"]
        for n, ex in exs.items():
            L.append(f"| {n} | {len(ex.get('active_tasks',[]))} | {len(ex.get('completed_tasks',[]))} | {len(ex.get('failed_tasks',[]))} | {ex.get('total_tasks_all_time',0)} |")
        L.append("")
    for t in d.get("pending_tasks", []):
        el = t.get("elapsed_seconds",0)
        L.append(f"- **{t.get('description',t.get('task_id','?'))[:40]}** — `{t.get('phase','?')}` ({el:.0f}s)" if el < 60 else f"- **{t.get('description',t.get('task_id','?'))[:40]}** — `{t.get('phase','?')}` ({el/60:.1f}m)")
    if d.get("pending_tasks"): L.append("")
    L.append("---")
    return "\n".join(L)

# ── Render dispatcher ───────────────────────────────────────────────────────

def _render(pid: str) -> str | None:
    if not _health_ok(): return f"\n\n> ⚠️ Foundry Manager not reachable at {FM_API}"
    try:
        if pid == "dashboard":
            return _render_dashboard(_fm("/api/monitoring/dashboard"), _fm("/api/monitoring/summary"), _fm("/api/monitoring/tasks/active"))
        elif pid == "dag":
            return _render_dag(_fm("/api/foundry/dag", project_path="text_query") or _fm("/api/foundry/dag"))
        elif pid == "manifest":
            return _render_manifest(_fm("/api/monitoring/dashboard"), _fm("/api/monitoring/summary"))
    except Exception as e: return f"\n\n> ⚠️ {pid} error: {e}"
    return None

# ── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(title="Foundry Manager Pipeline Server", version="1.0.0")
PIDS = ["foundry-monitor", "foundry-dag", "foundry-manifest"]

@app.get("/health")
async def health():
    return {"status": "ok" if _health_ok() else "degraded", "foundry_manager": "connected" if _health_ok() else "unreachable", "pipelines": PIDS}

@app.get("/models")
@app.get("/v1/models")
async def list_models():
    return {"object": "list", "data": [{"id": p, "object": "model", "owned_by": "foundry-manager", "pipeline": {"type": "filter", "priority": 10, "pipelines": ["*"]}} for p in PIDS]}

@app.get("/pipelines")
async def list_pipelines():
    return {"data": [{"id": p, "name": p, "type": "filter", "priority": 10} for p in PIDS]}

@app.post("/pipelines/upload")
async def upload(request: Request):
    try:
        form = await request.form(); file = form.get("file")
        if file:
            content = await file.read()
            log.info(f"Upload: {file.filename} ({len(content)} bytes)")
            return {"id": (file.filename or "uploaded").replace(".py", ""), "status": "uploaded"}
        return JSONResponse({"detail": "No file"}, 400)
    except Exception as e: return JSONResponse({"detail": str(e)}, 500)

# ── Simple pipeline inlet/outlet ────────────────────────────────────────────

@app.post("/pipeline/inlet")
async def inlet(body: dict):
    um = body.get("user_message", "")
    if isinstance(um, list): um = " ".join(p.get("text","") for p in um if isinstance(p, dict))
    ut = _get_user_text(body.get("messages", [])) or um.lower().strip()
    pid = _detect_pipeline(ut)
    if not pid: return {"pass_through": True, "body": body}
    result = _render(pid)
    if not result: return {"pass_through": True, "body": body}
    return {"pass_through": False, "action": "complete", "pipeline": pid, "messages": [{"role": "assistant", "content": result}]}

@app.post("/pipeline/outlet")
async def outlet(body: dict):
    ut = _get_user_text(body.get("messages", []))
    pid = _detect_pipeline(ut) if ut else None
    if not pid: return {"pass_through": True, "body": body}
    result = _render(pid)
    if not result: return {"pass_through": True, "body": body}
    for msg in reversed(body.get("messages", [])):
        if msg.get("role") == "assistant":
            msg["content"] = (msg.get("content", "") or "") + result; break
    return {"pass_through": False, "body": body}

# ── OWUI filter endpoints ──────────────────────────────────────────────────

@app.post("/{pipeline_id}/filter/inlet")
async def filter_inlet(pipeline_id: str, body: dict):
    payload = body.get("body", body)
    ut = _get_user_text(payload.get("messages", []))
    pid = _detect_pipeline(ut) if ut else None
    if not pid: return payload
    result = _render(pid)
    if result: payload.setdefault("messages", []).append({"role": "system", "content": f"[Foundry Pipeline: {pid}] {result}"})
    return payload

@app.post("/{pipeline_id}/filter/outlet")
async def filter_outlet(pipeline_id: str, body: dict):
    return body.get("body", body)

# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info(f"Starting Foundry Manager Pipeline Server on :{PORT}  |  FM API: {FM_API}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
