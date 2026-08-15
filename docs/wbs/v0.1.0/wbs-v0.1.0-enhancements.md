# WBS — Agent ToolTrust v0.1.0 Enhancement Pull-Forward

> **Milestones covered:** M19-M23 (v0.2/v0.3/v0.4 features pulled into v0.1.0)
> **GitHub Issues:** #123-135

| File | Milestones | Version | GitHub Issues | Status |
|------|-----------|---------|---------------|--------|
| [wbs-v0.1.0-enhancements.md](wbs-v0.1.0-enhancements.md) | M19-M23 (Security, OTel, Extensibility, Governance, SWE-bench) | v0.1.0 | #123-135 | **Complete ✅** |

## Issue Summary

| Milestone | Name | Issues | Range |
|-----------|------|--------|-------|
| M19 | Security Depth (OWASP 9/10) | 3 | #123-125 |
| M20 | Observability & Limits | 3 | #126-128 |
| M21 | Extensibility & Developer UX | 4 | #129-132 |
| M22 | Compliance & Governance | 2 | #133-134 |
| M23 | SWE-bench Integration | 1 | #135 |
| **Total** | | **13** | #123-135 |

## v0.1.0 Enhancement Milestones

| M# | Name | Features | Source | Exit gate |
|----|------|----------|--------|-----------|
| M19 | Security Depth | Tool scanner, Output inspector, OWASP 9/10 | M10, M13 | OWASP 9/10 mapped in SECURITY.md |
| M20 | Observability & Limits | OTel spans, Rate/burst limits, CI regression suite | M11 | Spans visible, limits enforced, CI catches drift |
| M21 | Extensibility & UX | Arg validators, Custom risk dims, Policy test runner, Case studies | M9, M11 | Validators work, custom dims score, `tooltrust test` green |
| M22 | Compliance & Governance | Governance reports, Tamper-evident audit chain | M14, M17 | Reports generate, audit verify passes |
| M23 | SWE-bench | Wrapper + 5 benchmark task runs | M11 | **COMPLETE ✅ — 5/5 tasks, 2 violations flagged** |

## Exit Gate Checklist (Every Milestone)

- [ ] Code review passed on all files
- [ ] Test coverage >95% on new code
- [ ] Ruff clean: `ruff check .` → 0 errors
- [ ] Mypy strict clean: `mypy --strict` → 0 errors
- [ ] Full test suite passes (432+ tests)

---

## Milestone 19: Security Depth — OWASP 9/10

**Goal:** Close 2 more OWASP Agentic AI Top 10 gaps via tool scanning and output inspection.

### M19 Task Checklist

| # | Task | Feature ID | Exit criteria |
|---|------|------------|---------------|
| 1 | **OWASP 9/10 audit:** Map all 10 OWASP Agentic AI Top 10 risks to ToolTrust mitigations. Update `SECURITY.md` | — | 9/10 risks covered with mitigation; remaining A03 partial (needs output inspector) |
| 2 | **Tool definition scanner:** `tooltrust scan --tool <def>` — regex patterns for hidden instructions, typosquatting, adversarial patterns in tool descriptions | F-81 | Detects: injected system prompts, Unicode lookalikes, hidden instructions. 10/10 adversarial definitions caught |
| 3 | **Output inspector:** `@tooltrust.output_inspector` — scans tool results for secrets (key patterns), PII (regex), injected instructions before returning to model | F-82 | Catches: "sk-..." API keys, SSN patterns, "ignore previous instructions" payloads |

### M19 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] OWASP mapping updated in SECURITY.md (9/10)
- [ ] Scanner catches 10/10 adversarial tool definitions
- [ ] Output inspector catches secrets, PII, injection payloads

---

## Milestone 20: Observability & Limits

**Goal:** Add OTel tracing, per-session rate limits, and CI policy regression.

### M20 Task Checklist

| # | Task | Feature ID | Exit criteria |
|---|------|------------|---------------|
| 1 | **OTel spans:** Wrap Engine.evaluate() with OpenTelemetry spans. Attributes: tool, action, env, decision, reason_code, latency | F-44 | Spans appear in OTel collector (console exporter) |
| 2 | **Session rate/burst limits:** Per-session call rate (calls/sec) and burst ceiling in SessionStore | F-86 | Rate limit kicks in after threshold; burst allows short spikes |
| 3 | **CI policy regression suite:** `tooltrust test` replays golden fixtures. Drift detection via CI job | F-84 | Change policy → CI catches unexpected decision change |

### M20 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] OTel spans visible in collector
- [ ] Rate limiter correctly throttles
- [ ] CI policy regression catches drift

---

## Milestone 21: Extensibility & Developer UX

**Goal:** Argument validation, custom risk dimensions, policy test runner, and case studies.

### M21 Task Checklist

| # | Task | Feature ID | Exit criteria |
|---|------|------------|---------------|
| 1 | **Argument-level validators:** `@tooltrust.arg_validator("regex", pattern=...)`, `"range"`, `"path"`, `"url"` decorators | F-80 | Each validator independently testable |
| 2 | **Custom risk dimension registry:** `@tooltrust.risk_dimension("my_dim")` decorator. Registered functions participate in scoring | F-62 | Custom dim adds to weighted sum; testable in isolation |
| 3 | **Policy test runner:** `tooltrust test --fixtures tests.yaml` replays golden (tool → decision) fixtures | F-71 | CI runs policy tests on every PR |
| 4 | **Case studies:** "Understanding Criticality" README section with 5 real-world risk scenarios and ToolTrust decisions | F-73 | README section explains risk ladder with examples |

### M21 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] All 4 validators pass for valid input, deny for invalid
- [ ] Custom dimensions participate in weighted scoring
- [ ] `tooltrust test` replays fixtures correctly
- [ ] Case studies committed to README

---

## Milestone 22: Compliance & Governance

**Goal:** Governance report generation and tamper-evident audit chains.

### M22 Task Checklist

| # | Task | Feature ID | Exit criteria |
|---|------|------------|---------------|
| 1 | **Governance reports:** `tooltrust report --type compliance --period 2026-Q3 [--format html|csv]` — aggregates decisions by agent, tool, risk level, approval rates | — | Report generates valid HTML with charts; CSV export works |
| 2 | **Tamper-evident audit chain:** Hash-chain over audit log entries. `tooltrust audit verify` proves log integrity. ed25519 signing for root | F-34 | Verify clean → PASS; modify one entry → verify FAIL with entry index |

### M22 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] Governance report generates valid HTML + CSV
- [ ] Tamper-evident chain verifiable and falsifiable

---

## Milestone 23: SWE-bench Integration

**Goal:** Run ToolTrust as a policy wrapper for SWE-bench coding agents.

### M23 Task Checklist

| # | Task | Exit criteria | Status |
|---|------|---------------|--------|
| 1 | **SWE-bench wrapper:** ToolTrust wraps SWE-bench coding agent runs. Tool policy enforced during benchmark; decision trace per task. Run on 5 benchmark tasks | 5/5 SWE-bench tasks run with ToolTrust; all tool calls logged; violations flagged | **Done ✅** — `SWEBenchGuard`/`SWEBenchRunner` in `agent_tooltrust.integrations.swe_bench`, `tooltrust swebench` CLI, 5-task fixture, 2 violations flagged |

### M23 Exit Gate

- [x] Code review, >95% coverage, ruff clean, mypy strict
- [x] ToolTrust wraps SWE-bench agent runs
- [x] 5 benchmark tasks complete with decision traces
- [x] Violations flagged in trace output