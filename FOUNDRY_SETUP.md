# FOUNDRY_SETUP.md — Open WebUI as Foundry GUI

> **Phase 2 Handoff** · Generated 2026-07-21 · Open WebUI v0.10.2 + Foundry Manager v0.2.0

## Architecture

```
┌──────────────────────┐
│   Open WebUI GUI     │  http://localhost:3000
│   (Svelte frontend)  │
│   forked at v0.10.2  │
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

Verify: `curl http://127.0.0.1:8000/api/health` → `{"status":"ok"}`

### 2. Start Open WebUI (GUI)

```bash
cd "C:\Users\reese\Projects\open-webui-foundry"

# Set environment variables
set OPENAI_API_BASE_URL=http://127.0.0.1:8000/v1
set OPENAI_API_KEY=foundry-manager
set OLLAMA_BASE_URL=
set DATA_DIR=C:\Users\reese\Projects\open-webui-foundry\data
set DATABASE_URL=sqlite:///C:\Users\reese\Projects\open-webui-foundry\data\webui.db
set WEBUI_AUTH=true
set WEBUI_SECRET_KEY=your-secret-key-here
set OAUTH_SESSION_TOKEN_ENCRYPTION_KEY=your-oauth-key-here

# Start
.venv\Scripts\open-webui.exe serve --host 127.0.0.1 --port 3000
```

Verify: `curl http://127.0.0.1:3000/api/config` → `{"status":true,...}`

### 3. First-time Setup

1. Open `http://localhost:3000` in your browser
2. Sign up with admin credentials (first user becomes admin)
3. The `foundry-manager` model should appear in the model selector
4. Start chatting — messages route through the Manager's planning pipeline

## What Works

### ✅ Chat Streaming (end-to-end verified)
- Open WebUI → `/v1/chat/completions` → Manager shim → Manager pipeline → streaming SSE response
- Both streaming and non-streaming modes work
- Content deltas arrive in real-time

### ✅ Model Selection
- `foundry-manager` model is automatically discovered from the shim's `/v1/models` endpoint
- Model appears in Open WebUI's model selector dropdown

### ✅ Foundry Pipeline Tools (registered via API)
Three tools are registered in Open WebUI:

| Tool | ID | Purpose |
|------|----|---------|
| **Foundry Dashboard** | `foundry_dashboard` | Fetches `GET /api/monitoring/dashboard` + `/api/monitoring/summary` + `/api/monitoring/tasks/active` |
| **Foundry Artifacts** | `foundry_artifacts` | Fetches `GET /api/tasks/{id}/artifacts` with existence verification |
| **Foundry Audit** | `foundry_audit` | Reads run manifests and renders the honest ledger (behavioral/partial/weak/existence tiers) |

Tools are invoked via Open WebUI's tool-calling mechanism when enabled in the chat model settings.

### ✅ Session Persistence
- Open WebUI stores chat history in SQLite (`data/webui.db`)
- Session memory persists across browser refreshes

## Known Gaps & Limitations

### ⚠️ Tool Routing Gap
**Issue:** Open WebUI's tool-calling requires the LLM to generate tool_call responses. When routing through the Manager shim, the Manager's GLM 5.2 model uses its own tool definitions (foundry executor, traditional agent) rather than Open WebUI's registered tools. This means:
- The Open WebUI tools (`foundry_dashboard`, `foundry_artifacts`, `foundry_audit`) are registered but NOT automatically invoked during Manager-routed chat
- They ARE available when using Open WebUI with a direct OpenAI-compatible model (not through the Manager)

**Workaround:** Users can manually call the tools via the Open WebUI UI's tool panel, or use the Foundry Manager's REST API directly.

**Future fix:** Extend the shim to pass Open WebUI's tool definitions through to the Manager, or create a separate Open WebUI model endpoint that bypasses the Manager and calls tools directly.

### ⚠️ No DAG/Manifest Visual Panel
**Issue:** The Open WebUI plugin API does not support rendering custom HTML panels (like a DAG visualization) inside the chat window. The functions can return formatted markdown text, but not interactive visualizations.

**Assessment:** This is a §6.3 gap — the plugin API genuinely cannot render DAG/manifest panels. Documented and stopped here rather than forking internals.

### ⚠️ Old UI Not Deleted
Per §5 Phase 2, the old `foundry_manager/static/index.html` (~1000 lines vanilla JS) is NOT deleted. The retirement decision is left to the user once parity is verified.

### ⚠️ Port Conflicts
The Manager runs on port 8000 and Open WebUI on port 3000. If either port is occupied, adjust the `--port` flag and update the `OPENAI_API_BASE_URL` accordingly.

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| OpenAI shim | `Foundry Manager/foundry_manager/api/openai_compat.py` | `/v1/chat/completions` endpoint |
| Shim tests | `Foundry Manager/tests/api/test_openai_compat.py` | 10 tests for the shim |
| Dashboard tool | `open-webui-foundry/backend/open_webui/tools/foundry/foundry_dashboard.py` | Monitoring dashboard |
| Artifacts tool | `open-webui-foundry/backend/open_webui/tools/foundry/foundry_artifacts.py` | Task artifact viewer |
| Audit tool | `open-webui-foundry/backend/open_webui/tools/foundry/foundry_audit.py` | Honest audit ledger |

## Environment Variables

### Foundry Manager
| Variable | Required | Purpose |
|----------|----------|---------|
| `GLM_ADVISOR_API_KEY` | Preferred | GLM 5.2 API key |
| `OPENROUTER_API_KEY` | If no GLM key | General OpenRouter account |

### Open WebUI
| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_BASE_URL` | Yes | `http://127.0.0.1:8000/v1` |
| `OPENAI_API_KEY` | Yes | Any value (Manager handles auth) |
| `OLLAMA_BASE_URL` | Set to `""` | Disable Ollama |
| `DATA_DIR` | Yes | `C:\Users\reese\Projects\open-webui-foundry\data` |
| `DATABASE_URL` | Yes | SQLite URL for persistence |
| `WEBUI_AUTH` | Yes | `true` for auth, `false` to disable |
| `WEBUI_SECRET_KEY` | If auth=true | Session encryption key |
| `OAUTH_SESSION_TOKEN_ENCRYPTION_KEY` | Yes | OAuth encryption key |

## Dependencies

### Foundry Manager (existing)
- FastAPI, uvicorn, pydantic, httpx, pyyaml, sse-starlette, python-dotenv

### Open WebUI (vendored fork)
- Full dependency list in `open-webui-foundry/pyproject.toml`
- Installed via `uv pip install -e "."` into `.venv/`
- Includes: FastAPI, SQLAlchemy, sentence-transformers (RAG), torch, transformers

## Testing

### Shim Tests (in Foundry Manager)
```bash
cd "C:\Users\reese\Projects\Foundry Manager"
.venv\Scripts\python.exe -m pytest tests/api/test_openai_compat.py -v
# 10 tests: models endpoint, non-streaming, streaming SSE, error handling
```

### Full Test Suite
```bash
cd "C:\Users\reese\Projects\Foundry Manager"
.venv\Scripts\python.exe -m pytest tests/ -v
# 230 tests passing (220 existing + 10 shim)
```

## Git History

### Foundry Manager
```
5b3390e feat: add OpenAI-compatible /v1/chat/completions shim for Open WebUI integration
```

### Open WebUI Fork
```
ecd48e2f7 0.10.2 (upstream clone, not yet committed with [foundry] patches)
```
Tools are registered via API, not yet committed to the fork. Commit pending.

## Next Steps (Phase 3+)

1. **Tool routing fix**: Pass Open WebUI tools through the shim to the Manager, or create a direct-model endpoint
2. **DAG visualization**: Evaluate if Open WebUI's Pipe system can render custom panels (likely requires frontend changes — §6.3 boundary)
3. **Frontend customization**: If deeper integration needed, fork Open WebUI's Svelte frontend per §6
4. **Pipeline panels**: Consider Open WebUI's Pipeline system for intercepting/transforming chat (alternative to tools)
5. **Old UI retirement**: Delete `foundry_manager/static/index.html` once parity is confirmed by user
