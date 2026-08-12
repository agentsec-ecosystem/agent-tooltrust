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

### PydanticAI (BLOCKED)
- Error: `'Agent' object has no attribute 'tools_functions'`
- Root cause: PydanticAI 2.28 registers tools via `@agent.tool` decorator, not `agent.tools_functions.append()`
- When using `agent.tool(fn)` as a function call (not decorator): `First parameter of tools that take context must be annotated with RunContext[...]`
- Next: use `@agent.tool` as decorator with proper function definition

### CrewAI (BLOCKED)
- Error: `ImportError: Fallback to LiteLLM is not available`
- Root cause: CrewAI's LLM falls back to LiteLLM which isn't installed
- Next: install `litellm` or use alternative LLM configuration

### OpenAI Agents SDK (BLOCKED)
- Error: `additionalProperties should not be set for object types`
- Root cause: Pydantic version conflict — OpenAI Agents SDK uses strict JSON schema
- Next: downgrade pydantic or add `strict=False` to function tools

### AutoGen / AG2 (BLOCKED)
- Error: `agent name must be a valid Python identifier`
- Root cause: Using `agent_id` like `"ag-01"` (contains hyphen) as agent name
- Fix: sanitize agent name (replace `-` with `_`)

### Remaining frameworks (untested)
- Smolagents, LlamaIndex, ADK, SWE-bench, ToolTrust MCP

## Lessons

1. **Don't confuse engine-only matrices with real-agent tests.** The user wants the LATTER.
2. **Use `RawAdapter.guard()` for simple tool wrapping** across all frameworks — it works universally with any Python callable.
3. **Each framework's build_agent shim must handle its own package import errors** lazily (MissingFrameworkError with clear install hint).
4. **Simple tool names MUST be in the taxonomy** — `get_weather`, `add`, `get_current_time`, `echo` were missing and caused `deny_unknown_tool`.
5. **Always save real-agent results to disk** (`tests/field/results/<framework>/`) with per-agent JSON — the WBS exit gate depends on it.
6. **Vendor repos (gitignored) + download script** is the right pattern — keeps the repo small, reproducible.
7. **The `@pytest.mark.field` marker** gates the build-agent test — deselected by default, run via `-m field`. Designed to FAIL (not skip) when framework deps are missing.
