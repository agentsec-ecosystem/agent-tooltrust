[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code of Conduct](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)
[![OpenSSF Best Practices](https://img.shields.io/badge/OpenSSF-Silver-informational)](https://www.bestpractices.dev)

# Agent ToolTrust

**Contextual risk and permission engine for tool-using AI agents. Allow, audit, escalate, or deny — with explainable, deterministic, auditable policy.**

> [!NOTE]
> **Status:** Design complete (PRD, architecture, WBS). Implementation starting.
> **Repo:** Private → public at v0.1.0 ship.
> **Package:** `agent-tooltrust` (PyPI at v0.1.0)

---

## Why

Giving an agent a tool is easy. Defining when it should be allowed to use it, in which environment, on what data, and under what approval model is the real problem.

Most teams manage agent tool permissions with flat allow-lists: this tool is allowed, that tool is denied. But the same tool is harmless in staging and dangerous in production. A read query over public docs is not equivalent to a query over customer-PII. **Flat allow-lists are a reachability control, not an authorization decision.** Agent ToolTrust replaces them with a contextual, deterministic, auditable risk engine.

**Research backing:** <18% of MCP server deployments scope tool permissions. ~80% of orgs report agent actions beyond intended scope. OWASP Agentic AI Top 10 classifies tool misuse as a first-class risk. ToolTrust implements the Policy Decision Point (PDP) pattern converged on by Permit0, Microsoft AGT, the OPA ecosystem, and OWASP guidance.

---

## What It Is

### The Decision Pipeline

```
 Tool Call → NORMALIZE → SCORE → DECIDE → EXPLAIN → AUDIT
```

Agent ToolTrust scores every tool invocation across five risk dimensions and returns one of four decisions:

| Decision | Meaning | When |
|----------|---------|------|
| **Allow** | Execute normally | Low risk (read-only in staging, public data) |
| **Audit** | Allow + enhanced logging | Elevated risk (read on sensitive data, write in staging) |
| **Escalate** | Human approval required | High risk (write in production, sensitive data mutation) |
| **Deny** | Blocked with reason | Critical risk (delete in production, PII access, destructive ops) |

### Risk Dimensions

| Dimension | Examples | Default weight |
|-----------|----------|---------------|
| Tool category | fs, shell, http, db, git, email, cloud, secrets, iam, payment | 1.0 (domain-dependent) |
| Action class | read (weight 0), write (3), delete (10), grant (10) | 1.0 |
| Environment | staging (0.1), production (0.8), pre-prod (0.6) | 1.0 (org-configurable) |
| Data sensitivity | public (0.0), internal (0.3), restricted (0.7), customer-PII (1.0) | 1.0 (org-configurable) |
| Agent class | ci-bot, support-bot, admin-bot, untrusted | 1.0 (configurable) |

### Starter Action Taxonomy (13 domains, 60+ verbs)

| Domain | Verbs | Baseline risk |
|--------|-------|---------------|
| `fs` (filesystem) | read, write, delete, list, move | low→high |
| `shell` | exec, pipe | high |
| `http` | get, post, put, delete, patch | low→med |
| `db` (database) | query, execute, migrate, drop | low→critical |
| `git` (version control) | status, diff, log, commit, push, force_push | low→critical |
| `email` | read, send, delete, search | low→high |
| `cloud` (infra) | list, describe, create, update, delete, scale | low→critical |
| `secrets` | read, write, rotate, revoke | critical |
| `iam` (identity) | read_role, assign_role, revoke_role, create_key | high→critical |
| `payment` | read, refund, transfer, charge | med→critical |
| `approval` | read, approve, deny, delegate | med→critical |
| `search` | query, index, delete_index | low→med |
| `notify` | send_slack, send_teams, send_webhook, page | low→high |

### Policy Posture Presets (never a blank slate)

```bash
tooltrust init --posture balanced  # Recommended default
tooltrust init --posture strict    # Prod fleets, compliance
tooltrust init --posture permissive # Local dev, sandboxes
```

### Delivery Modes

| Mode | How | Best for |
|------|-----|----------|
| **Python library** | `pip install agent-tooltrust`; `engine.evaluate(...)` in-process | Zero infra, 15-line integration |
| **MCP client wrapper** | Proxies `tools/call` through the engine | Agents using MCP tool servers |
| **MCP server** | ToolTrust exposes `evaluate` + `explain` as MCP tools | Any MCP agent queries authorization |
| **Framework adapters** | Decorators/guards for LangGraph, PydanticAI, OpenAI Agents SDK, CrewAI | Framework-native integration |

---

## Quickstart (v0.1.0 preview)

```bash
pip install agent-tooltrust
tooltrust init --posture balanced
```

```python
from agent_tooltrust import Engine

engine = Engine()

# Safe read in staging
result = engine.evaluate(
    tool="query_logs", action="read",
    environment="staging", data_class="internal",
    agent_id="debug-bot",
)
print(result.decision)    # "allow"
print(result.explanation) # "Read-only log query in staging: low risk. Proceeding."

# Write in production on sensitive data
result = engine.evaluate(
    tool="deploy_service", action="write",
    environment="production", data_class="restricted",
    agent_id="release-bot",
)
print(result.decision)    # "escalate"
print(result.explanation) # "Write action in production on sensitive data requires approval."

# Destructive operation — blocked
result = engine.evaluate(
    tool="drop_database", action="delete",
    environment="production", data_class="customer_pii",
    agent_id="release-bot",
)
print(result.decision)    # "deny"
print(result.explanation) # "Delete action in production on customer PII is blocked."

# Framework integration — pick your adapter
from agent_tooltrust.adapters.langgraph import ToolTrustToolNode
node = ToolTrustToolNode(tools, engine=engine)
```

---

## Framework Support

| Framework | Adapter | Integration point |
|-----------|---------|-------------------|
| **Raw Python** | `@engine.guard` decorator / `with engine.session():` | Function wrappers |
| **MCP client** | `ToolTrustMCPWrapper(mcp_client, engine)` | `tools/call` proxy |
| **LangGraph** | `ToolTrustToolNode(tools, engine)` | ToolNode pre-call interceptor |
| **PydanticAI** | `@tooltrust_guard(engine)` on `@agent.tool` | Tool decorator |
| **OpenAI Agents SDK** | `tooltrust_guardrail(engine)` → `@tool_input_guardrail` | Native guardrail API |
| **CrewAI** | `wrap_tool(tool, engine)` | Tool `_run()` wrapper |
| **SWE-bench** | `SWEBenchGuard(engine)` / `tooltrust swebench` | Coding-agent benchmark wrapper + per-task decision trace |

---

## Security Compliance Baseline

ToolTrust targets three concrete, audit-level security baselines:

| Baseline | v0.1 | v0.2 | v0.3 |
|----------|------|------|------|
| **OWASP Agentic AI Top 10** | 5/10 covered | 9/10 covered | 10/10 full |
| **OpenSSF Best Practices** | Silver | Silver+ | Gold aspirational |
| **ToolTrust Security Baseline** | Essential | Hardened | Certified |

See [SECURITY.md](SECURITY.md) for the full OWASP mapping and [SECURITY_BASELINE.md](docs/security-baseline.md) for the tier-by-tier checklist.

---

## Documentation

| Document | Content |
|----------|---------|
| [PRD](docs/design/PRD.md) | Product requirements: why, what, 11 CUJs, 92+ features |
| [Architecture](docs/architecture/architecture-v0.1.0.md) | System design, 5-stage pipeline, components, data model |
| [Design Decisions](docs/design/design-decisions.md) | 14 recorded design decisions with rationale |
| [API Reference](docs/reference/api.md) | Engine API, CLI, MCP tools, framework adapters, SWE-bench integration, error codes |
| [Release Notes v0.1.0](docs/reference/release-notes-v0.1.0.md) | What shipped in v0.1.0, quality gates, known limitations, roadmap |
| [CHANGELOG](CHANGELOG.md) | Keep a Changelog–formatted history of all releases |
| [Demo Scenario](docs/design/demo-scenario.md) | 5-call narrative: allow→audit→escalate→deny→replan |
| [Demo Agent Example](examples/demo-agent/README.md) | Runnable demo agent + adversarial variant, with captured output |
| [DB Schema](docs/architecture/db-schema-sketch.md) | Postgres + SQLite audit tables, JSONL format |
| [WBS](docs/wbs/README.md) | 6 files, 18 milestones across v0.1-v0.4 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup and guidelines |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting and security design |
| [GOVERNANCE.md](GOVERNANCE.md) | Project decision-making and releases |

---

## Milestones

| Version | Scope | Ship target |
|---------|-------|-------------|
| **v0.1.0** | Core engine, 6 adapters, MCP server, 3 posture presets, YAML+OPA/Rego dual backend, audit (JSONL/SQLite/Postgres), CLI, field tests (10 agents, 300 assertions), demo agent, OpenSSF Silver, OWASP 5/10, SWE-bench wrapper | ~Week 5-6 |
| **v0.2.0** | Session/context state, argument validation, escalation round-trip, tool scanning, tool hiding, CI policy suite, rate limits, OWASP 9/10, ToolTrust Hardened | TBD |
| **v0.3.0** | Output inspection, dispatcher safety, child delegation, tamper-evident audit, policy packs catalog, OWASP 10/10, Certified baseline | TBD |
| **v0.4.0** | Governance reports, distributed policy sync, OpenSSF Gold aspirational | TBD |

---

## Understanding Criticality — Risk Scenarios

ToolTrust scores every tool call across five dimensions. Here's how the risk
ladder works in practice:

### Risk Ladder

| Risk Level | Decision | Example |
|------------|----------|---------|
| **Low** | Allow | `query_logs` (read) in staging on public data by a CI bot |
| **Medium** | Audit | `read_secrets` (read) in production on restricted data — allowed but logged |
| **High** | Escalate | `deploy_service` (write) in production on restricted data — requires human approval |
| **Critical** | Deny | `drop_database` (delete) in production on customer PII — blocked |

### Scenario 1 — The CI Bot

A CI/CD pipeline bot queries application logs in staging for debugging:
- **Tool:** `query_logs` | **Action:** `read` | **Env:** `staging` | **Data:** `internal`
- **Result:** **ALLOW** — read-only log query in staging on internal data is low risk.
  All dimensions contribute minimally: action_class=0.00, environment=0.10, data=0.20.

### Scenario 2 — The Support Bot Reads Customer Data

A support bot needs to read customer information to resolve a ticket:
- **Tool:** `read_secrets` | **Action:** `read` | **Env:** `production` | **Data:** `restricted`
- **Result:** **AUDIT** — reading sensitive data in production triggers enhanced logging.
  Every access recorded with full context for compliance review.

### Scenario 3 — The Release Bot Deploys

A scheduled release bot pushes a deployment to production:
- **Tool:** `deploy_service` | **Action:** `write` | **Env:** `production` | **Data:** `restricted`
- **Result:** **ESCALATE** — write actions in production require explicit human approval.
  The bot cannot deploy until an on-call engineer approves the escalation.

### Scenario 4 — Destructive Operation

An agent attempts to delete a production database containing customer data:
- **Tool:** `drop_database` | **Action:** `delete` | **Env:** `production` | **Data:** `customer_pii`
- **Result:** **DENY** — destructive operation on sensitive data is blocked outright.
  The explanation suggests: "Use a read-only alternative or move to a lower-risk environment."

### Scenario 5 — Scoped Consent

A support bot is pre-approved to query logs in staging but tries to access production:
- **Session consent:** `[{tool: query_logs, env: staging, data_class: internal}]`
- **Call:** `query_logs` (read) in **production** on internal data
- **Result:** **ESCALATE** — the call falls outside the session's consent scope.
  The scope boundary prevents the agent from silently exceeding its granted permissions.

---

## Community

- [Report a bug](https://github.com/deghosal-2026/agent-tooltrust/issues/new?template=bug.md)
- [Request a feature](https://github.com/deghosal-2026/agent-tooltrust/issues/new?template=feature.md)
- [Security policy](SECURITY.md) — private vulnerability reporting

---

## License

MIT © 2026 Debashish Ghosal