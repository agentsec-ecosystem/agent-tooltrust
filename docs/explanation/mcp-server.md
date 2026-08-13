# ToolTrust MCP Server

The ToolTrust MCP server exposes the decision engine as MCP tools so any
MCP-compatible agent can query authorization through its own tool stack.

## Quickstart

```bash
tooltrust serve --port 8000 --posture balanced
```

The server starts an SSE endpoint that agents connect to, plus a read-only
HTTP audit dashboard at `/audit`.

## Configuration

| Env / Flag | Default | Purpose |
|-----------|---------|---------|
| `TOOLTRUST_POLICY_PATH` | (none) | Path to `tooltrust.yaml` |
| `--policy-path` | (none) | Overrides env var |
| `--posture` | `balanced` | `balanced`, `strict`, or `permissive` |
| `--port` | `8000` | SSE + HTTP port |
| `--host` | `127.0.0.1` | Bind address |

## MCP Tools

### `tooltrust.evaluate`

Evaluate a tool call through the full decision pipeline. Returns the Decision
as JSON with risk factors, criticality, reason code, and explanation.

**Input:**
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

**Output:**
```json
{
  "decision": "allow",
  "criticality": "low",
  "reason_code": "low_risk_allow",
  "explanation": "Read-only log query in staging: low risk. Proceeding.",
  "factors": [{"dimension": "action_class", "value": "read", "contribution": 0.0}],
  "policy_version": "0.1.0",
  "call_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_risk_score": 0.15
}
```

### `tooltrust.explain`

Get an explanation for a tool call decision. Accepts either the same input as
evaluate (runs the engine) or a `call_id` to look up a prior decision.

**Input (evaluate mode):**
```json
{
  "tool_name": "deploy_service",
  "action": "write",
  "environment": "production",
  "data_class": "restricted",
  "agent_id": "release-bot"
}
```

**Input (lookup mode):**
```json
{
  "call_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### `tooltrust.session_status`

Query the status of an active session: cumulative risk score, call count,
budgets, consent scopes, and recent decision history.

**Input:**
```json
{
  "session_id": "sess_abc123"
}
```

**Output:**
```json
{
  "session_id": "sess_abc123",
  "risk_score": 2.35,
  "tool_call_count": 12,
  "token_budget": null,
  "call_budget": null,
  "consent_scopes": [],
  "decision_history": [
    {"call_id": "...", "risk_increment": 0.25, "timestamp": 1234567890.0}
  ]
}
```

## /audit HTTP Endpoint

Read-only audit dashboard served alongside the MCP SSE transport.

| Endpoint | Description |
|----------|-------------|
| `GET /audit` | Last 100 audit entries (all sessions) |
| `GET /audit?session=<id>` | All entries for a session |
| `GET /audit?decision=deny` | Filter by decision type |
| `GET /audit/health` | Server status, uptime, active sessions |

## Session State

The server tracks per-session state in memory:

- **Cumulative risk score** — accumulates across calls in a session
- **Call budgets** — deny when `call_budget` ceiling is reached
- **Consent scopes** — escalate when calls go outside pre-approved scopes

Budgets and consent scopes are set on the first call with `session_id` by
passing `--tooltrust-budgets` or `--tooltrust-consent` in tool arguments.

## Framework Integration

```python
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.mcp_tools import register_tools
from agent_tooltrust.server.audit_routes import register_audit_routes
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore
from agent_tooltrust.audit.logger import AuditLogger
from fastmcp import FastMCP

engine = Engine(default_policy("balanced"))
core = ServerCore(engine=engine, session_store=SessionStore(), audit_logger=AuditLogger())

mcp = FastMCP("my-agent")
register_tools(mcp, core)
register_audit_routes(mcp, core)
mcp.run(transport="sse", port=8000)
```

## Security

- The server never crashes on a bad tool call — all errors return deny Decisions
- Audit entries are written for every decision (allow and deny alike)
- Policy is validated on startup; server refuses to start with invalid policy
- Session state is in-memory only — restarting the server clears all sessions