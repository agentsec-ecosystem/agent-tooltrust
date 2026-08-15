# Security Baseline

Agent ToolTrust ships a tiered security baseline so adopters can self-verify
that the deployment meets a minimum security posture. `tooltrust baseline check`
evaluates every item automatically and reports pass/fail per item.

The **Essential** tier (v0.1.0) is the default install posture. The
**Hardened** and **Certified** tiers are the v0.2.0 targets (issues #103, #115;
WBS M7).

## Tiers

| Tier | Version | Summary | Command |
|------|---------|---------|---------|
| **Essential** | v0.1.0 | Fail-closed engine, auditable policy, secret scanning | `tooltrust baseline check essential` |
| **Hardened** | v0.2.0 | Adds argument validation, output inspection, rate limiting | `tooltrust baseline check hardened` |
| **Certified** | v0.2.0 | Adds dispatcher parsing, child delegation, tamper-evident audit | `tooltrust baseline check certified` |

## Essential Tier Checklist

Each item maps to a feature ID, a test, or a configuration flag so it can be
verified automatically by `tooltrust baseline check essential`.

| # | Item | Verification (feature / test / config) | Default |
|---|------|-----------------------------------------|---------|
| E1 | **Fail-closed engine**: unknown tool, malformed input, or any internal failure resolves to `deny`, never an allow | `engine/fail_closed.py`; `tests/test_fail_closed.py`, `tests/test_engine.py::test_evaluate_denies_*` | ✅ enforced |
| E2 | **Policy is declarative and auditable**: risk is determined by policy rules + risk scoring, reviewable as code | `policy/models.py`, `policy/loader.py`, `policy/schema.py`; `tooltrust check` | ✅ |
| E3 | **Four-way decision & explanation**: every call returns decision + reason_code + human explanation + risk factors | `engine/explain.py`, `engine/decide.py`; `tests/test_explain.py` | ✅ |
| E4 | **Adversarial tool-name normalization**: confusable/Unicode tool names cannot bypass the taxonomy | `engine/normalize.py` (NFKC + case-fold + transliteration); `tests/test_normalize.py` (F-89 P0) | ✅ |
| E5 | **Destructive & sensitive operations denied/escalated**: delete in production and customer-PII access are blocked by default posture | `policy/postures.py`, `policy/models.py` default rules; `tests/test_engine.py::test_evaluate_denies_*`, `test_decide.py` | ✅ |
| E6 | **Audit trail**: every allow/deny/escalate recorded with full call context | `audit/` (JSONL/SQLite/Postgres sinks), `audit/logger.py`; `tests/test_audit_*`, `tooltrust audit` | ✅ |
| E7 | **Tamper-evident audit chain**: records are chained so modification is detectable | `audit/tamper_proof.py`; `tests/test_governance.py::test_verify_chain_*` (F-34) | ✅ |
| E8 | **Secret scanning in CI**: credentials committed to the repo are caught before merge | `.github/workflows/ci.yml` trufflehog step; output inspector `tests/test_output_inspector.py` (F-82) | ✅ |
| E9 | **OWASP Agentic Top 10 mapping published**: risks and mitigations documented | `SECURITY.md` (§ OWASP coverage); 7/10 covered v0.1 | ✅ |
| E10 | **Lint & type gates**: Ruff 0 errors, Mypy `--strict` 0 errors enforced in CI | `pyproject.toml` `[tool.ruff]`, `[tool.mypy] strict=true`; `.github/workflows/ci.yml` | ✅ |
| E11 | **Reproducible build**: locked dependencies for deterministic installs | `uv.lock` (`uv lock`); `pyproject.toml` `[dependency-groups] dev` | ✅ |
| E12 | **Vulnerability disclosure SLA**: private reporting with 48h acknowledgement, 90d remediation | `SECURITY.md` (§ Reporting a Vulnerability) | ✅ |

**Essential tier status: 12/12 verified** by `tooltrust baseline check essential`.

## Hardened Tier Checklist (v0.2.0, #103)

Each item maps to a feature, a test, or a config flag verified by
`tooltrust baseline check hardened`. Hardened is a **superset** of Essential.

| # | Item | Verification (feature / test / config) |
|---|------|-----------------------------------------|
| H1 | **Argument-level policy**: every destructive tool has a validated argument schema (required fields, forbid-list, bounds, env allowlists) | argument policy module (DD-15); `tests/test_argument_policy.py` |
| H2 | **Output inspection**: secrets / PII / injections stripped before content reaches the model | output inspector (F-82); `tests/test_output_inspector.py` |
| H3 | **Rate limiting**: per-agent / per-session call rate enforced | rate-limiter module; `tests/test_rate_limit.py` |
| H4 | **URL fetch guard**: robots.txt enforced, PII stripped, SSRF redirect blocked | category guard (DD-19); `tests/test_fetch_guard.py` |
| H5 | **Escalation TTL + action identity**: approvals expire and bind to exact tool/action/args | EscalationManager (F-09); `tests/test_escalation.py` |
| H6 | **Replay-attempt detection**: reused escalation_id with a different call → deny | (F-89-P1); `tests/test_escalation.py::test_replay_*` |
| H7 | **Deny-storm / probe detection**: dense denies trip throttle/lock/pause | session analyzer (DD-16); `tests/test_deny_storm.py` |
| H8 | **Scope enforcement**: resource/environment scoping is default-deny | scope module (DD-18); `tests/test_scope.py` |
| H9 | **All Essential items still pass** | `tooltrust baseline check essential` |

## Certified Tier Checklist (v0.2.0, #115)

Certified is a **superset** of Hardened and adds tamper-evidence, output
inspection verification, and external review readiness. Verified by
`tooltrust baseline check certified`.

| # | Item | Verification (feature / test / config) |
|---|------|-----------------------------------------|
| C1 | **All Hardened items pass** | `tooltrust baseline check hardened` |
| C2 | **Dispatcher parsing**: `bash` / `aws` / `http` calls canonicalized; unparseable → deny | dispatcher (F-87); `tests/test_dispatcher.py` |
| C3 | **Child-agent delegation subset invariant**: child scope ⊆ parent scope | (F-88); `tests/test_delegation.py` |
| C4 | **Tamper-evident audit chain verified**: chain falsifiable, not just present | tamper-proof (F-34); `tests/test_governance.py` |
| C5 | **External verification sink**: agent-unwritable ground truth vs. self-report | verifier (DD-17); `tests/test_verification_sink.py` |
| C6 | **OWASP Agentic Top 10: 10/10 covered** | `SECURITY.md` 10/10 mapping |
| C7 | **External review readiness**: documented review process + evidence package | governance reports (F-XX) |

## How the command works

`tooltrust baseline check <tier>` runs the checklist for that tier. Each item is
evaluated programmatically — e.g. confirming the fail-closed handler exists,
the default policy contains deny rules, the audit and tamper-proof modules are
importable, argument-policy and scope modules are present, and the ruff/mypy
configs are strict. It exits 0 only when every item in the tier passes, making
it safe to use as a release gate.
