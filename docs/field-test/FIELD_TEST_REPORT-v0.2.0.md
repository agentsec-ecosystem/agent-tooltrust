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
| smolagents | 10 | 10 | Qwen3.5-4B-4bit (local OMLX) |
| **Total** | **83** | **83** | **100%** |

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
| crewai | 11 | 14 | Qwen3.5-4B-4bit (crew-01 tier-1 2/5) |
| smolagents | — | — | pending re-run |
| **Total** | **106** | **109** | **97%** |

## Replan sweep — deny→replan→allow

| Mode | Passed | Total |
|------|--------|-------|
| live | 8 | 8 |
| scripted | 8 | 8 |

## Engine matrix (deterministic, no LLM)

**2490/2490 (100%)** via `tooltrust field-test`.

---

## Known issues

### crewai Plan B crew-01 tier-1 — 5-tool multi-tool selection (ACCEPTED)

crew-01 registers 5 scenario tools on one agent. The LLM picks the wrong tool across all models tested:

| Model | crew-01 tier-1 | Single-tool agents |
|-------|----------------|--------------------|
| gpt-oss-20b | 2/5 | 100% |
| deepseek-v4-flash | 2/5 | 100% |
| glm-5 (z-ai) | 4/5 (best) | 100% |
| Qwen3.5-4B-4bit (local) | 2/5 | 100% |

glm-5 is the most reliable (4/5), but no model reaches 5/5. Prompt strengthening ("call ONLY the tool, do not call any other tool") made it *worse* (2/5), confirming it's a model tool-selection limit, not a prompt issue.

**Root cause:** 5 tools with near-identical names (`scn_decision-allow-01`, `scn_decision-audit-01`, `scn_decision-escalate-01`, `scn_decision-deny-01`, `scn_adversarial-injection-01`) confuse the LLM. v0.1.1 documented: "one scenario per agent (Plan A) is the reliability sweet spot."

**Verdict:** Engine decisions are correct (validated 100% by the deterministic matrix). The failure is LLM tool-selection on a 5-tool agent — a known model limitation, not a ToolTrust defect. Accepted for v0.2.0.

### smolagents fixes (RESOLVED)

1. **LiteLLM hang:** `openai/` prefix stalls on OpenRouter. Fixed with `openrouter/` prefix (cloud) + `openai/` (local OMLX).
2. **`_entry` serialization:** closure factory replaces bound dict param — no more `KeyError: 'fn'`.
3. **Deny retry loop:** scenario tools catch `ToolTrustDecisionError` and return the decision string instead of raising. Result: smolagents Plan A passes 10/10 against local OMLX.

### Model comparison (all 4 tested)

| Model | $/M in | $/M out | Tool-calling reliability | Notes |
|-------|--------|---------|--------------------------|-------|
| gpt-oss-20b | 0.03 | 0.13 | good single-tool | fails multi-tool |
| deepseek-v4-flash | 0.07 | 0.14 | good single-tool | same pattern as gpt-oss |
| glm-5 (z-ai) | similar | similar | **best** | 4/5 on tier-1, fixed 6 failing agents |
| Qwen3.5-4B-4bit (local) | free | free | unreliable tool calling | 6/10 in v0.1.1, but deterministic in self-test |