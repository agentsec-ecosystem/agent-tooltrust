# Agent ToolTrust — Architecture v0.1.0

**Version:** 1.0 (Approved)
**Date:** 2026-08-08
**Status:** Draft
**Depends on:** [PRD.md](../design/PRD.md)

---

## 1. System Overview

Agent ToolTrust is a **pre-execution, deterministic policy decision point (PDP)** for tool-using AI agents. It sits between the agent's reasoning loop and tool execution, evaluating every proposed tool call against declarative policy and returning one of four outcomes: allow, audit, escalate, or deny.

```
┌──────────────┐     ┌─────────────────────────────┐     ┌──────────────┐
│              │     │       Agent ToolTrust        │     │              │
│  Agent Loop  │────►│                              │────►│  Tool Server │
│  (LLM)       │     │  Normalize → Score → Decide  │     │  (MCP/API)   │
│              │◄────│                              │◄────│              │
└──────────────┘     └──────────┬──────────────────┘     └──────────────┘
                                │
                         ┌──────▼──────┐
                         │  Audit Log  │
                         │  (JSONL/DB) │
                         └─────────────┘
```

The engine is **outside the model** — the LLM proposes, policy disposes. No amount of prompt engineering or jailbreaking can override a deny decision.

### Delivery Modes

| Mode | How | When |
|------|-----|------|
| **In-process library** | `pip install agent-tooltrust`; `engine.evaluate(...)` | Default, zero infra |
| **MCP client wrapper** | Proxy `tools/call` through the engine | Agents using MCP tool servers |
| **MCP server** | ToolTrust exposes `evaluate` / `explain` as MCP tools | Any agent can query authorization |
| **Framework adapters** | Decorators/guards for LangGraph, PydanticAI, OpenAI SDK, CrewAI | Framework-native integration |

---

## 2. Decision Pipeline

Every tool call flows through a five-stage pipeline. Each stage is deterministic, testable in isolation, and contributes to the final `Decision` object.

```
 Tool Call
    │
    ▼
┌──────────┐
│ NORMALIZE│  Canonicalize tool name, action, env, data class, agent identity
└────┬─────┘
     │
     ▼
┌──────────┐
│  SCORE    │  Apply risk dimensions → weighted score for this call
└────┬─────┘
     │
     ▼
┌──────────┐
│  DECIDE   │  Policy evaluation: allow / audit / escalate / deny
└────┬─────┘
     │
     ▼
┌──────────┐
│  EXPLAIN  │  Generate reason_code + human explanation + factor breakdown
└────┬─────┘
     │
     ▼
┌──────────┐
│   AUDIT   │  Append decision to log (JSONL / SQLite / Postgres)
└──────────┘
```

### Stage 1: Normalize

**Input:** Raw tool call from any framework (tool name, action verb, environment label, data class, agent ID, optional arguments, optional session context).

**Output:** `NormalizedCall` — canonical representation with tool_category resolved from the taxonomy, action_class mapped to a weight, all strings normalized (whitespace-collapsed, Unicode NFKC).

**Safety:** Unknown tool → `Deny("unknown_tool")`. Malformed input → `Deny("malformed_input")`. Engine crash → `Deny("engine_unavailable")`. All three are immediate pipeline exits — stages 2-5 never run.

### Stage 2: Score

**Input:** `NormalizedCall`, loaded policy (posture + org overrides).

**Output:** `RiskScore` with 5 dimension scores + aggregate.

| Dimension | Source | Weight (default) |
|-----------|--------|------------------|
| `tool_category` | Taxonomy lookup | 1.0 |
| `action_class` | Verb → weight map (read=0, write=3, delete=10, grant=10) | 1.0 |
| `environment` | Org-configured env → criticality map | 1.0 |
| `data_sensitivity` | Org-configured class → sensitivity map | 1.0 |
| `agent_class` | Agent identity → trust/role map | 1.0 |

Aggregate: `risk_score = weighted_sum(dimensions) / max_possible`, normalized to [0, 1].

**Extensibility:** Custom risk functions (`@tooltrust.risk_function`) can add or replace dimension scores. Dimensions are registered by name; new ones plug into the weighted sum without engine changes.

### Stage 3: Decide

**Input:** `RiskScore`, loaded policy rules.

**Output:** `Decision` enum + criticality.

| Risk band | Default decision |
|-----------|-----------------|
| `score < 0.25` | `allow` |
| `0.25 ≤ score < 0.50` | `audit` (allow + enhanced logging) |
| `0.50 ≤ score < 0.75` | `escalate` (human approval required) |
| `score ≥ 0.75` | `deny` |

Policy rules can override: an explicit `allow` or `deny` rule takes precedence over the band. OPA/Rego backend evaluates the same input → returns the same `Decision` enum — the dual-backend contract.

**Shadow mode:** When `dry_run=True`, the decision is computed and logged but the value returned to the caller is always `allow`. The audit log records both the shadow decision and the enforced decision.

### Stage 4: Explain

**Input:** `Decision`, `RiskScore`, `NormalizedCall`.

**Output:** `Explanation` — `reason_code` (machine-readable), `explanation` (human sentence), `factors` (list of `{dimension, value, contribution}`), `criticality` (none/low/med/high/critical).

**Template engine:** Each `reason_code` maps to a template string that substitutes dimension values. Example: `prod_write_sensitive` → "Write action ({action}) in production on sensitive data ({data_class}) requires approval. Move to staging or lower data class to proceed."

**LLM explain (optional, off by default):** When enabled, the template explanation is augmented by an LLM call that adds prose context. The LLM is non-authoritative — the decision and reason_code are already fixed. LLM failure falls back to template-only. Latency: the LLM call is explicitly not in the hot path; it runs after the decision is returned.

### Stage 5: Audit

**Input:** `Decision`, `Explanation`, `NormalizedCall`, session_id, policy_version, timestamp.

**Output:** `AuditEntry` appended to the configured sink.

**Sinks:**
- `jsonl` (default): append to `~/.tooltrust/audit.jsonl`
- `sqlite`: append to local SQLite DB
- `postgres`: append to configured Postgres table (pluggable write)

**Audit entry structure:**
```json
{
  "session_id": "sess_abc123",
  "timestamp": "2026-08-08T19:45:00Z",
  "tool": "deploy_service",
  "action": "write",
  "environment": "production",
  "data_class": "internal",
  "agent_id": "release-bot-01",
  "decision": "escalate",
  "criticality": "high",
  "reason_code": "prod_write_internal",
  "explanation": "Write action (write) in production on internal data requires approval...",
  "factors": [
    {"dimension": "environment", "value": "production", "contribution": 0.8},
    {"dimension": "action_class", "value": "write", "contribution": 0.6}
  ],
  "policy_version": "1.0.0",
  "dry_run": false,
  "escalation_id": null,
  "approver": null
}
```

---

## 3. Core Components

```
┌─────────────────────────────────────────────────────┐
│                  Agent ToolTrust                     │
├─────────────┬──────────────┬───────────┬────────────┤
│  Policy      │  Risk Engine  │  Decision  │  Audit    │
│  Manager     │  (Scorer)     │  Engine    │  Logger   │
├─────────────┼──────────────┼───────────┼────────────┤
│ - Load YAML │ - 5 dim score │ - Band map │ - JSONL   │
│ - Load Rego │ - Custom funcs│ - Overrides│ - SQLite  │
│ - Posture   │ - Weighted sum│ - Dry run  │ - Postgres│
│ - Validate  │               │ - Dual OPA │ - Rotate  │
├─────────────┴──────────────┴───────────┴────────────┤
│                  Integration Layer                    │
├─────────────────────────────────────────────────────┤
│  Library  │ MCP Wrapper │ MCP Server │ LangGraph    │
│  evaluate │ proxy call  │ evaluate() │ guard        │
│  guard()  │ intercept   │ explain()  │ PydanticAI   │
│  session  │             │            │ OpenAI       │
│           │             │            │ CrewAI       │
└─────────────────────────────────────────────────────┘
```

### 3.1 Policy Manager

**Responsibility:** Load, validate, and merge policies from multiple sources.

**Input sources (merge order, late wins):**
1. `default_policy.yaml` (shipped with ToolTrust — the posture preset)
2. `TOOLTRUST_POLICY_PATH` / `tooltrust.yaml` (org overrides)
3. Per-call context overrides (passed programmatically)

**Validation:** `tooltrust check` at startup and on policy reload. Parse errors stop the engine (fail-closed). Schema validation catches unknown keys, missing required sections, and type errors.

**OPA backend:** Same `NormalizedCall` is converted to Rego `input` document. The Rego policy must return a `decision` object with the same contract shape. OPA unreachable → immediate deny (fail-closed per backend).

### 3.2 Risk Engine

**Responsibility:** Compute a normalized risk score from the current call + loaded policy.

**Interface:** `RiskEngine.score(normalized_call: NormalizedCall, policy: Policy) -> RiskScore`

**Registered dimensions:** A registry of `RiskDimension` objects, each with a `compute(call, policy) -> float` method. Built-in dimensions: `tool_category`, `action_class`, `environment`, `data_sensitivity`, `agent_class`. Custom dimensions registered via `@tooltrust.risk_dimension("my_dim")`.

**Weighted aggregation:** Default weights are `[1.0, 1.0, 1.0, 1.0, 1.0]`. Overridable per org in `tooltrust.yaml` under `risk_weights`.

### 3.3 Decision Engine

**Responsibility:** Map `RiskScore` + policy rules → `Decision` + `criticality`.

**Resolution order:**
1. Explicit deny rules → `deny` (highest priority)
2. Explicit allow rules → `allow`
3. Explicit escalate rules → `escalate`
4. Risk band mapping → decision per band
5. Default: deny (fail-closed safety net)

**Criticality mapping:** `deny` → critical; `escalate` → high; `audit` → med; `allow` → low (or none if readable).

**OPA path:** OPA evaluates the same ordered rules. The OPA result is normalized to the same `Decision` enum — the caller doesn't know which backend returned it.

### 3.4 Audit Logger

**Responsibility:** Persist every decision (allow and deny alike) to the configured sink.

**Interface:** `AuditLogger.log(entry: AuditEntry) -> None`. Async, fire-and-forget from the main pipeline. Log failure is logged to stderr; never blocks the decision.

**Rotation:** JSONL rotates at configurable size/time. SQLite and Postgres have native retention policies.

---

## 4. Integration Architecture

### 4.1 Library (in-process)

```python
from agent_tooltrust import Engine

engine = Engine(policy_path="tooltrust.yaml")

# Direct evaluation
result = engine.evaluate(
    tool="deploy_service",
    action="write",
    environment="production",
    data_class="internal",
    agent_id="release-bot",
)
if result.decision == "escalate":
    print(f"Approval needed: {result.explanation}")

# Decorator guard
@engine.guard
def my_tool(args):
    ...

# Context manager
with engine.session("sess_123"):
    result = engine.evaluate(...)
```

### 4.2 MCP Client Wrapper

```
 Agent → MCP Client → [ToolTrust Wrapper] → MCP Server
                           │
                      evaluate() on every tools/call
                           │
                      allow? → forward to server
                      deny?  → return isError: true with reason
```

### 4.3 MCP Server (ToolTrust as MCP tool)

ToolTrust exposes itself as an MCP server with two tools:
- `tooltrust.evaluate(call: ToolCall) → Decision`
- `tooltrust.explain(call_id: str) → Explanation`

Any MCP-compatible agent can call these to query authorization.

### 4.4 Framework Adapters

| Framework | Integration Point | Denial Handling |
|-----------|-------------------|-----------------|
| **LangGraph** | ToolNode pre-call interceptor | `ToolMessage(content="[ToolTrust denied] ...")` |
| **PydanticAI** | `@engine.guard` decorator on `@agent.tool` | `ModelRetry` or tool-error return |
| **OpenAI Agents SDK** | `@tool_input_guardrail` | `ToolGuardrailFunctionOutput.deny(reason=...)` |
| **CrewAI** | Tool `_run()` wrapper | Error string in tool output |
| **Raw Python** | `@engine.guard` decorator | `ToolTrustDecisionError` exception |

---

## 5. Data Model

### 5.1 NormalizedCall

```python
@dataclass
class NormalizedCall:
    tool: str              # e.g., "deploy_service"
    tool_category: str     # resolved from taxonomy, e.g., "cloud"
    action: str            # e.g., "write"
    action_class: str      # read | write | delete | grant
    environment: str       # e.g., "production"
    data_class: str        # e.g., "internal"
    agent_id: str          # e.g., "release-bot-01"
    agent_class: str       # resolved from config, e.g., "ci-bot"
    session_id: str        # optional, e.g., "sess_abc123"
    arguments: dict        # optional, for argument-level validation
    context: dict          # optional, free-form session context
```

### 5.2 Decision

```python
@dataclass
class Decision:
    decision: Literal["allow", "audit", "escalate", "deny"]
    criticality: Literal["none", "low", "medium", "high", "critical"]
    reason_code: str
    explanation: str
    factors: list[Factor]
    escalation_id: str | None
    policy_version: str
    dry_run: bool
```

### 5.3 RiskScore

```python
@dataclass
class RiskScore:
    dimensions: dict[str, float]   # {"environment": 0.8, "action_class": 0.6, ...}
    aggregate: float               # weighted sum, normalized [0, 1]
    band: str                      # low | medium | high | critical
```

### 5.4 Policy Schema (tooltrust.yaml)

```yaml
version: "1.0.0"
posture: balanced  # strict | balanced | permissive

environments:
  staging: {criticality: 0.1}
  production: {criticality: 0.8}
  pre_prod: {criticality: 0.6}

data_classes:
  public: {sensitivity: 0.0}
  internal: {sensitivity: 0.3}
  restricted: {sensitivity: 0.7}
  customer_pii: {sensitivity: 1.0}

risk_weights:
  tool_category: 1.0
  action_class: 1.0
  environment: 1.0
  data_sensitivity: 1.0
  agent_class: 1.0

rules:
  - tool: "*"
    action: delete
    environment: production
    decision: deny
    reason: "Deletes in production are blocked"

  - tool: "query_logs"
    action: read
    environment: staging
    decision: allow

escalation:
  threshold: 0.5
  ttl_seconds: 300

audit:
  sink: jsonl
  path: ~/.tooltrust/audit.jsonl
  postgres_url: null
```

---

## 6. Security Architecture

### 6.1 Fail-Closed Guarantee

Every failure path returns `deny`. No exception, timeout, or error ever results in a silent allow.

| Failure | Behavior |
|---------|----------|
| Invalid input | `deny`, reason: `malformed_input` |
| Unknown tool | `deny`, reason: `unknown_tool` |
| Policy parse error | Engine refuses to load; all calls `deny` |
| OPA backend unreachable | OPA-path calls `deny`; native path unaffected |
| Audit sink failure | Decision stands; error logged to stderr |
| Engine process crash | Every downstream call `deny` |

### 6.2 Determinism Guarantee

Same `(NormalizedCall, Policy)` → same `Decision`, always. No randomness, no network calls in the hot path, no LLM influence on the decision. The LLM explainer is post-decision and advisory only.

### 6.3 Dual Backend Isolation

Native (Python) and OPA (Rego) backends are independent. A failure in one never affects the other. An attacker who compromises the OPA bundle cannot escalate to native-engine decisions because the caller chooses the backend per call.

---

## 7. Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Language** | Python 3.12+ | Accessibility, ecosystem reach, matches existing portfolio |
| **Package manager** | `uv` | Fast, deterministic, used across all repos |
| **Policy DSL** | YAML + Python objects | Declarative, PR-reviewable |
| **OPA integration** | `opa-python-client` or subprocess to `opa eval` | CNCF standard; subprocess for zero-dep P0 path |
| **Audit storage** | JSONL (default), SQLite (local), asyncpg (Postgres) | Progressive complexity; zero-dependency start |
| **API server** | FastAPI (MCP server, HTTP /authorize) | Async, typed, standard |
| **MCP** | `mcp` Python SDK | Native MCP protocol |
| **Testing** | pytest, hypothesis (fuzzing), ruff, mypy (strict) | Same toolchain as EvalForge/Obs |
| **CI** | GitHub Actions + OpenSSF checks | Standardized across portfolio |

---

## 8. Deployment Topology

### Single-Agent (Local)
```
[Agent Process] → [ToolTrust (in-process)] → [Tool]
                      │
                   [audit.jsonl]
```

### Multi-Agent (Gateway)
```
[Agent 1] ─┐
[Agent 2] ─┤→ [MCP Gateway] → [ToolTrust Wrapper] → [Tool Server]
[Agent N] ─┘                          │
                                  [Postgres]
```

### Fleet (v0.4+)
```
[Agent Fleet] → [AgentControlPlane] → [ToolTrust PDP Cluster]
                                           │
                                      [Postgres + OPAL sync]
```

---

## 9. Performance Budget

| Metric | Target |
|--------|--------|
| Deterministic hot path | < 0.5 ms per `evaluate()` |
| With OPA (subprocess) | < 2 ms per `evaluate()` |
| With LLM explain | + ~500 ms (non-blocking, post-decision) |
| Audit write | Fire-and-forget; never blocks decision |
| Memory | < 50 MB baseline, no persistent cache required |

---

## 10. Open Design Questions

- **Session state storage:** In-process dict vs. external store (Redis/Postgres). v0.1 is session-agnostic; v0.2 needs a decision.
- **OPA integration mode:** `opa eval` subprocess (zero-dep, simple) vs. `opa run --server` (persistent, lower latency). Subprocess for v0.1; server-mode for v0.2.
- **Policy hot-reload:** File watcher vs. explicit reload API. File watcher for v0.1 local path; API for fleet.
- **Argument serialization depth:** How deep do we inspect arguments for normalization? Surface-level in P0; deep inspection is part of F-80 (v0.2).