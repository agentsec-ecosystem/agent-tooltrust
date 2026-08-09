# API Reference — Agent ToolTrust v0.1.0

**Version:** 0.1.0 (draft)
**Date:** 2026-08-08

## Core API

### `Engine`

```python
from agent_tooltrust import Engine

engine = Engine(
    policy_path: str | None = None,      # path to tooltrust.yaml
    posture: str = "balanced",           # strict | balanced | permissive
    audit_sink: str = "jsonl",           # jsonl | sqlite | postgres
    audit_path: str | None = None,       # sink-specific path
    dry_run: bool = False,               # shadow mode
    enable_opa: bool = False,            # enable OPA/Rego backend
    enable_llm_explain: bool = False,    # enable LLM explanations
)
```

### `Engine.evaluate()`

```python
def evaluate(
    self,
    tool: str,                          # tool name, e.g. "deploy_service"
    action: str,                        # action verb, e.g. "write"
    environment: str,                   # e.g. "production"
    data_class: str,                    # e.g. "internal"
    agent_id: str,                      # agent identity
    session_id: str | None = None,      # session context
    arguments: dict | None = None,      # tool arguments (for arg validation)
    context: dict | None = None,        # free-form session context
    dry_run: bool | None = None,        # override engine default
    backend: str = "native",            # native | opa
) -> Decision:
```

**Returns:** `Decision` object.

### `Decision`

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

### `Factor`

```python
@dataclass
class Factor:
    dimension: str        # e.g. "environment"
    value: str            # e.g. "production"
    contribution: float   # normalized contribution to score [0, 1]
```

### `Engine.explain()`

```python
def explain(
    self,
    tool: str,
    action: str,
    environment: str,
    data_class: str,
    agent_id: str,
    use_llm: bool = False,
) -> str:
```

Returns a plain-language explanation without making the full decision. Useful for dry-run exploration without producing an audit entry.

### `Engine.guard()` (decorator)

```python
@engine.guard(
    tool="my_tool",
    action="write",
    environment="production",
    data_class="internal",
)
def my_tool(args):
    ...
```

Raises `ToolTrustDecisionError` on deny/escalate. `audit` passes through with logging.

### `Engine.session()` (context manager)

```python
with engine.session("sess_abc123") as session:
    result = session.evaluate(tool="query_logs", ...)
    result2 = session.evaluate(tool="deploy", ...)
```

All decisions within the context are tagged with the session ID. Session state accumulates for future context-aware scoring (v0.2).

---

## CLI

```bash
# Evaluate a tool call
tooltrust evaluate --tool deploy_service --action write --env production --data internal --agent release-bot

# Explain a decision
tooltrust explain --tool deploy_service --action write --env production --data internal

# Initialize a new project
tooltrust init [--posture strict|balanced|permissive]

# Validate policy
tooltrust check [--path tooltrust.yaml]

# Diff current policy against defaults
tooltrust diff

# Run field tests
tooltrust field-test [--framework all|langgraph|openai|...] [--verbose]

# Query audit log
tooltrust audit show --session sess_abc123 [--format json|csv]

# Approve or deny an escalation
tooltrust approve <escalation_id>
tooltrust deny <escalation_id> [--reason "Not approved for this deployment"]
```

---

## MCP Server Tools

### `tooltrust.evaluate`

**Input:**
```json
{
  "tool": "deploy_service",
  "action": "write",
  "environment": "production",
  "data_class": "internal",
  "agent_id": "release-bot",
  "session_id": "sess_abc123",
  "arguments": {},
  "context": {}
}
```

**Output:** `Decision` object.

### `tooltrust.explain`

**Input:**
```json
{
  "tool": "deploy_service",
  "action": "write",
  "environment": "production",
  "data_class": "internal",
  "use_llm": false
}
```

**Output:** `{ "explanation": "..." }`

---

## Framework Adapters

### LangGraph

```python
from agent_tooltrust.adapters.langgraph import ToolTrustToolNode

node = ToolTrustToolNode(tools, engine=engine)
# Intercepts every tool call, returns ToolMessage on deny
```

### PydanticAI

```python
from agent_tooltrust.adapters.pydantic import tooltrust_guard

@agent.tool
@tooltrust_guard(engine)
async def my_tool(ctx, args):
    ...
```

### OpenAI Agents SDK

```python
from agent_tooltrust.adapters.openai import tooltrust_guardrail

guardrail = tooltrust_guardrail(engine)


@function_tool(input_guardrail=guardrail)
def my_tool(args):
    ...
```

### CrewAI

```python
from agent_tooltrust.adapters.crewai import wrap_tool

wrapped_tool = wrap_tool(my_crewai_tool, engine=engine)
```

### MCP Client

```python
from agent_tooltrust.adapters.mcp import ToolTrustMCPWrapper

wrapper = ToolTrustMCPWrapper(mcp_client, engine=engine)
# Every tools/call goes through evaluate() first
```

### Raw Python

```python
from agent_tooltrust import guard


@guard(engine, tool="my_tool", action="write")
def my_tool(args):
    ...
```

---

## Error Codes

| `reason_code` | Meaning |
|---------------|---------|
| `allow_low_risk` | Decision: allow. Risk below threshold. |
| `audit_sensitive_data` | Decision: audit. Sensitive data read. |
| `escalate_prod_write` | Decision: escalate. Write in production. |
| `escalate_high_risk` | Decision: escalate. Aggregate risk crossed threshold. |
| `deny_critical_op` | Decision: deny. Destructive operation matched critical rule. |
| `deny_unknown_tool` | Decision: deny. Tool not in taxonomy. |
| `deny_malformed_input` | Decision: deny. Input failed normalization. |
| `deny_engine_unavailable` | Decision: deny. Engine process crashed. |
| `deny_opa_backend_down` | Decision: deny. OPA backend unreachable. |
| `deny_policy_parse_error` | Decision: deny. Policy file is malformed. |
| `deny_evaluation_timeout` | Decision: deny. Evaluation exceeded time budget. |

---

## HTTP API (v0.2 preview)

```
POST /authorize
Content-Type: application/json

{
  "tool": "deploy_service",
  "action": "write",
  "environment": "production",
  "data_class": "internal",
  "agent_id": "release-bot",
  "session_id": "sess_abc123"
}

Response 200:
{
  "decision": "escalate",
  "criticality": "high",
  "reason_code": "prod_write_internal",
  "explanation": "Write action in production on internal data requires approval.",
  "escalation_id": "esc_a1b2c3",
  "policy_version": "1.0.0"
}
```