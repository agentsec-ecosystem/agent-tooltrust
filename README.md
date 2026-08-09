[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code of Conduct](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)

# Agent ToolTrust

**Contextual risk and permission engine for tool-using AI agents. Allow, audit, escalate, or deny — with explainable policy.**

## Why

Giving an agent a tool is easy. Defining when it should be allowed to use it, in which environment, and under what approval level is the real problem.

Most teams manage tool permissions with flat allow-lists: this tool is allowed, that tool is denied. But the same tool is harmless in staging and dangerous in production. A read query over public docs is not equivalent to a query over sensitive incident data. Agent ToolTrust replaces flat allow-lists with contextual risk evaluation.

## What It Is

Agent ToolTrust scores every tool invocation across five dimensions:

| Dimension | Examples |
|-----------|----------|
| **Tool type** | file write, API call, database query, shell command |
| **Action class** | read, write, delete, execute |
| **Environment** | staging, production, local dev |
| **Data sensitivity** | public, internal, restricted, customer-PII |
| **Agent confidence** | high-certainty action vs. low-certainty improvisation |

Then returns one of four decisions:

| Decision | Meaning |
|----------|---------|
| **Allow** | Safe. Execute normally. |
| **Audit** | Allow but log with enhanced detail. |
| **Escalate** | Requires human approval with an explanation artifact. |
| **Deny** | Blocked with a policy explanation. |

Every decision comes with an **explanation artifact** — so engineers understand *why*, not just *what*.

## What It Is Not

| It is NOT | Instead |
|-----------|---------|
| A complete IAM product | A focused trust layer for agent tool calls |
| A replacement for auth systems | A policy engine that sits on top of existing auth |
| A guarantee of zero-risk autonomy | A guardrail that makes risk explicit and auditable |

## Quickstart

```bash
pip install agent-tooltrust
```

```python
from agent_tooltrust import RiskEngine, Decision

engine = RiskEngine()

result = engine.evaluate(
    tool="deploy_service",
    action="write",
    environment="production",
    data_class="internal",
    agent_id="release-bot-01",
)

print(result.decision)      # Decision.ESCALATE
print(result.explanation)   # "Write action in production requires approval"
```

## Documentation

| Document | Purpose |
|----------|---------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup and guidelines |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting and security design |
| [GOVERNANCE.md](GOVERNANCE.md) | Project decision-making and releases |
| [SUPPORT.md](SUPPORT.md) | Getting help |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Community standards |

## Community

- [Report a bug](https://github.com/deghosal-2026/agent-tooltrust/issues/new?template=bug.md)
- [Request a feature](https://github.com/deghosal-2026/agent-tooltrust/issues/new?template=feature.md)

## License

MIT © 2026 Debashish Ghosal