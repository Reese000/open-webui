# open-webui-foundry

> **Local customizations of [Open WebUI](https://github.com/open-webui/open-webui) (v0.10.2) to serve as the GUI for [Foundry Manager](../Foundry Manager/).**

This is NOT a general-purpose Open WebUI fork. It's a single-user, locally-hosted deployment with Foundry Manager integration baked in. Upstream Open WebUI provides the chat UI and model routing; the customizations here add tool-calling, pipeline filters, and a standalone pipeline server for Foundry Manager data.

**Status:** Working proof-of-concept. Chat streaming, model selection, and 5 Foundry tools + 3 pipeline filters are operational. Some tool-routing limitations remain (see [Known Issues](#known-issues)).

---

## What's Different from Stock Open WebUI

| Customization | Purpose |
|---|---|
| `backend/open_webui/tools/foundry/` | **5 tools** — Dashboard, Artifacts, Audit, DAG Visualizer, Manifest Viewer. Registered directly into OWUI's SQLite `tool` table. |
| `backend/open_webui/pipelines/foundry/` | **3 pipeline filters** — Monitor, DAG, Manifest. Registered as OWUI `function` table entries (filter type). |
| `pipeline_server.py` | **Standalone pipeline server** (FastAPI, port 9090) — intercepts `/dashboard`, `/dag`, `/manifest` triggers and renders Foundry Manager data before the LLM sees the message. |
| `scripts/register_foundry_pipelines.py` | DB registration script for pipeline filters (idempotent). |
| `scripts/register_foundry_tools.py` | DB registration script for tools + auto-creates admin user (idempotent). |
| `scripts/ensure_admin_user.py` | Ensures an admin user exists when `WEBUI_AUTH=false` (OWUI only auto-creates on browser signin, not API). |
| `start_owui.py` | Convenience startup script — sets env vars and runs uvicorn on `:3000`. |
| `test_pipeline_server.py` | Smoke tests for `pipeline_server.py` (10 tests: health, models, inlet/outlet routing, OWUI filter compatibility). |
| `backend/open_webui/env.py` | **2-line patch** — fixed `DATA_DIR.as_posix()` in `DATABASE_URL` for Windows path resolution. |
| `FOUNDRY_SETUP.md` | Comprehensive setup docs, architecture diagrams, tool reference. |

## Architecture

```
┌──────────────────────┐
│   Open WebUI GUI     │  http://localhost:3000
│   (Svelte frontend)  │
└──────────┬───────────┘
           │ /v1/chat/completions (SSE streaming)
           ▼
┌──────────────────────┐
│  Foundry Manager     │  http://localhost:8000
│  + OpenAI shim       │  /v1/chat/completions → Manager pipeline
│  (FastAPI backend)   │  /v1/models (virtual model)
└──────────┬───────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌──────────┐
│ Foundry │ │Traditional│
│Executor │ │  Agent   │
└─────────┘ └──────────┘
```

## Quick Start

### 1. Start Foundry Manager (backend)

```bash
cd "C:\Users\reese\Projects\Foundry Manager"
.venv\Scripts\python.exe -m uvicorn foundry_manager.api.app:app --host 127.0.0.1 --port 8000
```

### 2. Start Open WebUI (GUI)

```bash
cd "C:\Users\reese\Projects\open-webui-foundry"
python start_owui.py
```

Or manually set these env vars and run:
```
OPENAI_API_BASE_URL=http://127.0.0.1:8000/v1
OPENAI_API_KEY=foundry-manager
OLLAMA_BASE_URL=
DATA_DIR=C:\Users\reese\Projects\open-webui-foundry\data
WEBUI_AUTH=false
WEBUI_SECRET_KEY=<your-key>
```

### 3. Register Tools & Pipelines

```bash
.venv\Scripts\python.exe scripts/register_foundry_tools.py
.venv\Scripts\python.exe scripts/register_foundry_pipelines.py
```

### 4. (Optional) Start Pipeline Server

```bash
.venv\Scripts\python.exe pipeline_server.py
# Runs on :9090 — intercepts /dashboard, /dag, /manifest triggers
```

## Available Tools

| Tool | Functions | Purpose |
|---|---|---|
| `foundry_dashboard` | `get_foundry_dashboard`, `get_foundry_stats` | Real-time monitoring dashboard from Manager API |
| `foundry_artifacts` | `get_foundry_artifacts`, `get_foundry_task`, `list_foundry_tasks` | Task artifact viewer with existence verification |
| `foundry_audit` | `get_foundry_audit` | Honest audit ledger with tier-separated verification |
| `foundry_dag` | `get_foundry_dag`, `list_foundry_projects` | DAG → Mermaid diagram with verification status overlay |
| `foundry_manifest` | `get_foundry_manifest`, `list_foundry_manifests` | Manifest → structured tables + Mermaid pie charts |

## Known Issues

1. **Tool routing gap:** When chatting through the Manager shim, the Manager's LLM uses its own tool definitions (foundry executor, traditional agent) rather than Open WebUI's registered tools. The tools ARE available when using a direct OpenAI-compatible model.
2. **Auth toggle:** After toggling `WEBUI_AUTH`, clear browser site data for `127.0.0.1:3000`. If `/auth` hangs, delete `data/webui.db*` and restart.
3. **Port conflicts:** Manager on `:8000`, Open WebUI on `:3000`, Pipeline server on `:9090`. Adjust if occupied.

## Interconnectedness

This project is part of a two-repo system:

- **Foundry Manager** (`C:\Users\reese\Projects\Foundry Manager\`) — FastAPI backend, planning pipeline, executor, OpenAI-compatible shim. The tools here read its API at `http://127.0.0.1:8000`.
- **Compartmentalized Software Development** (`C:\Users\reese\Projects\Compartmentalized Software Development\`) — The "foundry harness" containing DAG YAML files, run manifests, and proof artifacts. The DAG/manifest tools read directly from this directory on disk.

## What's NOT Here

- No `.env` files, `.pem` keys, or API credentials (gitignored)
- No `data/` directory contents (runtime DB, vector DB — gitignored)
- No `node_modules/` or build artifacts
- The upstream Open WebUI codebase is intact — only the files listed above are customized

## License

Same as upstream [Open WebUI](https://github.com/open-webui/open-webui) — see upstream for license terms. This fork adds Foundry Manager integration on top.
