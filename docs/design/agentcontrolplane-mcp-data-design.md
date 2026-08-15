# AgentControlPlane PDP Service + MCP-Data Connector

**Version:** 1.0 (Draft for review)
**Date:** 2026-08-14
**Status:** Approved
**Issue:** [agent-tooltrust #112](https://github.com/anomalyco/agent-tooltrust/issues/112)

## Problem

Org-scale fleets of agents need a central policy decision point (PDP), and MCP
data sources need per-source authorization. ToolTrust is not wired to either.

Issue #112 asks for two things under one header:

1. A ToolTrust **PDP service** that authorizes fleet tool calls.
2. An **MCP-Data connector** that enforces per-data-source authorization.

## Scope Decisions

This design addresses both subsystems as a single spec, as agreed.

- **Control plane target:** Generic concept — ToolTrust exposes a documented
  integration contract that any fleet manager can consume. No specific
  third-party repo is vendored.
- **PDP surface:** The PDP reuses the HTTP `POST /authorize` contract planned
  for M6 issue #97 (F-43). This design defines the contract now; #97 later
  hardens and documents it as the public non-Python entry point.
- **MCP-Data meaning:** The formal MCP spec's Data-API direction. The connector
  maps per-data-source access requests to ToolTrust decisions.
- **PDP role:** The PDP is a *policy decision point*. It returns Decision JSON;
  it is not an OAuth 2.1 authorization/token server.

## Approach

**A: Mounted PDP + reference connector (chosen).**

The PDP is a route on the existing ToolTrust server (one server binary), and
the connector is a pure library module wired into the server as an MCP tool.
This satisfies both of #112's test bullets without creating a second process.

Rejected alternatives:

- **Standalone PDP app:** extra process duplicates server wiring and diverges
  from #97's surface.
- **MCP tool only (no HTTP route):** does not satisfy "PDP service authorizes
  fleet tool calls" — the fleet needs a service surface now.

## Architecture & Components

```
                 fleet manager / gateway / data MCP server
                              |   POST /authorize (JSON tool call)
                              v
                 +------------------------------+
                 |  server/pdp_routes.py        |  HTTP boundary
                 |  register_pdp_routes(mcp,..) |
                 +--------------+---------------+
                                v
                 +------------------------------+
                 |  server/server_core.py       |  shared decision core
                 |  ServerCore.evaluate()       |  (existing)
                 +--------------+---------------+
                                v
        tooltrust.authorize        mcp_data.py
        _data_source (MCP tool)    authorize_data_source(request)
        server/mcp_tools.py        mcp_data coupling
```

Three new components plus one registered MCP tool. Each has one job:

1. **`server/pdp_routes.py`** — HTTP boundary. Registers `POST /authorize` as a
   Starlette custom route on the FastMCP server (same pattern as
   `audit_routes.py`). Parses and validates the JSON tool call, delegates to
   `ServerCore.evaluate()`, returns Decision JSON. Mounted in
   `server/cli.py` alongside the other route registrars and exported from
   `server/__init__.py`.

2. **`mcp_data.py`** — pure module (no FastMCP dependency). Defines
   `DataAccessRequest` and `authorize_data_source(request, core)`.
   Maps a data-source access onto `ServerCore.evaluate()`. Reuses the
   existing policy dimensions so per-source rules work with no schema
   changes.

   **Registering data sources:** each source's `mcp_data.<id>` tool must be
   registered at startup via `mcp_data.register_data_source(source_id)` (a
   taxonomy entry), or all calls to it fail closed (deny). Per-source policy
   declares sensitivity through the `data_classes` map keyed on the source id.

3. **`server/mcp_tools.py`** — adds a `tooltrust.authorize_data_source` MCP
   tool that wires `mcp_data.authorize_data_source` to the running server.

4. **`ServerCore`** — existing shared engine + SessionStore + AuditLogger;
   unchanged.

### Component contracts

**`DataAccessRequest`** (frozen dataclass):
- `data_source_id: str`
- `operation: Literal["read", "write", "delete"]`
- `agent_id: str`
- `environment: str`
- `session_id: str | None = None`

**`authorize_data_source(request, core) -> dict`**: maps
`tool_name="mcp_data.<data_source_id>"`, `action=<operation>`,
`data_class=<data_source_id>`, `environment`, `agent_id`. Returns the same
Decision JSON shape produced by `ServerCore.evaluate()` — `decision`,
`criticality`, `reason_code`, `explanation`, `factors`, `escalation_id`,
`policy_version`, `dry_run`, `obligations`, `session_risk_score`, `call_id`.

**`POST /authorize`** request body:
```json
{
  "tool_name": "mcp_data.snowflake_analytics",
  "action": "read",
  "environment": "production",
  "data_class": "snowflake_analytics",
  "agent_id": "agent-a",
  "session_id": null
}
```
Response is the Decision JSON produced by `ServerCore.evaluate()`.

## Data Flow

1. A fleet manager, gateway, or data MCP server `POST /authorize` with a JSON
   tool call.
2. `pdp_routes` parses and validates the body, then calls
   `ServerCore.evaluate()`.
3. `ServerCore` runs the engine (risk scoring, policy, denial rules, session
   tracking, audit) and returns Decision JSON.
4. For per-data-source authorization, a gateway intercepting an MCP data
   request calls `authorize_data_source(request, core)` (directly as a library
   call or via the `tooltrust.authorize_data_source` MCP tool). The verdict is
   bound to the data source through the `mcp_data.<id>` tool name and
   `data_class=<id>` mapping.
5. Enforcement is by the caller: the PDP returns verdicts; the gateway/fleet
   denies execution on `deny` / `escalate`.

## Error Handling

- Unparsable body or missing `Content-Type: application/json` → `400` with a
  clear JSON error.
- Missing or blank `tool_name` / `action` / `environment` / `data_class` /
  `agent_id` → `400` naming the field.
- Unknown data source / tool → still evaluated through the engine, which fails
  closed (deny) per policy — consistent with in-process behavior.

## Testing

- **Unit:** `DataAccessRequest` → `evaluate` mapping (tool name, action,
  data_class derivation); malformed request rejection.
- **Route:** `POST /authorize` returns a Decision JSON consistent with the
  engine for the same call; invalid JSON → `400`; blank field → `400` naming
  it.
- **End-to-end:** boot the wiring as `server/cli.py` does, exercise
  `POST /authorize` and the `tooltrust.authorize_data_source` MCP tool; assert
  the authorization for a sensitive data source blocks a write while allowing
  a read (per policy).
- **MCP tool:** `authorize_data_source` registered and returning a decision
  consistent with `mcp_data.authorize_data_source`.

## Acceptance Criteria

- PDP service authorizes fleet tool calls (via `POST /authorize`).
- MCP-Data connector enforces per-data-source authorization.
- Integration tests pass end-to-end.

## Out of Scope

- OAuth 2.1 token issuance / discovery (MCP transport authorization) — the
  PDP returns decisions, not tokens.
- Public hardening/documentation of `POST /authorize` — deferred to M6 #97.
- Any specific third-party control-plane integration — the contract is
  generic.