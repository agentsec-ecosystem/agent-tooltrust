# MCP Server Implementation Plan

> **For agentic workers:** Implement tasks sequentially using TDD.

**Goal:** Ship the ToolTrust MCP server with `evaluate`, `explain`, `session_status` MCP tools, /audit HTTP endpoints, and session state tracking.

**Architecture:** FastMCP SSE server wrapping Engine + SessionStore + AuditLogger. `tooltrust serve` CLI command. All existing code (engine, policy, audit, adapters) unchanged except call_id addition.

**Tech Stack:** FastMCP 3.x, mcp 1.x, existing Engine/Policy/AuditLogger

## Global Constraints

- Test coverage >95% on new code
- ruff check --select ALL → 0 errors
- mypy --strict → 0 errors
- Every .py file: module-level + function-level docstrings with Args/Returns/Raises
- Fail-closed: any error → deny Decision, never crash the server

---

### Task 1: Add MCP dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] Add `mcp>=1.28` and `fastmcp>=3.4` to dependencies
- [ ] Run `uv sync` to install. Verify with `python -c "import fastmcp; from mcp import types; print('ok')"`

---

### Task 2: Add call_id to AuditEntry

**Files:**
- Modify: `src/agent_tooltrust/audit/models.py`
- Modify: `src/agent_tooltrust/audit/logger.py`
- Test: `tests/test_audit_models.py` (existing, add assertions)

**Interfaces:**
- Produces: `AuditEntry.call_id: str` — UUID generated on construction
- Produces: `AuditLogger.log()` returns `AuditEntry` with `call_id` populated

- [ ] Add `call_id: str` field to AuditEntry dataclass in `audit/models.py` — default `field(default_factory=lambda: str(uuid.uuid4()))`
- [ ] Add `import uuid` at top of models.py
- [ ] Verify `AuditEntry.from_decision()` propagates call_id, and `to_dict()` includes it
- [ ] In `audit/logger.py`, capture returned AuditEntry and verify call_id is set
- [ ] Run existing audit tests: `pytest tests/test_audit_*.py -v`. All should pass since call_id has a default.
- [ ] Commit

---

### Task 3: SessionStore + SessionState

**Files:**
- Create: `src/agent_tooltrust/server/session_store.py`
- Create: `tests/test_session_store.py`

**Interfaces:**
- Produces: `SessionState` dataclass with `session_id, risk_score, tool_call_count, token_budget, call_budget, consent_scopes, decision_history, created_at, last_updated`
- Produces: `SessionStore` class with `get_or_create()`, `get()`, `update()`, `exceeds_budget()`, `within_consent()`, `list_sessions()`

- [ ] Write `test_session_store.py` — tests for: create session, get session, update risk/count, budget exceeded, consent scope check, history rolling window (50), thread safety (lock)
- [ ] Run: `pytest tests/test_session_store.py -v` → all FAIL
- [ ] Implement `session_store.py` — `SessionState` dataclass, `SessionStore` with `threading.Lock`, `OrderedDict` for sessions
- [ ] Run: `pytest tests/test_session_store.py -v` → all PASS, >95% coverage
- [ ] Run: `ruff check .`, `mypy --strict src/agent_tooltrust/server/`
- [ ] Commit

---

### Task 4: ServerCore

**Files:**
- Create: `src/agent_tooltrust/server/server_core.py`
- Create: `tests/test_server_core.py`

**Interfaces:**
- Consumes: `Engine`, `SessionStore`, `AuditLogger`
- Produces: `ServerCore(engine, session_store, audit_logger)` with `.evaluate(tool_name, action, environment, data_class, agent_id, session_id=None, arguments=None, context=None) -> Decision`
- Produces: `ServerCore.explain_from_audit(call_id: str) -> dict | None`

- [ ] Write `test_server_core.py` — tests: evaluate passes through to Engine, session tracking updates state, budget exceeded → deny, consent boundary → escalate, explain_from_audit looks up by call_id, audit entry emitted
- [ ] Run: `pytest tests/test_server_core.py -v` → all FAIL
- [ ] Implement `server_core.py`:
  - Constructor: `__init__(self, engine, session_store, audit_logger)`
  - `evaluate()`: call engine.evaluate(), then `session_store.update()`, then budget/consent overrides, then `audit_logger.log()`, attach `session_risk_score` to return
  - `explain_from_audit()`: call `audit_logger.query(session_id=...)` and find by call_id
- [ ] Run: `pytest tests/test_server_core.py -v` → all PASS, >95% coverage
- [ ] Run: `ruff check .`, `mypy --strict src/agent_tooltrust/server/`
- [ ] Commit

---

### Task 5: MCP Tools (evaluate + explain + session_status)

**Files:**
- Create: `src/agent_tooltrust/server/mcp_tools.py`
- Create: `tests/test_mcp_tools.py`

**Interfaces:**
- Consumes: `ServerCore`
- Produces: `register_tools(mcp: FastMCP, core: ServerCore) -> None`

- [ ] Write `test_mcp_tools.py` — use FastMCP test client to call evaluate/explain/session_status tools, verify JSON output matches Engine, error handling returns deny not crash
- [ ] Run: `pytest tests/test_mcp_tools.py -v` → all FAIL
- [ ] Implement `mcp_tools.py`:
  ```python
  def register_tools(mcp, core):
      @mcp.tool(name="tooltrust.evaluate", description="...")
      def evaluate(tool_name, action, environment, data_class, agent_id,
                   session_id=None, arguments=None, context=None) -> dict:
          decision = core.evaluate(...)
          return decision.to_dict()

      @mcp.tool(name="tooltrust.explain", description="...")
      def explain(tool_name=None, action=None, ..., call_id=None) -> dict:
          if call_id:
              return core.explain_from_audit(call_id) or {"error": "not_found"}
          decision = core.evaluate(...)
          return {"explanation": decision.explanation, "factors": [...], ...}

      @mcp.tool(name="tooltrust.session_status", description="...")
      def session_status(session_id) -> dict:
          state = core.session_store.get(session_id)
          if not state: return {"session_id": session_id, "error": "not_found"}
          return {"session_id": ..., "risk_score": ..., ...}
  ```
- [ ] Run: `pytest tests/test_mcp_tools.py -v` → all PASS, >95% coverage
- [ ] Run: `ruff check .`, `mypy --strict`
- [ ] Commit

---

### Task 6: Audit HTTP Routes

**Files:**
- Create: `src/agent_tooltrust/server/audit_routes.py`
- Create: `tests/test_audit_routes.py`

**Interfaces:**
- Consumes: `AuditLogger` (from ServerCore)
- Produces: Starlette `Route` objects for /audit endpoint

- [ ] Write `test_audit_routes.py` — Starlette TestClient hitting GET /audit, GET /audit?session=X, GET /audit?decision=deny, GET /audit?since=..., GET /audit?agent=..., GET /audit/health
- [ ] Run: `pytest tests/test_audit_routes.py -v` → all FAIL
- [ ] Implement `audit_routes.py` — Starlette `Route` + `Router`, JSONResponse for each endpoint, health endpoint returns `status, policy_version, uptime, sessions_active`
- [ ] Run: `pytest tests/test_audit_routes.py -v` → all PASS, >95% coverage
- [ ] Run: `ruff check .`, `mypy --strict`
- [ ] Commit

---

### Task 7: CLI serve command + server __init__.py

**Files:**
- Create: `src/agent_tooltrust/server/__init__.py`
- Create: `src/agent_tooltrust/server/cli.py`
- Create: `tests/test_server_integration.py`
- Modify: `src/agent_tooltrust/cli/__init__.py`

**Interfaces:**
- Produces: `server.run_server(port, policy_path, posture) -> None` — entry point
- Produces: `cli.serve_command(args)` — CLI handler wired to `tooltrust serve`

- [ ] Write `test_server_integration.py` — start server in background thread, call MCP tools via client, verify audit entries, stop server
- [ ] Run: `pytest tests/test_server_integration.py -v` → all FAIL
- [ ] Implement `server/__init__.py`:
  ```python
  from agent_tooltrust.server.server_core import ServerCore
  from agent_tooltrust.server.session_store import SessionStore, SessionState
  from agent_tooltrust.server.mcp_tools import register_tools
  from agent_tooltrust.server.audit_routes import create_audit_routes
  ```
- [ ] Implement `server/cli.py`:
  ```python
  def serve_command(args):
      # Load policy, create Engine, SessionStore, ServerCore
      # Create FastMCP, register tools, mount audit routes
      # Run SSE server on port
  ```
- [ ] Wire into `cli/__init__.py`: add `serve` subparser, call `serve_command(args)` on dispatch
- [ ] Run: `pytest tests/test_server_integration.py -v` → all PASS
- [ ] Run: `ruff check .`, `mypy --strict`
- [ ] Test CLI: `tooltrust serve --help`, `tooltrust serve --port 9999` → starts, `Ctrl+C` stops
- [ ] Commit

---

### Task 8: Documentation

**Files:**
- Create: `docs/explanation/mcp-server.md`

- [ ] Write MCP server documentation: setup, configuration, tool reference, example client code
- [ ] Commit