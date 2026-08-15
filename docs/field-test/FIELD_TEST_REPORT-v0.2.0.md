# Field Test Report — v0.2.0

> **Milestone:** M8 (Release gate) · **When:** 2026-08-15 ·
> **Model:** `openai/gpt-oss-20b` via OpenRouter
> **Scope:** 9 frameworks (smolagents excluded — blocked: LiteLLM hang on sm-02, to be resolved separately)

## Plan A — one scenario per agent

| Framework | Passed | Total | Status | Broken scenarios |
|-----------|--------|-------|--------|------------------|
| langgraph | 6 | 6 | ✅ | — |
| pydanticai | 10 | 10 | ✅ | — |
| crewai | 7 | 10 | ⚠️ | crew-01 (decision-allow-01, decision-audit-01, decision-escalate-01) |
| openai-agents | 8 | 8 | ✅ | — |
| autogen | 8 | 8 | ✅ | — |
| llamaindex | 6 | 8 | ⚠️ | li-01 (decision-allow-01), li-XX (decision-audit-XX) |
| adk | 8 | 8 | ✅ | — |
| swebench | 5 | 5 | ✅ | — |
| tooltrust-mcp | 10 | 10 | ✅ | — |
| **Total** | **68** | **73** | **93%** | |

## Plan B — per-framework decision-type proof

| Framework | Passed | Total | Status | Broken scenarios |
|-----------|--------|-------|--------|------------------|
| langgraph | 10 | 10 | ✅ | — |
| pydanticai | 14 | 14 | ✅ | — |
| openai-agents | 12 | 12 | ✅ | — |
| autogen | 11 | 12 | ⚠️ | ag-01:decision-escalate-01 |
| llamaindex | 10 | 12 | ⚠️ | li-01:decision-escalate-01 |
| adk | 11 | 12 | ⚠️ | adk-04:decision-allow-04 |
| swebench | 9 | 9 | ✅ | — |
| tooltrust-mcp | 14 | 14 | ✅ | — |
| crewai | 8 | 14 | ⚠️ | crew-01:adversarial-injection-01, crew-01:decision-allow-01, crew-01:decision-deny-01, crew-05:adversarial-unicode-03, crew-07:adversarial-whitespace-05, crew-10:adversarial-nonstring-08 |
| **Total** | **99** | **109** | **91%** | |

## Failures (mark for re-run)

All broken rows are **LLM tool-call nondeterminism** (`not-available`) — the model answered textually instead of calling the tool, so the engine decision was never reached. Not policy or engine regressions.

- **crewai Plan A:** crew-01 decision-allow-01, decision-audit-01, decision-escalate-01
- **crewai Plan B:** crew-01 adversarial-injection-01, decision-allow-01, decision-deny-01; crew-05 adversarial-unicode-03; crew-07 adversarial-whitespace-05; crew-10 adversarial-nonstring-08
- **autogen Plan B:** ag-01 decision-escalate-01
- **llamaindex Plan A:** li-01 decision-allow-01; **Plan B:** li-01 decision-escalate-01
- **adk Plan B:** adk-04 decision-allow-04

## Engine matrix (deterministic, no LLM)

Separately validated: **2490/2490 (100%)** via `tooltrust field-test` against the engine directly.