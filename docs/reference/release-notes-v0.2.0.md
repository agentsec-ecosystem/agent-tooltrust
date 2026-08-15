# Agent ToolTrust v0.2.0 Release Notes

**Status:** Released ✅
**Package:** `agent-tooltrust` · **Version:** 0.2.0
**Released:** 2026-08-15
**Related:** [WBS v0.2.0](../wbs/v0.2.0/wbs-v0.2.0.md) · [decisions-v0.2.0](../design/decisions-v0.2.0.md) · [Field Test Report](../field-test/FIELD_TEST_REPORT-v0.2.0.md) · [Migration Guide](../design/migration-guide-v0.2.0.md) · [CHANGELOG](../../CHANGELOG.md)

---

## Highlights

Agent ToolTrust v0.2.0 ships a **fleet-ready, auditable, hardened** policy decision point. The core engine is unchanged and battle-tested; everything around it — audit, observability, security posture, and service surfaces — grew substantially.

1. **Fleet & PDP** — HTTP `POST /authorize` for non-Python hosts, MCP-Data connector for per-data-source authorization, OPAL distributed policy sync, and a community policy-pack catalog.
2. **Audit & observability** — session replay, session-to-session analytics, score calibration, argument redaction, stale-credential tagging, and write-time tamper-evident hash chaining.
3. **Security & compliance** — OWASP Agentic AI Top 10 **10/10**, ToolTrust Hardened baseline **15/15 checks**, OpenSSF path-to-Gold documented.
4. **Quality gate** — 1068+ tests, 91% coverage, ruff + mypy --strict clean, field test Plan A **83/83 (100%)**, deterministic engine matrix **2490/2490 (100%)**.

---

## What's new

### Fleet & PDP (M6)

- **HTTP `/authorize` endpoint** — language-agnostic PDP: post a JSON tool call and get a Decision back (F-43). Ideal for Go/JS/Java callers and gateways.
- **MCP-Data connector** — `tooltrust.authorize_data_source` MCP tool and `mcp_data` module authorize per data source (`mcp_data.<source_id>` taxonomy registration).
- **OPAL distributed policy sync** — `Engine.reload_policy()`, `integrations/opal.py` client, and `tooltrust policy rollback --version <v>`.
- **Policy packs catalog** — `packs/` catalog with 5 seed packs (`db-queries`, `fs-basics`, `shell-safe`, `cloud-read`, `http-crud`); `tool pack list` / `pack info`.
- **Fleet deployment guide** — topology, nginx LB, docker compose, OPAL sync, rollback, monitoring.

### Audit & Observability (M5)

- **Session replay from audit** — `audit session --replay <id>` reconstructs cumulative risk identically to live use (shared `session_risk_increment`).
- **Session-to-session analytics** — recurring benign denials, deny→allow transitions, dead/over-hit rules (`analytics sessions` + `/api/analytics/sessions`).
- **Score calibration & shadow mode** — counterfactual thresholds, false-allow/escalate rates by tool/env/data-class (`calibrate report` + `/api/analytics/calibration`).
- **Audit argument redaction** — `token`, `password`, `apiKey`, `authorization`, `secret`, … redacted by default; `redacted: true` flag; nested dict/list coverage.
- **Stale-credential classification** — `credential_status` tag distinguishes engine-allow-but-credential-rejected calls from `not-available`.
- **Write-time tamper-evident chain** — JSONL/SQLite/Postgres persist `chain_hash`/`prev_hash`; `audit verify` fails loudly on tampered/missing entries.

### Security & Compliance (M7)

- **ToolTrust Hardened baseline** — `baseline check hardened` → **15/15 PASS** (fail-closed, adversarial normalization, deny rules, tamper chain, redaction, session analytics, delegation, escalation, output inspector, OTel, deny-storm detection, argument policy).
- **OWASP Agentic AI Top 10** — **10/10** covered (up from 5/10 in v0.1.0).
- **OpenSSF Scorecard** — 12/14 Gold criteria met, path to Gold documented.

### Threat & Anomaly (M4)

- **Deny-storm / probe detection** — session-level analyzer; throttle/lock/pause.
- **URL fetch category guard** — robots.txt, PII strip, SSRF redirect re-resolution.
- **External verification sink** — agent-unwritable ground truth vs self-report.

---

## Breaking changes & migration

**No breaking API changes.** The in-process `Engine.evaluate()` API, adapters, and policy format are unchanged. See [Migration Guide](../design/migration-guide-v0.2.0.md) for:
- `Decision` and `AuditEntry` gained read-only fields (`counterfactual`, `arguments`, `redacted`, `credential_status`, `chain_hash`/`prev_hash`).
- Audit sinks now persist tamper-evident chain fields at write time.
- Audit redaction is on by default (sensitive arg keys → `***REDACTED***`).

---

## Quality gates

| Gate | Result |
|------|--------|
| Unit + integration tests | **1068+ passed** |
| Test coverage | **91%** (threshold 90%) |
| Ruff (strict) | **clean** |
| mypy --strict | **clean** (100 source files) |
| Field test — Plan A | **83/83 (100%)** across 10 frameworks |
| Field test — Plan B | **116/123 (94%)** (tier-1 LLM tool-selection limit, accepted — see report) |
| Replan sweep | **8/8 live, 8/8 scripted** |
| Deterministic engine matrix | **2490/2490 (100%)** |
| Docker console | `docker compose up --wait` green |

---

## Field test summary

Plan A (one scenario per agent) passes **100%** for all 10 frameworks. Plan B proves every framework surfaces allow/audit/escalate/deny; the only misses are 7 tier-1 rows where the LLM picked the wrong tool when 5 tools share near-identical names — an LLM tool-selection limit, not an engine defect. Full findings, model comparison (gpt-oss-20b vs deepseek-v4-flash vs glm-5 vs local Qwen), observations, and lessons in the [Field Test Report](../field-test/FIELD_TEST_REPORT-v0.2.0.md).

---

## Known limitations / deferred (post-0.2)

- Tier-1 multi-tool field-test pattern is unreliable with current LLMs; recommended to drop or convert to Plan A style.
- Deny-storm active enforcement and verification-sink adapters finalized.
- Policy-analytics auto-mutation deferred (human approves suggestions).
- Fleet-scale performance validated only to the 3-instance OPAL test.
- smolagents cloud (OpenRouter) interop caveat documented; local OMLX path verified.

---

**Thanks for using Agent ToolTrust.**