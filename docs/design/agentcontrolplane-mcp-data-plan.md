# AgentControlPlane PDP + MCP-Data Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a ToolTrust PDP (`POST /authorize`) for fleet-manager tool-call authorization and an MCP-Data connector that authorizes per-data-source access, sharing the existing `ServerCore` decision pipeline.

**Architecture:** Two consumers over one decision core. `server/pdp_routes.py` mounts a Starlette `POST /authorize` custom route on the FastMCP server that parses a JSON tool call and delegates to `ServerCore.evaluate()`. `mcp_data.py` maps a `DataAccessRequest` onto a `mcp_data.<source_id>` tool in the `db` domain and calls the same `ServerCore.evaluate()`, keeping per-source identity in `data_class=<source_id>`. A new `tooltrust.authorize_data_source` MCP tool exposes the connector to MCP clients.

**Tech Stack:** Python 3.12+, FastMCP (Starlette custom routes), pytest, ruff, mypy --strict.

## Global Constraints

- `python` is not on PATH; run tests/lint/typecheck with `uv run`:
  `uv run pytest`, `uv run ruff check .`, `uv run mypy --strict src/`.
- Engine fails closed on unknown tools (`engine/normalize.py:120-121`): an
  unregistered `mcp_data.<id>` evaluates to a `deny` Decision. This is the
  intended default; operators register known sources via
  `mcp_data.register_data_source()`.
- `data_class=<source_id>` (fail-closed to 1.0 if the policy's `data_classes`
  map does not declare the source — see `engine/score.py:50-52`).
- Follow existing route pattern: `server/audit_routes.py` (custom_route +
  Starlette `Request`/`JSONResponse`, name nested under the `mcp` server).
- Follow existing fixture pattern in tests: `Engine(default_policy("balanced"))`
  + `SessionStore()` + `AuditLogger()` → `ServerCore` (see
  `tests/test_audit_routes.py:19-34`).
- No new runtime dependencies. No comments in code unless the file's module
  docstring requires context (docstrings allowed).
- Commit style: `feat(m5): <summary> (#112)`; do not push or open a PR unless
  asked.
- Coverage floor: audit/pdp/mcp_data modules must stay ≥ 95%; overall repo
  ≥ 85% (`fail_under` in pyproject.toml).

---

### Task 1: Taxonomy runtime registration + `mcp_data` connector

**Files:**
- Modify: `src/agent_tooltrust/taxonomy/__init__.py` (append `register_tool` function)
- Create: `src/agent_tooltrust/mcp_data.py`
- Test: `tests/test_mcp_data.py`

**Interfaces:**
- Consumes: `agent_tooltrust.taxonomy.DOMAINS` (tuple of domain names), existing `KNOWN_TOOLS` dict.
- Produces:
  - `taxonomy.register_tool(tool: str, domain: str) -> None` — registers a runtime tool→domain mapping; raises `ValueError` on blank `tool` or unknown `domain`.
  - `mcp_data.Operation = Literal["read", "write", "delete"]`
  - `mcp_data.DataAccessRequest` (frozen dataclass): `data_source_id: str`, `operation: Operation`, `agent_id: str`, `environment: str`, `session_id: str | None = None`.
  - `mcp_data.register_data_source(source_id: str, domain: str = "db") -> None` — registers `mcp_data.<source_id>` in the taxonomy via `register_tool`; raises `ValueError` on blank `source_id`.
  - `mcp_data.authorize_data_source(request: DataAccessRequest, core: Any) -> dict[str, Any]` — builds tool `mcp_data.<source_id>`, action `request.operation`, data_class `<source_id>`, calls `core.evaluate(...)`, returns the Decision dict (with `session_risk_score`, `call_id`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_data.py`:

```python
"""Tests for the MCP-Data connector (per-data-source authorization)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.mcp_data import DataAccessRequest, authorize_data_source, register_data_source
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore
from agent_tooltrust.taxonomy import domain_for, register_tool


class TestRegisterTool:
    def test_registers_tool_to_domain(self) -> None:
        register_tool("mcp_data.test_src", "db")
        assert domain_for("mcp_data.test_src") == "db"

    def test_blank_tool_raises(self) -> None:
        with pytest.raises(ValueError):
            register_tool("  ", "db")

    def test_unknown_domain_raises(self) -> None:
        with pytest.raises(ValueError):
            register_tool("mcp_data.x", "not_a_domain")


class TestRegisterDataSource:
    def test_registers_source_as_db_tool(self) -> None:
        register_data_source("snowflake_analytics")
        assert domain_for("mcp_data.snowflake_analytics") == "db"

    def test_blank_source_raises(self) -> None:
        with pytest.raises(ValueError):
            register_data_source("  ")


class TestAuthorizeDataSource:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"))
        session_store = SessionStore()
        audit_logger = AuditLogger()
        return ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)

    def _core_with_source(self, source_id: str, sensitivity: float = 0.0) -> ServerCore:
        from dataclasses import replace

        policy = replace(
            default_policy("balanced"),
            data_classes={**default_policy("balanced").data_classes, source_id: sensitivity},
        )
        return ServerCore(
            engine=Engine(policy),
            session_store=SessionStore(),
            audit_logger=AuditLogger(),
        )

    def test_registered_source_read_allowed(self) -> None:
        core = self._core_with_source("analytics_shard")
        register_data_source("analytics_shard")
        result = authorize_data_source(
            DataAccessRequest(
                data_source_id="analytics_shard",
                operation="read",
                agent_id="data-sci",
                environment="staging",
            ),
            core,
        )
        assert result["decision"] == "allow"
        assert "call_id" in result

    def test_unregistered_source_denies(self, core: ServerCore) -> None:
        result = authorize_data_source(
            DataAccessRequest(
                data_source_id="unknown_warehouse",
                operation="read",
                agent_id="data-sci",
                environment="staging",
            ),
            core,
        )
        assert result["decision"] == "deny"

    def test_write_on_registered_source_not_allow(self) -> None:
        core = self._core_with_source("customer_pii_store", sensitivity=1.0)
        register_data_source("customer_pii_store")
        result = authorize_data_source(
            DataAccessRequest(
                data_source_id="customer_pii_store",
                operation="write",
                agent_id="release-bot",
                environment="production",
            ),
            core,
        )
        assert result["decision"] in ("deny", "escalate")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mcp_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_tooltrust.mcp_data'` and
`AttributeError: module 'agent_tooltrust.taxonomy' has no attribute 'register_tool'`.

- [ ] **Step 3: Add `register_tool` to the taxonomy**

Append to `src/agent_tooltrust/taxonomy/__init__.py`:

```python
def register_tool(tool: str, domain: str) -> None:
    """Register a runtime tool→domain mapping (used by connectors).

    Dynamic tool names such as ``mcp_data.<source_id>`` are resolved by the
    normalize stage through the same ``KNOWN_TOOLS`` map as built-in tools.
    Registering an unknown tool keeps the fail-closed guarantee intact: a tool
    that is *not* registered still evaluates to ``deny``.
    """
    name = tool.strip()
    if not name:
        raise ValueError("tool must be a non-blank name")
    if domain not in DOMAINS:
        raise ValueError(f"unknown domain {domain!r}; known: {sorted(DOMAINS)}")
    KNOWN_TOOLS[name] = domain
```

- [ ] **Step 4: Create `src/agent_tooltrust/mcp_data.py`**

```python
"""MCP-Data connector — per-data-source authorization on the ToolTrust pipeline.

Maps a data-source access request onto the normal engine by modelling each
source as a ``mcp_data.<source_id>`` tool in the ``db`` domain, with the
source's own id carried as ``data_class``. Operators register known sources
with :func:`register_data_source`; unregistered sources fail closed (deny).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from agent_tooltrust.taxonomy import register_tool

Operation = Literal["read", "write", "delete"]


@dataclass(frozen=True)
class DataAccessRequest:
    """A request to access a named data source with a given operation."""

    data_source_id: str
    operation: Operation
    agent_id: str
    environment: str
    session_id: str | None = None


def register_data_source(source_id: str, domain: str = "db") -> None:
    """Register a data source so ``mcp_data.<id>`` resolves through the engine.

    Args:
        source_id: The data-source identifier (also its policy ``data_class``).
        domain: Taxonomy domain to map the tool to (default ``db``).

    Raises:
        ValueError: If ``source_id`` is blank.
    """
    name = source_id.strip()
    if not name:
        raise ValueError("source_id must be a non-blank string")
    register_tool(f"mcp_data.{name}", domain)


def authorize_data_source(request: DataAccessRequest, core: Any) -> dict[str, Any]:
    """Authorize a data-source access through the shared decision core.

    Args:
        request: The data access to authorize.
        core: A :class:`ServerCore` instance (imported lazily to avoid a
            hard dependency at import time).

    Returns:
        The Decision dict from ``ServerCore.evaluate``, including
        ``session_risk_score`` and ``call_id``.
    """
    source_id = request.data_source_id.strip()
    return core.evaluate(
        tool_name=f"mcp_data.{source_id}",
        action=request.operation,
        environment=request.environment,
        data_class=source_id,
        agent_id=request.agent_id,
        session_id=request.session_id,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp_data.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 6: Commit**

```bash
git add src/agent_tooltrust/taxonomy/__init__.py src/agent_tooltrust/mcp_data.py tests/test_mcp_data.py
git commit -m "feat(m5): mcp_data connector + taxonomy runtime registration (#112)"
```

---

### Task 2: PDP `POST /authorize` HTTP route

**Files:**
- Create: `src/agent_tooltrust/server/pdp_routes.py`
- Modify: `src/agent_tooltrust/server/__init__.py` (export `register_pdp_routes`)
- Test: `tests/test_pdp_routes.py`

**Interfaces:**
- Consumes: `ServerCore.evaluate(...)` (existing signature), Starlette `Request`/`JSONResponse`.
- Produces: `server.pdp_routes.register_pdp_routes(mcp: Any, core: Any) -> None` — mounts `POST /authorize` on the FastMCP server. Request body fields: `tool_name`, `action`, `environment`, `data_class`, `agent_id` (required, non-blank); optional `session_id`, `arguments`, `context`. Response: the Decision dict from `ServerCore.evaluate`. Errors: `400` JSON `{"error": "..."}` for invalid JSON / non-object body / missing or blank fields.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pdp_routes.py`:

```python
"""Tests for the PDP POST /authorize HTTP endpoint."""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.pdp_routes import register_pdp_routes
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


class TestPdpRoutes:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"))
        session_store = SessionStore()
        audit_logger = AuditLogger()
        return ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)

    @pytest.fixture
    def client(self, core: ServerCore) -> TestClient:
        from fastmcp import FastMCP

        mcp = FastMCP("test")
        register_pdp_routes(mcp, core)
        app = mcp.http_app()
        return TestClient(app)

    def test_authorize_returns_decision(self, client: TestClient) -> None:
        response = client.post(
            "/authorize",
            json={
                "tool_name": "query_logs",
                "action": "read",
                "environment": "staging",
                "data_class": "internal",
                "agent_id": "debug-bot",
            },
        )
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert data["decision"] in ("allow", "audit")
        assert "reason_code" in data
        assert "call_id" in data

    def test_authorize_denies_destructive(self, client: TestClient) -> None:
        response = client.post(
            "/authorize",
            json={
                "tool_name": "drop_database",
                "action": "delete",
                "environment": "production",
                "data_class": "customer_pii",
                "agent_id": "release-bot",
            },
        )
        assert response.status_code == 200
        assert response.json()["decision"] == "deny"

    def test_authorize_matches_engine(self, client: TestClient, core: ServerCore) -> None:
        body = {
            "tool_name": "deploy_service",
            "action": "write",
            "environment": "production",
            "data_class": "restricted",
            "agent_id": "release-bot",
        }
        response = client.post("/authorize", json=body)
        via_route = response.json()
        via_engine = core.evaluate(**body)
        assert via_route["decision"] == via_engine["decision"]
        assert via_route["criticality"] == via_engine["criticality"]

    def test_missing_field_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/authorize",
            json={"tool_name": "query_logs", "action": "read", "agent_id": "debug-bot"},
        )
        assert response.status_code == 400
        assert "error" in response.json()
        assert "environment" in response.json()["error"]
        assert "data_class" in response.json()["error"]

    def test_blank_field_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/authorize",
            json={
                "tool_name": "  ",
                "action": "read",
                "environment": "staging",
                "data_class": "internal",
                "agent_id": "debug-bot",
            },
        )
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_json_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/authorize",
            content=b'{"tool_name": ',
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400
        assert "error" in response.json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pdp_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_tooltrust.server.pdp_routes'`.

- [ ] **Step 3: Create `src/agent_tooltrust/server/pdp_routes.py`**

```python
"""PDP HTTP endpoint — POST /authorize for fleet managers and gateways.

Accepts a JSON tool call and returns the Decision dict from
``ServerCore.evaluate`` — the language-agnostic policy decision point
contracted for M6 (F-43) and used by the AgentControlPlane fleet manager
(#112). Malformed requests fail with a 400 JSON error.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

_REQUIRED_FIELDS = ("tool_name", "action", "environment", "data_class", "agent_id")


def register_pdp_routes(mcp: Any, core: Any) -> None:
    """Register the POST /authorize PDP route on a FastMCP server.

    Args:
        mcp: A FastMCP server instance.
        core: A :class:`ServerCore` instance.
    """

    @mcp.custom_route("/authorize", methods=["POST"])  # type: ignore[untyped-decorator]
    async def authorize(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "request body must be valid JSON"}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse({"error": "request body must be a JSON object"}, status_code=400)

        missing = [
            field
            for field in _REQUIRED_FIELDS
            if not isinstance(body.get(field), str) or not body[field].strip()
        ]
        if missing:
            return JSONResponse(
                {"error": f"missing or blank required field(s): {', '.join(sorted(missing))}"},
                status_code=400,
            )

        decision = core.evaluate(
            tool_name=body["tool_name"],
            action=body["action"],
            environment=body["environment"],
            data_class=body["data_class"],
            agent_id=body["agent_id"],
            session_id=body.get("session_id"),
            arguments=body.get("arguments"),
            context=body.get("context"),
        )
        return JSONResponse(decision)
```

- [ ] **Step 4: Export from `server/__init__.py`**

Add `<string>` import and export to `src/agent_tooltrust/server/__init__.py`:

```python
from agent_tooltrust.server.pdp_routes import register_pdp_routes
```
and add `"register_pdp_routes"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_pdp_routes.py -v`
Expected: PASS (all 6 tests).

- [ ] **Step 6: Commit**

```bash
git add src/agent_tooltrust/server/pdp_routes.py src/agent_tooltrust/server/__init__.py tests/test_pdp_routes.py
git commit -m "feat(m5): PDP POST /authorize route for fleet authorization (#112)"
```

---

### Task 3: `tooltrust.authorize_data_source` MCP tool

**Files:**
- Modify: `src/agent_tooltrust/server/mcp_tools.py`
- Modify: `src/agent_tooltrust/server/__init__.py` (no change expected — function stays exported via `register_tools`)
- Test: `tests/test_mcp_tools.py`

**Interfaces:**
- Consumes: `mcp_data.register_data_source`, `mcp_data.DataAccessRequest`, `mcp_data.authorize_data_source` (Task 1); `ServerCore` via the `core` argument already passed to `register_tools`.
- Produces: Additional entry ``"tooltrust.authorize_data_source"`` in the dict returned by `register_tools`. Tool params: `data_source_id: str`, `operation: str`, `agent_id: str`, `environment: str`, `session_id: str | None = None`. Returns the Decision dict.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mcp_tools.py`:

```python
    def test_authorize_data_source_returns_decision(self, tools: dict[str, Any], core: ServerCore) -> None:
        from agent_tooltrust.mcp_data import register_data_source

        register_data_source("analytics_shard")
        result = tools["tooltrust.authorize_data_source"](
            data_source_id="analytics_shard",
            operation="write",
            agent_id="data-sci",
            environment="staging",
        )
        assert "decision" in result
        assert "call_id" in result

    def test_authorize_data_source_unregistered_denies(
        self, tools: dict[str, Any]
    ) -> None:
        result = tools["tooltrust.authorize_data_source"](
            data_source_id="never_registered_source",
            operation="write",
            agent_id="data-sci",
            environment="staging",
        )
        assert result["decision"] == "deny"

    def test_authorize_data_source_consistency(
        self, tools: dict[str, Any], core: ServerCore
    ) -> None:
        from agent_tooltrust.mcp_data import DataAccessRequest, authorize_data_source, register_data_source

        register_data_source("analytics_shard")
        via_tool = tools["tooltrust.authorize_data_source"](
            data_source_id="analytics_shard",
            operation="read",
            agent_id="data-sci",
            environment="staging",
        )
        via_lib = authorize_data_source(
            DataAccessRequest(
                data_source_id="analytics_shard",
                operation="read",
                agent_id="data-sci",
                environment="staging",
            ),
            core,
        )
        assert via_tool["decision"] == via_lib["decision"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mcp_tools.py -v`
Expected: FAIL with `KeyError: 'tooltrust.authorize_data_source'`.

- [ ] **Step 3: Register the tool in `server/mcp_tools.py`**

Add inside the `register_tools` function, after `session_status` and before the
`return` dict:

```python
    @mcp.tool(  # type: ignore[untyped-decorator]
        name="tooltrust.authorize_data_source",
        description=(
            "Authorize access to a named data source (read/write/delete) for a "
            "given agent and environment. Returns the ToolTrust Decision with "
            "risk factors and reason code. Unregistered sources are denied."
        ),
    )
    def authorize_data_source(
        data_source_id: str,
        operation: str,
        agent_id: str,
        environment: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        from agent_tooltrust.mcp_data import DataAccessRequest, authorize_data_source as _authorize

        return _authorize(
            DataAccessRequest(
                data_source_id=data_source_id,
                operation=operation,  # type: ignore[arg-type]
                agent_id=agent_id,
                environment=environment,
                session_id=session_id,
            ),
            core,
        )
```

Update the final `return` dict to include:

```python
        "tooltrust.authorize_data_source": authorize_data_source,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp_tools.py -v`
Expected: PASS (all tests in the file, including the 3 new ones).

- [ ] **Step 5: Commit**

```bash
git add src/agent_tooltrust/server/mcp_tools.py tests/test_mcp_tools.py
git commit -m "feat(m5): tooltrust.authorize_data_source MCP tool (#112)"
```

---

### Task 4: Wire PDP into server CLI + end-to-end integration tests

**Files:**
- Modify: `src/agent_tooltrust/server/cli.py` (register `register_pdp_routes` in `_serve`)
- Modify: `tests/test_server_integration.py` (add end-to-end PDP + connector tests)
- Modify: `tests/test_audit_routes.py` (no change — pattern reference only)
- Modify: `docs/design/agentcontrolplane-mcp-data-design.md` (add a "Registering data sources" note under Testing/acceptance)

**Interfaces:**
- Consumes: `register_pdp_routes` (Task 2), `register_tools` returning `tooltrust.authorize_data_source` (Task 3).

- [ ] **Step 1: Write the failing end-to-end tests**

Append to `tests/test_server_integration.py`:

```python
    def test_pdp_authorize_end_to_end(self, core: ServerCore) -> None:
        from dataclasses import replace

        from agent_tooltrust.server.pdp_routes import register_pdp_routes
        from fastmcp import FastMCP

        mcp = FastMCP("test-pdp")
        register_pdp_routes(mcp, core)
        client = TestClient(mcp.http_app())

        response = client.post(
            "/authorize",
            json={
                "tool_name": "query_logs",
                "action": "read",
                "environment": "staging",
                "data_class": "internal",
                "agent_id": "debug-bot",
            },
        )
        assert response.status_code == 200
        assert response.json()["decision"] in ("allow", "audit")

    def test_connector_to_authorize_end_to_end(self, core: ServerCore) -> None:
        from dataclasses import replace

        from agent_tooltrust.mcp_data import (
            DataAccessRequest,
            authorize_data_source,
            register_data_source,
        )

        policy = replace(
            core.engine.policy,
            data_classes={**core.engine.policy.data_classes, "analytics_shard": 0.0},
        )
        core = ServerCore(
            engine=Engine(policy),
            session_store=SessionStore(),
            audit_logger=AuditLogger(),
        )
        register_data_source("analytics_shard")
        result = authorize_data_source(
            DataAccessRequest(
                data_source_id="analytics_shard",
                operation="read",
                agent_id="data-sci",
                environment="staging",
            ),
            core,
        )
        assert result["decision"] == "allow"
        assert "call_id" in result
```

Note: `TestClient`, `Engine`, `SessionStore`, `AuditLogger`, `ServerCore`, and
`default_policy` are already imported at the top of
`tests/test_server_integration.py`; only the new `from dataclasses import
replace` and `from agent_tooltrust.mcp_data import ...` imports are additions.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server_integration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named
'agent_tooltrust.server.pdp_routes'` (new tests) — existing tests in the file
still pass.

- [ ] **Step 3: Wire `register_pdp_routes` into the server CLI**

In `src/agent_tooltrust/server/cli.py` `_serve`, add the import and registration
alongside the existing registrars (around line 103), and a startup print line:

```python
    from agent_tooltrust.server.pdp_routes import register_pdp_routes
    ...
    register_pdp_routes(mcp, core)
    ...
    print(f"  PDP /authorize: http://{args.host}:{args.port}/authorize")
```

- [ ] **Step 4: Add "Registering data sources" note to the design doc**

In `docs/design/agentcontrolplane-mcp-data-design.md`, under the Components
contract for the MCP-Data connector, add:

```markdown
**Registering data sources:** each source's `mcp_data.<id>` tool must be
registered at startup via `mcp_data.register_data_source(source_id)` (a
taxonomy entry), or all calls to it fail closed (deny). Per-source policy
declares sensitivity through the `data_classes` map keyed on the source id.
```

- [ ] **Step 5: Run the full test suite, coverage, lint, typecheck**

Run: `uv run pytest -q`
Expected: all existing + new tests PASS (previous baseline 983 passed; new
suite ≥ 983).

Run: `uv run ruff check .`
Expected: no errors.

Run: `uv run mypy --strict src/`
Expected: no errors.

Run: `uv run pytest --cov=agent_tooltrust --cov-report=term-missing -q`
Expected: pdp_routes/mcp_data at ≥ 95%; repo-wide ≥ 85%.

- [ ] **Step 6: Commit**

```bash
git add src/agent_tooltrust/server/cli.py tests/test_server_integration.py docs/design/agentcontrolplane-mcp-data-design.md
git commit -m "feat(m5): wire PDP into server CLI + e2e tests (#112)"
```