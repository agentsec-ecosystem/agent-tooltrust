# WBS — Agent ToolTrust v0.1.0 Part 3: MCP Server, CLI, Explanation

> **Milestones covered:** M5 (MCP Server) + M6 (CLI + Explanation Engine)
> **PRD:** [PRD.md](../design/PRD.md) | **Architecture:** [architecture-v0.1.0.md](../architecture/architecture-v0.1.0.md)

---

## Milestone 5: ToolTrust MCP Server

**Objective:** Expose ToolTrust as an MCP server so any MCP-compatible agent can query authorization through its own tool stack. Ships three tools: `tooltrust.evaluate`, `tooltrust.explain`, and `tooltrust.session_status`, plus a `/audit` HTTP endpoint with session state tracking.

**PRD coverage:** F-11, session state (F-08 family)
**CUJs covered:** CUJ 2 (MCP integration path)
**Status:** **COMPLETE ✅** — 51 tests, FastMCP SSE server, 3 tools, /audit endpoint, session tracking, ruff clean, mypy strict.

### M5 Task Checklist

| # | Task | Feature ID | Verification | Status |
|---|------|------------|-------------|--------|
| 1 | **MCP server scaffold:** `server/mcp_server.py` — FastMCP or `mcp` SDK server. Registers three tools: `tooltrust.evaluate`, `tooltrust.explain`, `tooltrust.session_status`. Loads policy on startup | F-11 | Server starts; lists tools via MCP discovery | ✅ Implemented as `server/` package |
| 2 | **`tooltrust.evaluate` tool:** Accepts JSON `ToolCall` (tool, action, env, data_class, agent_id, session_id, arguments, context). Returns `Decision` as JSON | F-11 | MCP call returns same Decision as library `evaluate()` | ✅ 9 tests pass |
| 3 | **`tooltrust.explain` tool:** Accepts `call_id` or raw call JSON. Returns explanation string. Optional `use_llm: bool` parameter | F-11 | MCP call returns explanation matching library `explain()` | ✅ Lookup by call_id works |
| 4 | **Policy loading on startup:** Server loads `TOOLTRUST_POLICY_PATH` or defaults. Validates with `tooltrust check` equivalent. Refuses to start on invalid policy | F-11, F-67 | Server refuses start with malformed policy; logs line/column error | ✅ `tooltrust serve --policy-path` or --posture |
| 5 | **MCP server tests:** Start server, connect MCP client, call evaluate/explain/session_status tools, verify decisions match in-process engine | — | 51 test calls → 51 correct decisions; explain matches library output | ✅ test_mcp_tools.py + test_server_core.py + test_server_integration.py |
| 6 | **Server error handling:** Internal error → `isError: true` with reason. Engine crash → tool returns deny. Audit entries emitted for all calls | — | Server stays up; tools return errors not crashes | ✅ Fail-closed via Engine, budget/consent overrides |
| 7 | **MCP server documentation:** `docs/explanation/mcp-server.md` — how to configure, connect, and use the ToolTrust MCP server | — | Doc covers server start, tool discovery, example calls | ✅ docs/explanation/mcp-server.md |

### M5 Success Metrics

| Metric | Target | Verification |
|--------|--------|-------------|
| MCP tool correctness | 100% match with library `evaluate()` | 20-tool-call MCP client test |
| Server startup check | Refuses invalid policy; starts with valid | Malformed policy test |
| Error resilience | Server stays up after tool error | Error injection test |
| Test coverage | >95% on server module | `pytest --cov=agent_tooltrust.server --cov-fail-under=95` |

### M5 Exit Gate

- [x] Code review passed (every file reviewed)
- [x] Every `.py` file has module-level and function-level docstrings
- [x] Test coverage >95% (`pytest --cov=agent_tooltrust --cov-fail-under=95`)
- [x] Ruff clean (`ruff check .` — 0 errors)
- [x] Mypy strict clean (`mypy --strict` — 0 errors)
- [x] MCP server starts, registers tools, responds to evaluate/explain/session_status
- [x] MCP server refuses to start with malformed policy
- [x] MCP server emits audit entries for all calls
- [x] /audit HTTP endpoint serves data + health check
- [x] Session state tracks risk accumulation, budget enforcement, consent scopes

**Dependency:** M1 (Core Engine), M2 (Policy Manager), M3 (Audit Logger)
**Produces for later milestones:** MCP server consumed by field tests (M7)

---

## Milestone 6: CLI + Explanation Engine Polish

**Objective:** Ship the full CLI surface (`tooltrust evaluate`, `explain`, `init`, `check`, `diff`, `field-test`, `audit`) and polish the explanation engine with the actionability test (CUJ 3).

**PRD coverage:** F-23, F-51, F-52, F-74, F-85
**CUJs covered:** CUJ 3 (explainable), CUJ 8 (posture customization — init)
**Status:** **COMPLETE ✅** — 8 CLI commands, actionability tests pass, quickstart doc, 432 tests

### M6 Task Checklist

| # | Task | Feature ID | Verification |
|---|------|------------|-------------|
| 1 | **`tooltrust evaluate` CLI:** Accepts --tool, --action, --env, --data, --agent, --session, --dry-run flags. Prints Decision as formatted table or JSON | F-51 | CLI call matches library output; --format json produces valid JSON |
| 2 | **`tooltrust explain` CLI:** Accepts --tool, --action, --env, --data flags. Prints factor breakdown. `--llm` flag enables LLM prose | F-23, F-74 | Template explanation correct; --llm path adds prose; LLM failure falls back to template |
| 3 | **`tooltrust init` CLI:** `tooltrust init [--posture strict|balanced|permissive] [--path ./]`. Generates tooltrust.yaml with chosen posture | F-85, F-66 | Generated YAML validates with `tooltrust check`; balanced is default posture |
| 4 | **`tooltrust check` CLI:** Reads tooltrust.yaml, validates, exits 0 on success or non-zero with line/column on error | F-67 | Valid YAML → exit 0; malformed → exit 1 + error message with location |
| 5 | **`tooltrust diff` CLI:** Compares loaded policy to defaults. Shows kept/overridden/gaps | F-65 | Diff output is human-readable and machine-parseable |
| 6 | **`tooltrust audit` CLI:** `audit show --session <id>`, `audit query --decision deny`, `audit export --format csv` | F-51 | All subcommands work against JSONL and SQLite sinks |
| 7 | **`tooltrust field-test` CLI (scaffold):** Placeholder command that prints "field test harness" and exits 0. Full implementation in M7 | — | Command exists, documented, exits cleanly |
| 8 | **Explanation actionability test (CUJ 3):** Scripted test: given a denied call + its explanation, a human (or LLM judge) can identify the one change that would get it allowed | — | Actionability test passes: explanation identifies the blocking factor |
| 9 | **Quickstart documentation:** `docs/reference/quickstart.md` — 15-line integration walkthrough with copy-pasteable commands. Covers: install, init, evaluate, integrate | F-52 | Follow the quickstart end-to-end in under 5 minutes |
| 10 | **CLI integration tests:** Every command tested with valid and invalid inputs | — | `tooltrust evaluate` with all flags → correct output; `tooltrust init` → valid YAML; `tooltrust check` → validates correctly |

### M6 Success Metrics

| Metric | Target | Verification |
|--------|--------|-------------|
| CLI completeness | All planned commands implemented and tested | CLI integration test suite |
| Init experience | `tooltrust init` → valid tooltrust.yaml in < 1 second | Time-to-init test |
| Explanation actionability | 100% of denied calls have actionable explanations | CUJ 3 test suite |
| Quickstart time | < 5 minutes install → first evaluate() | Timed quickstart walkthrough |
| Test coverage | >95% on CLI module | `pytest --cov=agent_tooltrust.cli --cov-fail-under=95` |

### M6 Exit Gate

- [x] Code review passed (every file reviewed)
- [x] Every `.py` file has module-level and function-level docstrings
- [x] Test coverage >95% (`pytest --cov=agent_tooltrust --cov-fail-under=95`)
- [x] Ruff clean (`ruff check .` — 0 errors)
- [x] Mypy strict clean (`mypy --strict` — 0 errors)
- [x] All CLI commands work with valid inputs
- [x] All CLI commands fail gracefully with invalid inputs (exit non-zero + message)
- [x] `tooltrust init` generates valid YAML for all 3 postures
- [x] Explanation actionability test passes (CUJ 3)
- [x] Quickstart document is followable end-to-end

**Dependency:** M1-M5 (all prior milestones)
**Produces for later milestones:** Full CLI surface, quickstart doc