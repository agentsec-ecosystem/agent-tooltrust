# M5: MCP Server Design

> **Milestone:** M5 (ToolTrust MCP Server) — combined with session state (B) and audit dashboard (C)
> **WBS reference:** `docs/wbs/wbs-v0.1.0-part3-cli-mcp.md`
> **Date:** 2026-08-11
> **Status:** Approved

## Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| MCP framework | FastMCP | Decorator-based, minimal boilerplate, widely used |
| Transport | SSE (HTTP) | Agents connect over network, aligns with architecture |
| CLI entry | `tooltrust serve` | Consistent with existing CLI (init, check, diff, audit) |
| Scope | A+B+C combined | Thin proxy + temporary session state + audit endpoint |

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                 tooltrust serve                      │
│                                                      │
│  ┌─────────────────┐    ┌────────────────────────┐   │
│  │  FastMCP Server  │    │   /audit HTTP endpoint │   │
│  │  (SSE transport) │    │   (Starlette mount)    │   │
│  │                  │    │                        │   │
│  │  tooltrust.      │    │  GET  /audit           │   │
│  │    evaluate      │    │  GET  /audit?session=  │   │
│  │    explain       │    │  GET  /audit?decision= │   │
│  │    session_status│    │  GET  /audit/health    │   │
│  └───────┬──────────┘    └───────────┬────────────┘   │
│          │                           │                │
│  ┌───────┴───────────────────────────┴────────────┐   │
│  │              ServerCore                         │   │
│  │  ┌──────────┐  ┌────────────┐  ┌────────────┐ │   │
│  │  │  Engine  │  │ SessionStore│  │ AuditLogger│ │   │
│  │  └──────────┘  └────────────┘  └────────────┘ │   │
│  └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

### ServerCore

Single instance shared across FastMCP tools and /audit endpoint. Holds:
- `Engine` — the full 5-stage decision pipeline
- `SessionStore` — in-memory session state (cumulative risk, budgets, consent)
- `AuditLogger` — configured from env or tooltrust.yaml

## MCP Tools

### `tooltrust.evaluate`

Evaluates a tool call through the full decision pipeline. Returns the Decision as JSON.

**Input schema:**
```json
{
  "tool_name": "query_logs",
  "action": "read",
  "environment": "staging",
  "data_class": "internal",
  "agent_id": "debug-bot",
  "session_id": "sess_abc123",
  "arguments": {},
  "context": {}
}
```

**Output schema:**
```json
{
  "decision": "allow",
  "criticality": "low",
  "reason_code": "low_risk_allow",
  "explanation": "Read-only log query in staging: low risk. Proceeding.",
  "factors": [{"dimension": "action_class", "value": "read", "contribution": 0.0}],
  "policy_version": "0.1.0",
  "dry_run": false,
  "session_risk_score": 0.15
}
```

**Required fields:** `tool_name`, `action`, `environment`, `data_class`, `agent_id`
**Optional fields:** `session_id`, `arguments`, `context`
**On error:** returns `{"decision": "deny", "reason_code": "...", "explanation": "..."}` — never raises

### `tooltrust.explain`

Returns an explanation for a tool call decision. Accepts either the same input as evaluate (runs engine and returns explanation) or a `call_id` (looks up from audit — every call gets a UUID `call_id` stored in AuditEntry).

**Input schema:**
```json
{
  "tool_name": "deploy_service",
  "action": "write",
  "environment": "production",
  "data_class": "restricted",
  "agent_id": "release-bot"
}
```
OR
```json
{
  "call_id": "call_abc123"
}
```

**Output schema:**
```json
{
  "explanation": "Write action in production on restricted data: high risk. Escalation required.",
  "factors": [{"dimension": "action_class", "value": "write", "contribution": 0.6}],
  "reason_code": "high_risk_escalate",
  "criticality": "high"
}
```

### `tooltrust.session_status`

Queries active session state by session_id. Returns cumulative risk, budgets, consent scopes, and recent decision history.

**Input schema:**
```json
{
  "session_id": "sess_abc123"
}
```

**Output schema:**
```json
{
  "session_id": "sess_abc123",
  "risk_score": 2.35,
  "tool_call_count": 12,
  "token_budget": 100000,
  "call_budget": 100,
  "budget_remaining": {"tokens": 45000, "calls": 88},
  "consent_scopes": [{"tool": "query_logs", "env": "staging", "data_class": "internal"}],
  "decision_history": [
    {"decision": "allow", "tool": "query_logs", "risk": 0.15, "timestamp": "..."},
    {"decision": "escalate", "tool": "deploy_service", "risk": 0.8, "timestamp": "..."}
  ]
}
```

Returns error if session does not exist.

## /audit HTTP Endpoint

Mounted as Starlette routes alongside the FastMCP SSE server. Read-only.

| Route | Description |
|-------|-------------|
| `GET /audit` | Last 100 decisions (all sessions) |
| `GET /audit?session=<id>` | All entries for a session |
| `GET /audit?decision=deny` | Filter by decision type |
| `GET /audit?since=2026-08-01` | Filter by date |
| `GET /audit?agent=<id>` | Filter by agent |
| `GET /audit/health` | `{"status": "ok", "policy_version": "0.1.0", "uptime": 3600, "sessions_active": 5}` |

All responses are JSON arrays of AuditEntry objects (from `audit/models.py`).

## Session State Model

### New module: `server/session_store.py`

In-memory, thread-safe store. Keyed by `session_id`.

```python
@dataclass
class SessionState:
    session_id: str
    risk_score: float          # cumulative across all calls
    tool_call_count: int
    token_budget: int | None
    call_budget: int | None
    consent_scopes: list[dict]  # [{tool, env, data_class}, ...]
    decision_history: list      # last 50 decisions (rolling window)
    created_at: float
    last_updated: float

class SessionStore:
    def get_or_create(session_id: str, budgets: dict | None = None) -> SessionState
    def get(session_id: str) -> SessionState | None
    def update(session_id: str, decision: Decision, risk_score: float) -> SessionState
    def exceeds_budget(session_id: str) -> tuple[bool, str | None]  # (exceeded, reason)
    def within_consent(session_id: str, tool: str, env: str, data_class: str) -> bool
    def list_sessions() -> list[str]
```

### Flow per evaluate call with session tracking

1. Engine.evaluate() → Decision (unchanged pipeline)
2. SessionStore.update() — bumps call count, accumulates risk score
3. Budget check: if call count exceeds `call_budget` → override to deny("budget_exceeded")
4. Consent check: if consent scopes exist and call is outside → override to escalate("scope_boundary")
5. Attach `session_risk_score` to the response
6. AuditLogger.log() emits entry with session_id

## Server Startup Flow

```
1. Parse CLI args: --port (default 8000), --policy-path, --posture (default balanced)
2. Resolve policy path: TOOLTRUST_POLICY_PATH env → --policy-path → default posture preset
3. Load + validate policy (reraises PolicyParseError with line/column on invalid)
4. Build Engine(policy, audit_logger=sink_from_config(...))
5. Create SessionStore()
6. Create ServerCore(engine, session_store, audit_logger)
7. Create FastMCP server named "tooltrust" with SSE transport on configured port
8. Register tools: evaluate, explain, session_status
9. Mount /audit Starlette routes
10. Print startup banner with port, policy version, audit sink info
11. Start server — block until SIGTERM
```

Invalid policy → exit 1 with error message. Valid policy → server starts. Missing optional config → fall through defaults.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Engine crash during evaluate | Return `deny("engine_failure")` as valid JSON; log to stderr |
| Missing required field in input | Return `deny("invalid_input")` with explanation of which fields required |
| Invalid policy on startup | Exit 1, print error with file path + line/column |
| Audit sink failure | Log to stderr, decision unaffected (existing Engine behavior) |
| Session store OOM/error | Deny with `reason_code="session_error"`, Engine decision still returned |
| /audit query on empty audit | Return `[]` |
| Unknown session_id in session_status | Return error object with `session_id` and `"error": "not_found"` |

**Fail-closed always:** any unexpected error produces a deny Decision. Server never crashes on a single bad tool call.

## Files to Create/Modify

### New files

| File | Purpose |
|------|---------|
| `src/agent_tooltrust/server/__init__.py` | Module init, exports ServerCore, run_server |
| `src/agent_tooltrust/server/server_core.py` | ServerCore class (Engine + SessionStore + AuditLogger) |
| `src/agent_tooltrust/server/mcp_tools.py` | FastMCP tool definitions (evaluate, explain, session_status) |
| `src/agent_tooltrust/server/session_store.py` | SessionStore + SessionState classes |
| `src/agent_tooltrust/server/audit_routes.py` | /audit Starlette HTTP routes |
| `src/agent_tooltrust/server/cli.py` | `tooltrust serve` CLI command |

### Modified files

| File | Change |
|------|--------|
| `src/agent_tooltrust/cli/__init__.py` | Add `serve` subcommand |
| `src/agent_tooltrust/audit/models.py` | Add `call_id: str` field to AuditEntry (UUID on construction) |
| `src/agent_tooltrust/audit/logger.py` | Generate call_id on each `log()` call |
| `pyproject.toml` | Add `mcp[cli]>=1.0` and `fastmcp>=2.0` dependencies |
| `src/agent_tooltrust/__init__.py` | Export server module public API |

### Test files

| File | Purpose |
|------|---------|
| `tests/test_server_core.py` | ServerCore unit tests |
| `tests/test_session_store.py` | SessionStore unit tests |
| `tests/test_mcp_tools.py` | MCP tool integration tests (FastMCP test client) |
| `tests/test_audit_routes.py` | /audit endpoint tests (Starlette TestClient) |
| `tests/test_server_integration.py` | End-to-end: start server, call tools, verify audit |

## Dependencies

- `mcp[cli]>=1.0` — Python MCP SDK (FastMCP is built on this)
- `fastmcp>=2.0` — FastMCP server framework
- Server wraps existing `Engine`, `Policy`, `AuditLogger` — no new engine-level changes
- Session tracking is server-layer only (Engine is unchanged)

## Success Metrics (from WBS M5)

| Metric | Target |
|--------|--------|
| MCP tool correctness | 100% match with library `evaluate()` |
| Server startup check | Refuses invalid policy; starts with valid |
| Error resilience | Server stays up after tool error |
| Test coverage | >95% on server module |
| Session state | Correct accumulation, budget enforcement, consent boundaries |
| Audit endpoint | All query params work, health returns correct status |
| ruff/mypy | 0 errors on strict |

## Exit Gate (from WBS M5)

- [ ] Code review passed (every file reviewed)
- [ ] Every `.py` file has module-level and function-level docstrings
- [ ] Test coverage >95% (`pytest --cov=agent_tooltrust --cov-fail-under=95`)
- [ ] Ruff clean (`ruff check .` — 0 errors)
- [ ] Mypy strict clean (`mypy --strict` — 0 errors)
- [ ] MCP server starts, registers tools, responds to evaluate/explain/session_status
- [ ] MCP server refuses to start with malformed policy
- [ ] MCP server emits audit entries for all calls
- [ ] /audit endpoint serves correct data
- [ ] Session state correctly accumulates risk and enforces budgets/consent