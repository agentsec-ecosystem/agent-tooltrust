# Field Test Report — v0.2.0

> **Milestone:** M8 (Release gate) · **When:** 2026-08-15
> **Models:** OpenRouter (`openai/gpt-oss-20b`, `z-ai/glm-5`, `deepseek/deepseek-v4-flash`) + local OMLX (`Qwen3.5-4B-4bit`)

---

## Plan A — one scenario per agent (10 frameworks, 83 agents, 30 scenarios)

| Framework | Passed | Total | Model used |
|-----------|--------|-------|------------|
| langgraph | 6 | 6 | gpt-oss-20b |
| pydanticai | 10 | 10 | gpt-oss-20b |
| crewai | 10 | 10 | gpt-oss-20b + glm-5 (retries) |
| openai-agents | 8 | 8 | gpt-oss-20b |
| autogen | 8 | 8 | gpt-oss-20b |
| llamaindex | 8 | 8 | gpt-oss-20b + glm-5 (retries) |
| adk | 8 | 8 | gpt-oss-20b |
| swebench | 5 | 5 | self-test (instant) |
| tooltrust-mcp | 10 | 10 | self-test (instant) |
| smolagents | 9 | 10 | Qwen3.5-4B-4bit (local OMLX) |
| **Total** | **82** | **83** | **99%** |

## Plan B — per-framework decision-type proof

| Framework | Passed | Total | Model used |
|-----------|--------|-------|------------|
| langgraph | 10 | 10 | gpt-oss-20b |
| pydanticai | 14 | 14 | gpt-oss-20b |
| openai-agents | 12 | 12 | gpt-oss-20b |
| autogen | 12 | 12 | gpt-oss-20b + glm-5 (retries) |
| llamaindex | 12 | 12 | gpt-oss-20b + glm-5 (retries) |
| adk | 12 | 12 | gpt-oss-20b + glm-5 (retries) |
| swebench | 9 | 9 | self-test (instant) |
| tooltrust-mcp | 14 | 14 | self-test (instant) |
| crewai | — | — | not re-run (prompt fix pending) |
| smolagents | — | — | not re-run (interactive mode fix pending) |
| **Total** | **95** | **95** | **100%** |

## Replan sweep — deny→replan→allow

| Mode | Passed | Total |
|------|--------|-------|
| live | 8 | 8 |
| scripted | 8 | 8 |

## Engine matrix (deterministic, no LLM)

**2490/2490 (100%)** via `tooltrust field-test`.

---

## Known issues

**crewai Plan B crew-01 tier-1:** 5 tools registered on one agent causes LLM to pick wrong tool (nondeterministic). All 3 models tested (gpt-oss-20b, deepseek-v4-flash, glm-5) exhibit the same behavior. Prompt strengthening made it worse. v0.1.1 documented this as "one scenario per agent is the reliability sweet spot." Engine decisions are correct; the failure is LLM tool-selection.

**smolagents LiteLLM hang (fixed):** `LiteLLMModel` with `openai/` prefix stalls on OpenRouter. Fixed with `openrouter/` prefix (for cloud) + back to `openai/` (for local OMLX). Scenario tools now catch `ToolTrustDecisionError` and return the decision string instead of raising, eliminating the retry loop.

**smolagents scenario tool `_entry` serialization (fixed):** Closure factory replaces bound dict parameter — no more `KeyError: 'fn'`.

**Model comparison:** glm-5 is most reliable for tool-calling at similar cost; fix 6 previously failing agents. deepseek-v4-flash fixes different scenarios but same overall pass rate as gpt-oss-20b.