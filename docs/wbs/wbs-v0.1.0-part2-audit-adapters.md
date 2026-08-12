# WBS — Agent ToolTrust v0.1.0 Part 2: Audit & Integration

> **Milestones covered:** M3 (Audit Logger) + M4 (Integration Adapters + MCP Client Wrapper)
> **PRD:** [PRD.md](../design/PRD.md) | **Architecture:** [architecture-v0.1.0.md](../architecture/architecture-v0.1.0.md)

---

## Milestone 3: Audit Logger — JSONL, SQLite, Postgres

**Objective:** Append every decision (allow and deny alike) to a pluggable audit sink. Ship JSONL (zero-dep default), SQLite (local query), and Postgres (operational) in v0.1.

**PRD coverage:** F-30, F-31, F-33
**CUJs covered:** CUJ 6 (compliance — audit export)

### M3 Task Checklist

| # | Task | Feature ID | Verification |
|---|------|------------|-------------|
| 1 | **AuditEntry dataclass:** `audit/models.py` — fields matching architecture spec (session_id, timestamp, tool, action, env, data_class, agent_id, decision, criticality, reason_code, explanation, factors, policy_version, dry_run, escalation_id) | F-31 | ✅ JSON-serializable round-trip; all fields populated from Decision + NormalizedCall |
| 2 | **AuditSink interface:** `audit/sink.py` — Abstract base class with `write(entry: AuditEntry) -> None` and `query(session_id: str) -> list[AuditEntry]` | F-30 | ✅ Pluggable; new sinks implement two methods |
| 3 | **JSONL sink:** `audit/sinks/jsonl.py` — Append to `~/.tooltrust/audit.jsonl`. Rotates at configurable size or time. Fire-and-forget (never blocks decision) | F-30 | ✅ Writes valid JSONL; rotation creates new file; write failure → stderr, decision unaffected |
| 4 | **SQLite sink:** `audit/sinks/sqlite.py` — Append to local SQLite DB. Creates table on first write. Supports `query(session_id)` | F-30, F-31 | ✅ `tooltrust audit query --session <id> --sink sqlite` returns all entries |
| 5 | **Postgres sink:** `audit/sinks/postgres.py` — Append via asyncpg. Configurable connection URL. Connection pool with retry | F-33 | ✅ Async writes; connection failure → stderr + falls back to JSONL buffer |
| 6 | **AuditLogger facade:** `audit/logger.py` — `log(entry, sink)` dispatches to configured sink. Sink failure never raises — logs to stderr + continues | F-30 | ✅ All 3 sinks individually verified; configuration via env var or constructor |
| 7 | **`tooltrust audit` CLI:** `cli/audit.py` — `audit show --session <id> [--format json|csv]`, `audit query --decision deny [--since 2026-08-01]`, `audit export --session <id> --format csv` | F-30, F-31 | ✅ Export produces valid CSV/JSON; query filters by decision, date range, agent |
| 8 | **Audit integration with Engine:** Engine calls `audit_logger.log()` after every decision (stage 5 of pipeline). Audit failure never prevents decision from being returned | — | ✅ Integration test: engine.evaluate() → audit entry appears in configured sink |
| 9 | **Unit tests:** Each sink in isolation (JSONL write/read/rotate, SQLite create/query, Postgres write/query), AuditLogger dispatch, CLI commands | — | >95% coverage on audit module |

### M3 Success Metrics

| Metric | Target | Verification |
|--------|--------|-------------|
| JSONL correctness | Valid JSONL, no data loss on rotation | Integration test with 1000 writes → 1000 reads |
| SQLite query | Correct `session_id` grouping | Query 50-session dataset |
| Postgres latency | < 10 ms async write | Benchmark test |
| Sink failure resilience | Write failure → stderr, decision unaffected | Inject disk-full error test |
| CLI export | Valid CSV/JSON output, correct columns | Integration test |
| Test coverage | >95% on audit module | `pytest --cov=agent_tooltrust.audit --cov-fail-under=95` |

### M3 Exit Gate

- [x] Code review passed (every file reviewed)
- [x] Every `.py` file has module-level and function-level docstrings
- [x] Test coverage >95% (`pytest --cov=agent-tooltrust --cov-fail-under=95`)
- [x] Ruff clean (`ruff check .` — 0 errors)
- [x] Mypy strict clean (`mypy --strict` — 0 errors)
- [x] JSONL, SQLite, Postgres sinks all verified in integration tests
- [x] `tooltrust audit show --session <id>` works for all 3 sinks
- [x] `tooltrust audit export --format csv` produces valid CSV
- [x] Sink failure does not crash the engine (audit failure test passes)
- [x] Policy version recorded in every audit entry

**Dependency:** M1 (Core Engine), M2 (Policy Manager) — requires `Decision`, `NormalizedCall`
**Produces for later milestones:** `AuditLogger`, `AuditSink` interface, CLI audit commands

---

## Milestone 4: Integration Adapters — 6 Frameworks + MCP Wrapper

**Objective:** Ship adapter modules for all 6 target frameworks (raw Python, MCP client, LangGraph, PydanticAI, OpenAI Agents SDK, CrewAI). Every adapter intercepts tool calls before side effects, returns denies as native framework errors, and emits audit entries.

**PRD coverage:** F-40, F-41, F-42
**CUJs covered:** CUJ 2 (per-framework integration)

### M4 Task Checklist

| # | Task | Feature ID | Verification |
|---|------|------------|-------------|
| 1 | **Adapter base class:** `adapters/base.py` — `BaseAdapter` with `intercept(tool_call) → Decision`, `wrap_tool(tool_fn) → wrapped_fn`. Framework-specific adapters extend this | F-40 | Common interface across all adapters |
| 2 | **Raw Python adapter:** `adapters/raw.py` — `@engine.guard(tool="...", action="...")` decorator + `with engine.session():` context manager. Raises `ToolTrustDecisionError` on deny | F-41 | Decorator intercepts; context manager tags session_id; deny → ToolTrustDecisionError |
| 3 | **MCP client wrapper:** `adapters/mcp.py` — `ToolTrustMCPWrapper(mcp_client, engine)`. Proxies `tools/call` through engine.evaluate(). Deny → `isError: true` with reason as content | F-41, F-42 | MCP tool call intercepted; deny returned as MCP error message the model can see |
| 4 | **LangGraph adapter:** `adapters/langgraph.py` — `ToolTrustToolNode(tools, engine)`. Subclasses LangGraph's ToolNode. Intercepts via `_run_one()` override. Deny → `ToolMessage(content="[ToolTrust denied] reason")` | F-41 | Denied tool returns ToolMessage; graph continues without crash |
| 5 | **PydanticAI adapter:** `adapters/pydantic.py` — `@tooltrust_guard(engine)` decorator compatible with `@agent.tool`. Deny → `ModelRetry` or tool-error return | F-41 | Decorator works on PydanticAI tools; deny triggers retry or error |
| 6 | **OpenAI Agents SDK adapter:** `adapters/openai.py` — `tooltrust_guardrail(engine)` returning `@tool_input_guardrail`. Deny → `ToolGuardrailFunctionOutput.deny(reason=...)` | F-41 | Native OpenAI guardrail integration; deny returns framework-native denial |
| 7 | **CrewAI adapter:** `adapters/crewai.py` — `wrap_tool(tool, engine)`. Wraps `_run()` method. Deny → error string in tool output | F-41 | CrewAI tool wrapped; deny returns error string agent can handle |
| 8 | **Per-adapter integration tests:** Each adapter tested in its native framework with a real (or mocked) agent loop. Decision flows; only allowed calls execute; deny surfaced as framework-native error | — | 6 adapter integration tests; each passes the 4-decision demo scenario |
| 9 | **Cross-adapter audit test:** All 6 adapters emit identical audit entries for the same tool call | — | Compare audit entries across adapters → identical except adapter_name field |

### M4 Success Metrics

| Metric | Target | Verification |
|--------|--------|-------------|
| Framework coverage | 6/6 adapters working | Per-framework integration test |
| Deny handling | 6/6 adapters surface deny as framework-native result, not protocol crash | Adapter-specific error handling test |
| Audit uniformity | Same call → same audit entry across all adapters | Cross-adapter comparison test |
| Fail-closed on adapter errors | Any adapter exception → deny + logged | Error injection test per adapter |
| Test coverage | >95% on adapters module | `pytest --cov=agent_tooltrust.adapters --cov-fail-under=95` |

### M4 Exit Gate

- [ ] Code review passed (every file reviewed)
- [ ] Every `.py` file has module-level and function-level docstrings
- [ ] Test coverage >95% (`pytest --cov=agent_tooltrust --cov-fail-under=95`)
- [ ] Ruff clean (`ruff check .` — 0 errors)
- [ ] Mypy strict clean (`mypy --strict` — 0 errors)
- [ ] All 6 adapters pass integration test (real framework, demo scenario)
- [ ] MCP client wrapper correctly proxies `tools/call` with decision evaluation
- [ ] All adapters emit audit entries on every decision (allow and deny)
- [ ] All adapters fail closed on internal errors

**Dependency:** M1 (Core Engine), M3 (Audit Logger)
**Produces for later milestones:** Adapter modules consumed by field tests (M7), demo agent (M8)