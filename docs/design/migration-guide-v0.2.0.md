# Migration Guide — v0.1.x → v0.2.0

> **Applies to:** users upgrading from `agent-tooltrust` 0.1.0 / 0.1.1 to 0.2.0.
> **Install:** `pip install --upgrade agent-tooltrust`

---

## Summary

v0.2.0 keeps the same core decision pipeline (`NORMALIZE → SCORE → DECIDE → EXPLAIN → AUDIT`) and the same `Engine.evaluate()` API. **There are no breaking changes to the in-process Python API.** Most of the work is additive: new CLI commands, new server endpoints, new audit capabilities, and a hardened security posture.

Your existing `tooltrust.yaml`, `Engine()` calls, and adapters continue to work unchanged.

---

## Breaking changes

There are **no breaking changes** that require code edits for normal users. Items below are behavior notes, not migration requirements.

| Change | What changed | Do I need to act? |
|--------|-------------|-------------------|
| `__version__` | 0.1.1 → 0.2.0 | Replace any pinned `agent-tooltrust==0.1.x` with `>=0.2,<0.3`. |
| `Decision` JSON shape | Added `counterfactual` field (score threshold that would flip the decision) | Read-only addition — no action needed. |
| `AuditEntry` schema | Added `arguments`, `redacted`, `credential_status`, `counterfactual` fields | If you parse audit JSONL directly, new fields appear; old fields are unchanged. |
| Audit sinks | JSONL/SQLite/Postgres now persist a hash chain at write time | Old logs lack chain fields; `verify` will flag them as unverifiable (expected). Re-export/re-log to get chained entries. |
| Audit redaction | Sensitive arg keys (token, password, apiKey, …) are redacted as `***REDACTED***` by default, `redacted: true` flag set | Watch for redacted args in log consumers. Overridable per-policy. |

If you consume the audit trail programmatically and expect raw (unredacted) argument values, new decisions now arrive redacted — see [Audit redaction](#audit-redaction) below.

---

## What's new in v0.2.0

### 1. Fleet & PDP features

- **`POST /authorize` HTTP endpoint** — language-agnostic Policy Decision Point. Post a JSON tool call and get Decision JSON back. Built for Go/JS/Java fleet callers and gateways.
- **MCP-Data connector** — `tooltrust.authorize_data_source` MCP tool + `mcp_data.py` module for per-data-source authorization (`mcp_data.<source_id>` taxonomy registration).
- **OPAL distributed policy sync** — `Engine.reload_policy()` + an OPAL client (`integrations/opal.py`); `tooltrust policy rollback --version <v>`.
- **Policy packs catalog** — `packs/` community catalog (5 seed packs) + `tooltrust pack list` / `pack info`.

### 2. Audit & Observability

- **Session replay** — `tooltrust audit session --replay <id>` reconstructs cumulative risk from the audit trail.
- **Session analytics** — `tooltrust analytics sessions` + `GET /api/analytics/sessions`: recurring denials, deny→allow transitions, dead/over-hit rules.
- **Score calibration** — `tooltrust calibrate report` + `GET /api/analytics/calibration`: counterfactual thresholds, per-tool/env/data-class rates.
- **Audit redaction** — deny-list `token`, `password`, `apiKey`, `authorization`, `secret`, … with per-policy override; `redacted: true` flag.
- **Stale-credential tagging** — `credential_status` on audit entries to distinguish engine-allow-but-credential-rejected calls.
- **Tamper-evident chain at write time** — sinks persist `chain_hash`/`prev_hash`; `audit verify` fails loudly on tamper.

### 3. Security & Compliance

- **ToolTrust Hardened baseline** — `tooltrust baseline check hardened` → **15/15 checks pass**; OWASP Agentic AI Top 10 **10/10** coverage.
- **OpenSSF Scorecard assessment** — documented path to Gold.

### 4. Server / Operator console additions

- `GET /api/analytics/sessions` and `/api/analytics/calibration` added to the operator console.

---

## New CLI commands

| Command | Purpose |
|---------|---------|
| `tooltrust audit session --replay <id>` | Replay a session's cumulative risk from audit |
| `tooltrust audit verify` | Verify audit hash-chain integrity |
| `tooltrust analytics sessions` | Session-to-session policy analytics |
| `tooltrust calibrate report` | Score calibration / false-rate report |
| `tooltrust pack list` / `pack info` | Policy pack catalog |
| `tooltrust policy rollback --version <v>` | Roll back a policy version |
| `tooltrust baseline check hardened` | Verify the Hardened security baseline |

---

## Audit redaction — action required?

Note the audit trail now redacts known-sensitive argument keys **by default** for every decision outcome (allow, audit, allow_with_obligation), not just audit-mode calls. The sensitive keys: `token`, `password`, `api_key`, `authorization`, `secret`, `key`, `passwd`, `credential`, `access_token`, `private_key`, `api_secret`, `client_secret`, `auth_token`, `bearer` (case-insensitive, nested dicts/lists).

**If you need to audit a non-default sensitive key**, pass extras when constructing the logger:

```python
from agent_tooltrust.audit.logger import AuditLogger
logger = AuditLogger(redact_keys={"api_token", "db_password"})
```

**If you intentionally want raw argument values persisted** (not recommended for secrets/PII), there is no per-call opt-out by default in v0.2.0 — redaction is a security default. Open an issue if you have a legitimate need to record sensitive argument values.

---

## API reference — same as v0.1.x

The in-process integration surface is unchanged:

```python
from agent_tooltrust import Engine

engine = Engine()
result = engine.evaluate(tool_name="query_logs", action="read",
                         environment="staging", data_class="internal",
                         agent_id="debug-bot")
```

All framework adapters (LangGraph, PydanticAI, OpenAI Agents SDK, CrewAI, AutoGen, Smolagents, LlamaIndex, ADK, MCP, SWE-bench) work without changes.

---

## How to upgrade

```bash
pip install --upgrade "agent-tooltrust>=0.2,<0.3"
```

```bash
# verify the install
tooltrust --version        # 0.2.0
tooltrust baseline check hardened   # 15/15 PASS expected
```

---

## Known limitations in v0.2.0

- Field-test tier-1 (5 tools on one agent) is unreliable with LLM tool-selection; engine itself validated 100% deterministically (see [field test report](../field-test/FIELD_TEST_REPORT-v0.2.0.md)).
- smolagents works against local OMLX; LiteLLM cloud-path interop documented as a caveat for some host integrations.
- `tooltrust serve` remains SSE-based; HTTP `/authorize` mounts there as a custom route.

---

## Notes / tips

- Field test report (`docs/field-test/FIELD_TEST_REPORT-v0.2.0.md`) has observations, conclusions, and model comparison lessons learned.
- Release checklist (`docs/wbs/v0.2.0/release-checklist.md`).

**Happy upgrading!**