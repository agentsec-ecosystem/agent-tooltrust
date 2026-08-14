# WBS — Agent ToolTrust

Work Breakdown Structure — milestone plans and task breakdowns for all versions.

> **GitHub Issues:** 135 issues across 2 versions. All issues link back to these WBS files.

| File | Milestones | Version | GitHub Issues | Status |
|------|-----------|---------|---------------|--------|
| [v0.1.0/wbs-v0.1.0-part1-engine.md](v0.1.0/wbs-v0.1.0-part1-engine.md) | M1-M2 (Engine + Policy) | v0.1.0 | #1-23 | **Complete ✅** |
| [v0.1.0/wbs-v0.1.0-part2-audit-adapters.md](v0.1.0/wbs-v0.1.0-part2-audit-adapters.md) | M3-M4 (Audit + Adapters) | v0.1.0 | #24-43 | **Complete ✅** |
| [v0.1.0/wbs-v0.1.0-part3-cli-mcp.md](v0.1.0/wbs-v0.1.0-part3-cli-mcp.md) | M5-M6 (MCP + CLI) | v0.1.0 | #44-57 | **Complete ✅** |
| [v0.1.0/wbs-v0.1.0-part4-field-ship.md](v0.1.0/wbs-v0.1.0-part4-field-ship.md) | M7-M8 (Field + Ship) | v0.1.0 | #58-76 | **M7 Complete ✅** (Plan A 83/83, replan 8/8, CI gate; Plan B 116/123 w/ 7 doc'd no-call). **M8 in progress** — demo done, hardening/lint/coverage done, CHANGELOG+release+PyPI (v0.1.0/v0.1.1) done, full sweep green. Remaining: OpenSSF Silver (#67), OWASP 5/10 (#68), Essential baseline (#69), Ruff/Mypy closeout (#72), repo public (#75), exit gate (#76) |
| [v0.1.0/wbs-v0.1.0-enhancements.md](v0.1.0/wbs-v0.1.0-enhancements.md) | M19-M23 (Security, OTel, Extensibility, Governance, SWE-bench) | v0.1.0 | #123-136 | **Complete ✅** |
| [v0.1.0/wbs-v0.1.0-docker.md](v0.1.0/wbs-v0.1.0-docker.md) | M24 (Docker + Container Tests) | v0.1.0 | #137-141 | **Complete ✅** |
| [v0.2.0/wbs-v0.2.0.md](v0.2.0/wbs-v0.2.0.md) | M1-M8 (Policy, Scoping, Escalation, Threat, Audit, Service, Compliance, Release) | v0.2.0 | #81, #83-86, #88-89, #91, #93, #95, #97, #100-101, #103-104, #106-108, #110-117, #119-122, #142-148 | In progress (`rel-0.2.0`) — **M1 complete ✅**, **M2 complete ✅** (scoping, delegation, dispatcher; gates: ruff/mypy/review done, coverage lift + CI pending) |
| [v0.2.0/wbs-v0.2.0-m7_5.md](v0.2.0/wbs-v0.2.0-m7_5.md) | M7.5 (Operator Console & Web Dashboard) | v0.2.0 | #149-157 | **In progress (`rel-0.2.0`)** — all 9 tasks implemented ✅ (shell, escalations, audit, sessions, analytics, baselines, Playwright, Docker hosting, containerized tests); gates: suites green, screenshots committed; pending issue closeout |

## Issue Summary

| Milestone | Version | Issues | Closed | Range |
|-----------|---------|--------|--------|-------|
| M1-M2 | v0.1.0 Engine + Policy | 23 | 23 | #1-23 |
| M3-M4 | v0.1.0 Audit + Adapters | 20 | 20 | #24-43 |
| M5 | v0.1.0 MCP Server | 6 | 6 | #44-49 |
| M6 | v0.1.0 CLI + Explanation | 8 | 8 | #50-57 |
| M7-M8 | v0.1.0 Field + Ship | 19 | 6 | #58-76 |
| M19-M22 | v0.1.0 Enhancements | 12 | 12 | #123-134 |
| M23 | v0.1.0 SWE-bench | 1 | 1 | #135 |
| M20 (extra) | v0.1.0 Rate limits | 1 | 1 | #136 |
| M24 | v0.1.0 Docker + Tests | 5 | 5 | #137-141 |
| M9-M18 | v0.2.0 (old scheme) | 44 | 17 | #77-122 |
| M1-M8 | v0.2.0 (re-baselined) | 36 | 0 | #81-122, #142-148 |
| **Total** | | **142** | **92** | #1-141 |

## v0.1.0 Milestone Summary

> **Status: M1-M7, M19-M24 Complete ✅. M7 (Field Test) — all 10 frameworks wired; Plan A 83/83 (100%), replan 8/8, LLM-free CI gate; Plan B 116/123 (7 `not-available` = LLM no-call, documented). Results + consolidated `FIELD_TEST_REPORT.md` committed. Remaining: M8 (Ship).**

| M# | Name | Features | CUJs | Exit gate |
|----|------|----------|------|-----------|
| M1 | Core Engine | F-01-F-05, F-07, F-12, F-20-F-22, F-89(P0) | CUJ 1, 9, 11 | Code review, >95% coverage, lint strict, 40-cell matrix — **COMPLETE ✅ (commit `4649365`)** |
| M2 | Policy Manager | F-06, F-10, F-60, F-63, F-65-F-67, F-70, F-72 | CUJ 4, 8 | Code review, >95% coverage, lint strict, OPA parity — **COMPLETE ✅ (commit `1b1c4dd`)** |
| M3 | Audit Logger | F-30, F-31, F-33 | CUJ 6 | 3 sinks verified, CLI audit working — **COMPLETE ✅** |
| M4 | Integration Adapters | F-40-F-42 | CUJ 2 | 6 adapters pass integration tests — **COMPLETE ✅** |
| M5 | MCP Server | F-11, session state, /audit HTTP | CUJ 2 | Server starts, 3 tools, session tracking, audit emitted — **COMPLETE ✅** |
| M6 | CLI + Explanation | F-23, F-51, F-52, F-74, F-85 | CUJ 3, 8 | All CLI commands working, quickstart verified, CUJ 3 actionability passes — **COMPLETE ✅** |
| M7 | Field Tests | F-75 | CUJ 7, 11 | 10-framework sweep (83 agents), real LLM via OMLX |
| M8 | Demo + Hardening + Ship | F-50, F-91 | All P0 CUJs | PyPI v0.1.0, OpenSSF Silver, OWASP 5/10 |
| **M19** | **Security Depth** | Scanner, Output inspector, OWASP 9/10 | — | **v0.1.0 pull-forward (#123-125)** |
| **M20** | **Observability** | OTel, Rate limits, CI regression | — | **v0.1.0 pull-forward (#126-128)** |
| **M21** | **Extensibility & UX** | Arg validators, Custom dims, test runner | — | **v0.1.0 pull-forward (#129-132)** |
| **M22** | **Governance** | Reports, Tamper-evident audit | — | **v0.1.0 pull-forward (#133-134)** |
| **M23** | **SWE-bench** | Wrapper + 5 task runs | — | **COMPLETE ✅ (#135)** |
| **M24** | **Docker + Container Tests** | Dockerfile, Makefile, smoke, SSE integration, CI | — | **COMPLETE ✅ (#137-141)** |

## Exit Gate Checklist (Every Milestone)

- [ ] Code review passed on all files
- [ ] Every `.py` file has module-level and function-level docstrings with Args/Returns/Raises
- [ ] Test coverage >95% (`pytest --cov=agent_tooltrust --cov-fail-under=95`)
- [ ] Ruff clean: `ruff check . --select ALL` → 0 errors
- [ ] Mypy strict clean: `mypy --strict` → 0 errors