# M7 Field Test — Learnings & Troubleshooting

## Architecture

### Two test layers (very different — keep them separate)

1. **Engine-only deterministic matrix** — `tooltrust field-test` / `FieldTestRunner`
   - Calls `Engine.evaluate()` directly with scenario tool/action/env/data_class
   - No LLM, no framework packages needed
   - 2490 assertions, 100% green
   - Useful for: policy regression, CI gating

2. **Real-agent LLM-driven field test** — what the user actually wants
   - Builds real framework agents via `build_agent()` shims
   - Prompts agent via LLM (OMLX at `http://127.0.0.1:8000/v1`)
   - LLM picks a tool → adapter guard intercepts → engine evaluates
   - Results stored per-agent in `tests/field/results/<framework>/<agent>.json`
   - Candidate result format:
     ```json
     {
       "agent_id": "lg-01", "framework": "langgraph",
       "tools": ["get_weather", "get_current_time"],
       "results": [
         {"tool": "get_weather", "called": true, "decision": "allow",
          "reason": "allow_low_risk", "elapsed_s": 4.7}
       ]
     }
     ```

### Roster — agents.yaml

- 83 agents across 10 frameworks (5-10 unique per framework)
- Each agent has `agent_id`, `framework`, `agent_class`, `domain`, `tools`, `source`
- Sources resolved against `tests/field/agents/vendor/` (downloaded repos, gitignored)
- Agent classes map to policy risk: ci-bot(0.1), engineer(0.3), general(0.5), analyst(0.7), sensitive(0.9)

## Per-Framework Results

### LangGraph ✅
```
lg-01: get_weather → ALLOW (allow_low_risk)
        get_current_time → ALLOW (allow_low_risk)
lg-02: add → ALLOW, get_weather → ALLOW
lg-03: get_weather → ALLOW, search_docs → ALLOW
lg-04: add → AUDIT (audit_sensitive_data)
        get_weather → AUDIT, get_current_time → AUDIT
lg-05: query_logs → AUDIT, get_current_time → AUDIT
lg-06: add → ALLOW, echo → ALLOW
```

- 13/13 LLM calls with guard interception — all passed
- Architecture: `RawAdapter.guard()` wraps raw Python tool functions, then `lg_tool(guarded)` wraps for LangChain, then `create_react_agent(llm, tools)`
- LLM: ChatOpenAI to OMLX `http://127.0.0.1:8000/v1`, model `Qwen3.5-4B-4bit`, api_key `omlx-test`
- LangGraph adapter's `ToolTrustToolNode` was broken (`_GuardedToolNode` not callable in langgraph v1.x) so we used `RawAdapter` instead

### PydanticAI (RESOLVED) ✅
- Error: `'Agent' object has no attribute 'tools_functions'`
- Root cause: PydanticAI 2.28 registers tools via `@agent.tool` decorator, not `agent.tools_functions.append()`
- When using `agent.tool(fn)` as a function call (not decorator): `First parameter of tools that take context must be annotated with RunContext[...]`
- Fix: use `@agent.tool` (or `agent.tool_plain`) as a decorator with proper function definition.

### CrewAI (RESOLVED) ✅
- Error: `ImportError: Fallback to LiteLLM is not available`
- Root cause: CrewAI's LLM falls back to LiteLLM which isn't installed
- Fix: `uv add litellm` (already a pyproject dep). Now record via `crew.kickoff(inputs={"input": prompt})` and read `result.raw`.
- CrewAI scanner tool wraps with `CrewAIAdapter.wrap_tool(...)`; scenario tools wrap `scenario_bound_tools(...)[0]["fn"]` with `@crew_tool(name)`.

### OpenAI Agents SDK (RESOLVED) ✅
- Error: `additionalProperties should not be set for object types`
- Root cause: Pydantic version conflict — OpenAI Agents SDK uses strict JSON schema
- Fix: `function_tool(..., strict_mode=False)`.
- **Model/endpoint wiring:** `set_default_openai_client(AsyncOpenAI(base_url=ENDPOINT, api_key=API_KEY))` + `set_default_openai_key(...)`. (NOT `set_default_openai_base_url` — that API doesn't exist in this version; use the client setter.)
- Invoke via `Runner.run_sync(agent, input=prompt)` and read `result.final_output`.

### AutoGen / AG2 (RESOLVED) ✅
- Error: `agent name must be a valid Python identifier`
- Root cause: Using `agent_id` like `"ag-01"` (contains hyphen) as agent name
- Fix: sanitize agent name (replace `-` with `_`).
- **The local Qwen model often answers textually instead of calling a tool unless the prompt is strongly directive.** The real `_prompt_for()` ("you must call the tool exactly named `scn_<id>` ... Do not skip the tool call") forces the call; a terse prompt does not.
- Invoke: `asyncio.run(agent.on_messages([TextMessage(content=prompt, source="user")], CancellationToken()))` → read `response.chat_message.content`.

### Smolagents (RESOLVED) ✅
- `agent.run(prompt)` — do NOT pass `reset_stack=True` (raises TypeError in this version).
- `@tool` requires a docstring with per-arg descriptions or it fails schema generation (`DocstringParsingException`).
- Scenario guard `entry["fn"]` is `_echo(text)`-style — its keyword arg is `text`.
- Returns the final answer as a plain string.

### LlamaIndex (RESOLVED) ✅
- Two ReActAgent variants exist. In `llama-index-core 0.14` use the **workflow** agent: `from llama_index.core.agent.workflow import ReActAgent`. The legacy `llama_index.core.agent.ReActAgent` has no `.query()`/`.chat()`.
- Invoke is a pydantic Workflow: `ctx = Context(workflow=agent); handler = agent.run(user_msg=prompt, ctx=ctx); async for event in handler.stream_events(): ...` — the `async for` DRIVES execution. A separate `await handler` then `stream_events()` yields nothing (already-consumed handler).
- Build response text from `AgentStream` events (`event.response.delta` / `.text`).
- **Custom/local model:** `OpenAI(model="Qwen3.5-4B-4bit", api_base=ENDPOINT)` fails at `metadata` because `openai_modelname_to_contextsize()` can't resolve the name. Subclass `OpenAI` and override the `metadata` property with a `LLMMetadata(context_window=32768, is_function_calling_model=True, system_role="system", ...)`. NB `system_role` must be lowercase `"system"` (pydantic enum rejects `"SYSTEM"`).

### Google ADK (RESOLVED) ✅
- `Agent(name=..., model=MODEL_STRING)` fails at runtime: `ValueError: Model Qwen3.5-4B-4bit not found.` ADK resolves model strings through its own LLM registry (Google/Gemini), not OMLX.
- Fix: pass `model=LiteLlm(model=f"openai/{MODEL}", api_base=ENDPOINT, api_key=API_KEY)` from `google.adk.models.lite_llm`.
- `InMemorySessionService.create_session(...)` is a **coroutine** — must be `await`-ed.
- Invoke: `runner = AdkRunner(agent=agent, app_name=..., session_service=session_service)`; `async for event in runner.run_async(user_id=..., session_id=..., new_message=Content(role="user", parts=[Part(text=prompt)])):`; read `event.is_final_response()` → `event.content`.
- Benign warning: `Default value is not supported in function declaration schema for Google AI` — harmless (the guarded fn has defaulted args).

### SWE-bench (RESOLVED — self-test) ✅
- Not an interactive LLM agent; it's a replay harness (`SWEBenchRunner`). The field harness drives each scenario through the engine directly.
- Attach `runner._scenario_tools` (from `scenario_bound_tools`) and a `_scenario_tool(name)` accessor in the shim.

### ToolTrust MCP (RESOLVED — self-test) ✅
- Self-test wrapper (`SimpleNamespace` with `evaluate`/`describe`), not an interactive LLM agent.
- Attach a `scenario_tools` dict (scenario id → guarded callable) so the harness can invoke per scenario.

### Self-test invocation pattern (shared)
- Non-LLM frameworks (SWE-bench, ToolTrust MCP) register `scenario_tools` built from `scenario_bound_tools(engine, specs, agent_id)`.
- `scripts/run_field_agents.py::_self_test_run` parses the `` `scn_<id>` `` name from the prompt, looks it up in `scenario_tools` / `_scenario_tools`, and calls it with `text="field-test"` (the scenario `_echo` guard requires a `text` kwarg). This makes the engine record the decision so the row is not `not-available`.

### Remaining frameworks (untested)
- None — all 10 wired. (`langgraph`, `pydanticai` were already proven; the 8 above resolved in this session.)

## Run-count reduction — covering design (full cross product is unnecessary)

### The problem

Running the full WBS matrix as written — **every agent × every scenario** — on the local OMLX Qwen model is infeasible:

| Quantity | Value |
|---|---|
| Frameworks | 10 |
| Agents (roster) | 83 |
| Scenarios (20 decision + 10 adversarial) | 30 |
| Full cross product (every agent × every scenario) | **83 × 30 = 2,490 runs** |
| Cost per run on local LLM | ~30-80 s/call (multi-step ReAct); avg ~40 s |
| Estimated wall time at 10 workers | ~2,490 × 40 / 10 ≈ **~2.7 hours**, and often far more when the model answers textually and retries |

### Why the full cross product is overkill (how we arrived at the reduction)

1. **The engine is 100% framework-agnostic.** `Engine.evaluate(tool, action, env, data_class, agent_id)` knows nothing about langgraph/crewai/etc. A scenario's expected decision depends only on `(scenario, agent_class)`, never on the framework. So the framework axis contributes *adapter* evidence, not *engine* evidence.
2. **Engine correctness is already proven deterministically.** The engine-only `FieldTestRunner` matrix (2,490 assertions, 100% green, no LLM) already validates every `(scenario × agent_class)` cell against the golden expectations. Re-running every cell through the LLM re-validates the engine, which is redundant.
3. **The LLM field test's real job is adapter proof** — that each framework surfaces allow/audit/escalate/deny (and adversarial fail-closed) correctly inside a *real* agent loop (the "deny surfaced as a protocol crash vs a ToolMessage" class of bug, per DD-11). That is a per-framework property, not a per-cell property.
4. **Roster shape makes covering cheap.** Every one of the 10 frameworks already contains all 5 agent classes (ci-bot, engineer, general, analyst, sensitive). The scenario set only branches on 4 classes (ci-bot, engineer, analyst, sensitive) plus the `*` default — all already present in every framework.

Putting (1)-(4) together: we don't need 2,490 cells. We need a **covering design** where every scenario appears ≥1×, every agent runs ≥1×, and every framework runs ≥1× (ideally with each framework touching all decision types). The (scenario × agent_class) golden is left to the already-green deterministic matrix.

### Chosen plan — "one scenario per agent, distributed" (Plan A)

Assign each of the 83 roster agents **exactly one scenario**, with scenarios distributed so that:

- all 30 scenarios appear ≥1× (covers the **scenario axis**),
- every agent runs once (covers the **agent axis** — and therefore all **10 frameworks**),
- each framework's assigned scenarios span all 5 types (allow/audit/escalate/deny + adversarial), so each adapter is proven to surface every decision type,
- the handful of class-specific scenario expectations (keyed on ci-bot/engineer/analyst/sensitive) are paired with an agent of that class.

| Axis | Coverage | Runs |
|---|---|---|
| Scenarios (30) | each run ≥1× | 30 (distributed across the 83) |
| Agents (83) | each runs 1 scenario | 83 |
| Frameworks (10) | each has agents running | 10 |
| **Total runs** | | **83** |

| Metric | Full cross product | Plan A |
|---|---|---|
| LLM runs | 2,490 | **83** |
| Reduction | 1× | **~30×** |
| Est. wall time (@10 workers, 40 s/call) | ~2.7 h | **~5 min** |
| All scenarios covered | ✅ | ✅ |
| All agents covered | ✅ | ✅ |
| All frameworks covered | ✅ | ✅ |
| Every (scenario × class) golden cell re-validated via LLM | ✅ (redundant) | ❌ (left to the deterministic matrix) |
| Every framework proven to surface all 4 decision types + adversarial | ✅ | ✅ (collectively; per-framework in Plan B) |

8 of the 83 runs are real-LLM frameworks (langgraph, pydanticai, crewai, openai-agents, autogen, smolagents, llamaindex, adk); the other 15 are the SWE-bench + ToolTrust-MCP self-test agents which are instant (no LLM — they evaluate scenarios directly through the engine; see "Self-test invocation pattern" above). So the *LLM-bound* runs are only ~68.

### Optional richer plan — "adapter-proof + cover" (Plan B)

If, beyond coverage, you want **each framework individually** to prove all four decision types + one adversarial (not just collectively):

- **Tier 1 — adapter proof:** 1 agent per framework × 5 representative scenarios (allow / audit / escalate / deny / 1 adversarial) = 50 runs.
- **Tier 2 — roster smoke:** the remaining 73 agents × 1 scenario = 73 runs, chosen to fill any scenario not yet hit.

| Metric | Plan A | Plan B |
|---|---|---|
| Runs | 83 | ~123 |
| Reduction vs full | ~30× | ~12× |
| Each framework proves all decision types individually | no (collectively) | **yes** |
| Est. wall time | ~5 min | ~8 min |

### Reference: the rejected full options

| Plan | Runs | What it adds |
|---|---|---|
| C — full golden on 1 framework + smoke the rest | ~263 | re-runs the full 30×5-class golden grid on langgraph |
| Full cross product | 2,490 | every cell (overkill — engine already deterministically validated) |

### Recommendation

**Plan A** is the default: it satisfies "all scenarios + all agents + all frameworks, not all combinations," and leans on the already-green deterministic matrix for per-cell engine correctness. Use **Plan B** only if you want per-framework decision-type assurance written into the live run.

### Implementation note

The distribution is produced by a small planner that, given the roster + scenario set, assigns scenarios round-robin (sorted so class-specific expectations land on a matching-class agent) and guarantees every scenario id is assigned ≥1×. This maps to a `--plan A|B|full` flag on `run_field_agents.py` that runs exactly the assigned (agent → scenario) pairs instead of the full cross product.

## Lessons

1. **Don't confuse engine-only matrices with real-agent tests.** The user wants the LATTER.
2. **Use `RawAdapter.guard()` for simple tool wrapping** across all frameworks — it works universally with any Python callable.
3. **Each framework's build_agent shim must handle its own package import errors** lazily (MissingFrameworkError with clear install hint).
4. **Simple tool names MUST be in the taxonomy** — `get_weather`, `add`, `get_current_time`, `echo` were missing and caused `deny_unknown_tool`.
5. **Always save real-agent results to disk** (`tests/field/results/<framework>/`) with per-agent JSON — the WBS exit gate depends on it.
6. **Vendor repos (gitignored) + download script** is the right pattern — keeps the repo small, reproducible.
7. **The `@pytest.mark.field` marker** gates the build-agent test — deselected by default, run via `-m field`. Designed to FAIL (not skip) when framework deps are missing.
8. **Each framework's invoke handler (`script/run_field_agents.py::INVOKE_HANDLERS`) must be added or the framework shows `no invoke handler`.** Wiring the shim alone is not enough.
9. **The multi-adapter script (`run_field_agents.py`) swallows exceptions per scenario** — a broken handler shows up as `not-available` in 0.0s rather than a traceback. Debug by invoking the handler directly on one scenario and surfacing the exception.
10. **`not-available` (0.0s) ≠ `ok`.** If every row is `not-available`, the guard never ran — the handler isn't driving the agent to call a tool. Verify by checking `engine.recorded` for the scenario's `(tool, action, env, data_class, agent_id)` key.
11. **The local Qwen model (OMLX) is slow and non-deterministic about tool calls.** It answers textually unless the prompt is imperative ("you MUST call the tool exactly named `scn_<id>` ... Do not skip the tool call"). Full 30-scenario sweeps are ~5 min/framework (30-80s per LLM call); use `--agents` to test one agent or a scenario subset.
12. **Async frameworks need a real event loop.** PydanticAI/LlamaIndex/ADK/AutoGen handlers must `asyncio.run(...)` and `await` coroutines (e.g. ADK `create_session`, LlamaIndex `handler.stream_events()`). A 0.0s result after "building agent" often means an un-awaited coroutine or an already-consumed handler.
13. **Non-LLM "self-test" frameworks (SWE-bench, ToolTrust MCP) can't force the LLM** — wire them to evaluate each scenario directly via registered `scenario_tools` so the engine records the decision. Otherwise they stay `not-available`.
