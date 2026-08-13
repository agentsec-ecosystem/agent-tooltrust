# Security Baseline

Agent ToolTrust ships a tiered security baseline so adopters can self-verify
that the deployment meets a minimum security posture. `tooltrust baseline check`
evaluates every item automatically and reports pass/fail per item.

The **Essential** tier (v0.1.0) is the default install posture. Higher tiers
(**Hardened**, **Certified**) target v0.2.0+ and are documented in the roadmap.

## Tiers

| Tier | Version | Summary | Command |
|------|---------|---------|---------|
| **Essential** | v0.1.0 | Fail-closed engine, auditable policy, secret scanning | `tooltrust baseline check essential` |
| **Hardened** | v0.2.0 | Adds argument validation, output inspection, rate limiting | v0.2.0 (roadmap) |
| **Certified** | v0.3.0 | Adds dispatcher parsing, child delegation, tamper-evident audit | v0.3.0 (roadmap) |

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

## How the command works

`tooltrust baseline check essential` runs the checklist above. Each item is
evaluated programmatically — e.g. confirming the fail-closed handler exists,
the default policy contains deny rules, the audit and tamper-proof modules are
importable, and the ruff/mypy configs are strict. It exits 0 only when every
Essential item passes, making it safe to use as a release gate.
