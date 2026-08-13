# Agent ToolTrust v0.1.0 Release Notes

**Released:** 2026-08-13
**Package:** `agent-tooltrust` · **Version:** 0.1.0
**License:** MIT

Agent ToolTrust is a deterministic policy decision point for tool-using AI
agents. It scores every tool invocation across five risk dimensions and returns
one of four decisions — **allow, audit, escalate, deny** — with a fully
explainable, auditable, fail-closed policy. This is the first stable release.

---

## What shipped

### The decision pipeline

```
 Tool Call → NORMALIZE → SCORE → DECIDE → EXPLAIN → AUDIT
```

Every call produces a complete `Decision` (verdict, criticality, reason code,
human explanation, risk factors, escalation id). Any stage that fails closes to
a **deny** — never an exception surfacing, and never a silent allow.

| Decision | Meaning | Example |
|----------|---------|---------|
| **Allow** | Execute normally | read of internal data in staging |
| **Audit** | Allow + enhanced logging | delete in staging by a trusted agent |
| **Escalate** | Human approval required | write/deploy in production |
| **Deny** | Blocked with reason | delete in production, PII access |

### Integration options

- **Raw Python** — `@engine.guard` decorator + session context manager.
- **Framework adapters** — LangGraph, PydanticAI, OpenAI Agents SDK, CrewAI,
  AutoGen, LlamaIndex, SmolAgents, Google ADK.
- **MCP** — an MCP server exposing `evaluate`, `explain`, and
  `session_status` (SSE transport); plus a client wrapper for MCP
  `tools/call` proxying.
- **Docker** — containerized server with health endpoint and SSE integration
  tests (`docker compose up`).

### Security posture

- **Adversarial normalization** (F-89 P0): NFKC + case-fold + confusable
  transliteration blocks Unicode / homoglyph tool-name obfuscation.
- **Fail-closed by default**: unknown tool, blank input, or malformed call →
  deny.
- **Shadow / dry-run mode** to preview policy without blocking.
- **Policy presets**: balanced / strict / permissive, YAML `tooltrust.yaml`,
  OPA/Rego backend, hot-reload.
- **Audit trail**: JSONL / SQLite / Postgres sinks with a tamper-evident hash
  chain and `tooltrust audit` CLI.
- **Governance**: OWASP Agentic Top 10 mapping (5/10 covered in v0.1),
  security baseline, arg validators (path-traversal, URL), output inspector
  (secrets / PII / injection), and tool scanning.

### Field validation

- **83-agent roster** across 10 agent frameworks.
- **Decision matrix**: 2,490 assertions, Plan A 83/83 (100% green), plus 100
  adversarial assertions.
- **Model replan round-trip**: deny → different tool → allow, with a CI-safe
  deterministic (scripted) mode (8/8) and an optional live LLM mode.
- **SWE-bench integration** (`tooltrust swebench`) replays coding-agent
  benchmarks with per-task violation traces.

### CLI

```bash
tooltrust init --posture balanced
tooltrust evaluate ...        # one-shot decision
tooltrust explain ...         # human-readable reasoning
tooltrust check FILE          # policy check
tooltrust diff A.yaml B.yaml  # policy diff
tooltrust scan TARGET         # tool scanning
tooltrust audit               # audit trail
tooltrust report              # governance reports
tooltrust test                # test runner
tooltrust field-test          # field matrix + replan sweep
tooltrust swebench            # SWE-bench benchmark
```

See the [CLI reference](api.md) for full usage.

---

## Demo

A runnable [demo agent](../demo-agent/README.md) shows the full decision
spectrum in one session — allow → audit → escalate → deny → replan — plus an
adversarial variant that correctly denies prompt injection and Unicode
obfuscation. Run:

```bash
python examples/demo-agent/demo.py
python examples/demo-agent/demo_adversarial.py
```

---

## Quality gates (v0.1.0)

| Gate | Result |
|------|--------|
| Unit + integration tests | 564 passing |
| Field test matrix | 2,490 / 2,490 passing (100%) |
| Replan round-trip | 8/8 (scripted) |
| Ruff | 0 errors |
| Mypy (--strict) | 0 errors |
| Test coverage baseline | 85% (raised in v0.2) |

---

## Known limitations

- **OWASP Agentic Top 10**: 5/10 risks covered in v0.1.0; remaining 5 (arg
  validation, rate limiting, output inspection depth, child delegation,
  tool hiding) target v0.2+.
- **OpenSSF Silver / Sigstore / PyPI publish** are staged for this release
  gate and not yet live.
- **Live replan** field sweep needs a local LLM endpoint (omlx); the
  scripted (CI-safe) path is the default.

---

## What's coming in v0.2.0

- Remaining OWASP coverage (9/10) and ToolTrust **Hardened** baseline.
- Session/context state, escalation round-trip, tool hiding/hardening.
- Distributed policy sync and OpenSSF Silver / Gold aspiration.

---

## Links

- [CHANGELOG](../../CHANGELOG.md)
- [API Reference](api.md)
- [Architecture](../../architecture/architecture-v0.1.0.md)
- [Demo Agent](../demo-agent/README.md)
- [PRD](../../design/PRD.md)
- [WBS](../../wbs/README.md)
