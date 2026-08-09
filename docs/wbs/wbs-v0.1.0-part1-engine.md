# WBS — Agent ToolTrust v0.1.0 Part 1: Engine Foundation

> **Milestones covered:** M1 (Core Engine) + M2 (Policy Manager)
> **Target:** M1 + M2 complete end of first build sprint
> **PRD:** [PRD.md](../design/PRD.md) | **Architecture:** [architecture-v0.1.0.md](../architecture/architecture-v0.1.0.md)

---

## Milestone 1: Core Engine — `evaluate()` to `Decision`

**Objective:** Stand up the full 5-stage decision pipeline (normalize → score → decide → explain → audit) as a pure Python library. A single `engine.evaluate()` call returns a correct `Decision` for every cell in the acceptance matrix.

**PRD coverage:** F-01, F-02, F-03, F-04, F-05, F-07, F-12, F-20, F-21, F-22, F-89(P0)
**CUJs covered:** CUJ 1 (15-line evaluate), CUJ 9 (degraded modes), CUJ 11 (adversarial resilience P0)

### M1 Task Checklist

> **Status: COMPLETE** — committed `4649365` (2026-08-09). 197 tests, 100% coverage, ruff clean, mypy strict clean, 40/40 cells green.

| # | Task | Feature ID | Verification | Status |
|---|------|------------|-------------|--------|
| 1 | **Taxonomy module:** `agent_tooltrust/taxonomy/` — 13-domain vocabulary (fs, shell, http, db, git, email, cloud, secrets, iam, payment, approval, search, notify) with verbs and baseline risk weights | F-05 | `tooltrust taxonomy list` prints all 13 domains with verb counts | ✅ `taxonomy/__init__.py` + `test_taxonomy.py` |
| 2 | **Normalization:** `engine/normalize.py` — `normalize(tool, action, env, data_class, agent_id) → NormalizedCall` dataclass. Whitespace collapse, Unicode NFKC, unknown-tool checks | F-04, F-89(P0) | Normalize 100 known tools + 50 edge cases (trailing spaces, Unicode lookalikes, case variants) — all known resolve correctly, all unknown → `deny("unknown_tool")` | ✅ `normalize.py` + `test_normalize.py` (confusables table, fail-closed on non-string input) |
| 3 | **Risk scorer:** `engine/score.py` — 5-dimension weighted sum. Default weights [1.0,1.0,1.0,1.0,1.0], per-dimension score from taxonomy + org config. `score(normalized_call, policy) → RiskScore` | F-03 | Score 40-cell matrix; verify monotonicity (higher-risk cells score higher) | ✅ `score.py` + monotonicity/boundary tests |
| 4 | **Decision engine:** `engine/decide.py` — `decide(risk_score, policy) → Decision`. Resolution order: explicit deny > explicit allow > explicit escalate > band mapping > default deny | F-02 | All 4 decision types produced on the acceptance matrix | ✅ `decide.py` + `test_decide.py`; all 4 types in matrix |
| 5 | **Explanation engine:** `engine/explain.py` — `explain(decision, risk_score, normalized_call) → Explanation`. Template substitution with `reason_code`, `explanation` sentence, `factors` list, `criticality` | F-20, F-21, F-22 | Every decision carries machine-readable reason_code + human explanation + factor breakdown | ✅ `explain.py` + `test_explain.py` |
| 6 | **Fail-closed handler:** `engine/fail_closed.py` — every exception path mapped to `deny` + distinct `reason_code`. Invalid input, unknown tool, malformed input, engine crash, timeout, audit failure | F-12 | 6 failure scenarios return deny with correct reason_code (CUJ 9 matrix) | ✅ `fail_closed.py` + `test_fail_closed.py` + CUJ 9 sweep in `test_acceptance_matrix.py` |
| 7 | **`Decision` and `NormalizedCall` dataclasses:** `types.py` — strict, frozen, with `__repr__` | F-02 | Importable, JSON-serializable, field validation on construction | ✅ `types.py` + `test_types.py` (frozen, validated, `to_dict`) |
| 8 | **Engine facade:** `engine/engine.py` — `Engine` class with `evaluate(tool, action, env, data_class, agent_id, ...) → Decision`. Orchestrates the 5-stage pipeline | F-01 | `engine.evaluate(...)` returns correct `Decision` in < 2 ms | ✅ `engine.py` + `test_engine.py` |
| 9 | **LLM explain (optional, off by default):** `engine/llm_explain.py` — post-decision, non-authoritative. Falls back to template on error. `Engine(enable_llm_explain=True)` | F-07, F-74 | LLM API error → template fallback; decision unchanged; latency not on hot path | ✅ `llm_explain.py` + `test_llm_explain.py` (fallback with no API key) |
| 10 | **Tool-name normalization:** `engine/normalize.py` → `_normalize_tool_name(name: str) → str`. NFKC, strip, lowercase, collapse multiple spaces. Rejects names with only whitespace | F-89(P0) | 50 adversarial name variants all normalize correctly; "dеploy" (cyrillic e) → "deploy" | ✅ confusables table; `test_normalize.py` lookalike/case/space suite |
| 11 | **Unit tests for core engine:** pytest covering all 5 stages individually + integration test (end-to-end `evaluate()`). Coverage target >95% | — | `pytest --cov=agent_tooltrust --cov-fail-under=95` | ✅ **100%** coverage (340/340 stmts), 197 tests |
| 12 | **Acceptance matrix test:** 40-cell matrix (tool × env × action × data_class) with expected decisions. Golden fixture file | — | All 40 cells produce expected decision; CI runs this on every push | ✅ `tests/fixtures/acceptance_matrix.yaml` + `test_acceptance_matrix.py` — 40/40 green |

> **Note re Task 1:** `tooltrust taxonomy list` (the CLI) is an M2+ CLI entry point; the M1 taxonomy module exposes `taxonomy_summary()` which prints the same 13-domain summary. CLI wiring ships with `tooltrust check` in M2.

### M1 Success Metrics

| Metric | Target | Verification |
|--------|--------|-------------|
| Decision correctness | 100% on 40-cell acceptance matrix | Automated test in CI |
| Fail-closed coverage | 6/6 failure scenarios → deny | CUJ 9 matrix test |
| Tool-name normalization | 50/50 adversarial names correct | Unicode/case/space test suite |
| Performance | < 2 ms per `evaluate()` | `pytest --benchmark` in CI |
| Test coverage | >95% | `pytest --cov-fail-under=95` |
| Lint | 0 ruff errors, 0 mypy errors (strict) | `ruff check . && mypy --strict` |

### M1 Exit Gate

- [x] Code review passed (commit `4649365`)
- [x] Every `.py` file has module-level docstring and function-level docstrings
- [x] Every public method has a docstring (Raises documented on `normalize`, `Engine.evaluate`, `fail_closed`)
- [x] Test coverage >95% (`pytest --cov=agent_tooltrust --cov-fail-under=95`) — **100% (340/340)**
- [x] Ruff clean (`ruff check .` — 0 errors)
- [x] Mypy strict clean (`mypy --strict` — 0 errors)
- [x] All 40-cell acceptance matrix passes
- [x] All 6 failure scenarios pass (CUJ 9) — unknown tool / blank tool / blank action / confusable / injection / fail-closed
- [x] All 50 tool-name normalizations pass (F-89 P0) — confusables, case, whitespace, fullwidth suite in `test_normalize.py`
- [x] `python -c "from agent_tooltrust import Engine; e = Engine(); print(e.evaluate(...))"` — verified via `Engine` smoke tests in `test_engine.py`; `Engine` is exported from the package

**Dependency:** None (M1 is the foundation)
**Produces for later milestones:** `Engine.evaluate()`, `Decision`, `NormalizedCall`, `RiskScore`, `Explanation` types

---

## Milestone 2: Policy Manager — YAML, OPA/Rego, Posture Presets

**Objective:** Ship the full policy configuration surface: YAML schema, posture presets (strict/balanced/permissive), OPA/Rego dual backend, `tooltrust check` validation, `tooltrust diff`, policy versioning.

**PRD coverage:** F-06, F-10, F-60, F-63, F-65, F-66, F-67
**CUJs covered:** CUJ 4 (shadow mode), CUJ 8 (customize posture)

### M2 Task Checklist

| # | Task | Feature ID | Verification |
|---|------|------------|-------------|
| 1 | **YAML policy schema:** `agent_tooltrust/policy/schema.py` — Pydantic model for `tooltrust.yaml`: version, posture, environments, data_classes, risk_weights, rules (allow/deny/escalate per tool/action/env/data), escalation (threshold, ttl), audit config | F-06, F-60 | Schema validates correct YAML, rejects malformed with line/column errors |
| 2 | **Policy loader:** `policy/loader.py` — `load_policy(path) → Policy`. Merge order: default_policy → org tooltrust.yaml → per-call context. Validates on load | F-60 | Loads valid policy, raises `PolicyParseError` with line/column on invalid |
| 3 | **Posture presets:** `policy/postures/` — `strict.yaml`, `balanced.yaml`, `permissive.yaml` shipped in package. Generated by `tooltrust init --posture <name>` | F-66 | Init generates correct preset; balanced is default; strict denies by default; permissive only denies destructive |
| 4 | **`tooltrust check`:** `cli/check.py` → reads tooltrust.yaml, validates against schema, reports errors with line/column | F-67 | Malformed YAML → parse error with location; missing required key → validation error; clean YAML → exit 0 |
| 5 | **`tooltrust diff`:** `cli/diff.py` → compares loaded policy against default posture, shows kept/overridden/gaps | F-65 | Diff output shows: kept defaults, overridden values, gaps (missing sections); machine-parseable format |
| 6 | **OPA/Rego backend:** `policy/opa.py` → `opa_evaluate(normalized_call, rego_policy_path) → Decision`. Subprocess `opa eval` with JSON input. Fail-closed on OPA unreachable | F-10, F-63 | Same NormalizedCall → same Decision from both native and OPA paths; OPA down → deny("opa_backend_unavailable") |
| 7 | **Policy hot-reload:** `policy/watcher.py` — `watch(path)` using `watchfiles`. Reloads policy on change without restart | F-60 | File change → policy reloaded within 1s; stale decisions return old policy version in audit |
| 8 | **Shadow mode:** `Engine(dry_run=True)` — decision computed + logged but returned as `allow`. Audit entry records both shadow and enforced decisions | F-70 | `dry_run=True` → caller always gets `allow`; audit shows the shadow decision; `tooltrust audit query --dry-run` filters |
| 9 | **Policy versioning:** `policy/version.py` — `version` field in tooltrust.yaml; recorded in every audit entry; `tooltrust check --migrate` detects breaking changes | F-72 | Policy version in every audit entry; migration check reports removed tools, renamed classes, threshold shifts |
| 10 | **Unit tests:** Policy loader (valid/invalid/missing), schema validation, posture preset correctness, OPA parity (same input = same output), shadow mode, hot-reload, versioning | — | >95% coverage on policy module |
| 11 | **Integration test:** Engine + policy: load a policy, evaluate 40 cells, verify decisions match policy rules (explicit overrides win over band mapping) | — | Explicit deny rule overrides scorer; explicit allow overrides scorer; shadow mode returns allow but logs real decision |

### M2 Success Metrics

| Metric | Target | Verification |
|--------|--------|-------------|
| Policy validation | 100% of malformed YAML caught with line/column | Fuzzing test with hypothesis |
| OPA parity | 100% matching decisions on 40-cell matrix | Dual-backend comparison test |
| Shadow mode | 100% shadow decisions logged; callers see allow | Integration test |
| Posture presets | 3 presets generate correct default policies | Diff test against expected output |
| Policy version in audit | Every audit entry includes policy_version | Audit integration test |
| Test coverage | >95% on policy module | `pytest --cov=agent_tooltrust.policy --cov-fail-under=95` |

### M2 Exit Gate

- [x] Test coverage >95% (`pytest --cov=agent_tooltrust --cov-fail-under=95`) — **100% on policy module, 97% overall**
- [x] Ruff clean (`ruff check .` — 0 errors)
- [x] Mypy strict clean (`mypy --strict` — 0 errors)
- [x] `tooltrust init --posture balanced` creates valid tooltrust.yaml
- [x] `tooltrust init --posture strict` creates valid tooltrust.yaml
- [x] `tooltrust init --posture permissive` creates valid tooltrust.yaml
- [x] `tooltrust check` accepts valid YAML, rejects malformed with line/column
- [x] `tooltrust diff` shows meaningful delta from defaults
- [ ] OPA path produces same decisions as native path on 40-cell matrix (mocked only — real Rego parity deferred)
- [x] OPA unreachable → deny with `opa_backend_unavailable` (does not crash)
- [x] Shadow mode correctly logs shadow decisions while returning `allow`
- [ ] Code review passed (every `.py` file reviewed)
- [ ] Every public method has Args/Returns/Raises docstring (partial coverage)

**Dependency:** M1 (Core Engine) — requires `Engine.evaluate()`, `Decision`, `NormalizedCall`
**Produces for later milestones:** `Policy` type, YAML schema, OPA integration, posture presets, `tooltrust check`, `tooltrust diff`