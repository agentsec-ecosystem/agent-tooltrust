# WBS — Agent ToolTrust

Work Breakdown Structure — milestone plans and task breakdowns for all versions.

> **GitHub Issues:** 135 issues across 2 versions. All issues link back to these WBS files.

| File | Milestones | Version | GitHub Issues | Status |
|------|-----------|---------|---------------|--------|
| [wbs-v0.1.0-part1-engine.md](wbs-v0.1.0-part1-engine.md) | M1-M2 (Engine + Policy) | v0.1.0 | #1-23 | **Complete ✅** |
| [wbs-v0.1.0-part2-audit-adapters.md](wbs-v0.1.0-part2-audit-adapters.md) | M3-M4 (Audit + Adapters) | v0.1.0 | #24-43 | **Complete ✅** |
| [wbs-v0.1.0-part3-cli-mcp.md](wbs-v0.1.0-part3-cli-mcp.md) | M5-M6 (MCP + CLI) | v0.1.0 | #44-57 | **Complete ✅** |
| [wbs-v0.1.0-part4-field-ship.md](wbs-v0.1.0-part4-field-ship.md) | M7-M8 (Field + Ship) | v0.1.0 | #58-76 | Pending |
| [wbs-v0.1.0-enhancements.md](wbs-v0.1.0-enhancements.md) | M19-M22 (Security, OTel, Extensibility, Governance) complete + M23 (SWE-bench) pending | v0.1.0 | #123-136 | **M19-M22 done ✅** |
| [wbs-v0.1.0-docker.md](wbs-v0.1.0-docker.md) | M24 (Docker + Container Tests) | v0.1.0 | #137-141 | Pending |
| [wbs-v0.2.0.md](wbs-v0.2.0.md) | M9-M18 (Session, Escalation, Dispatcher, Delegation, Packs, Governance) | v0.2.0 | #81, #83-86, #88-89, #91, #93, #95, #97, #100-101, #103-104, #106-108, #110-117, #119-122 | Pending |

## Issue Summary

| Milestone | Version | Issues | Closed | Range |
|-----------|---------|--------|--------|-------|
| M1-M2 | v0.1.0 Engine + Policy | 23 | 23 | #1-23 |
| M3-M4 | v0.1.0 Audit + Adapters | 20 | 20 | #24-43 |
| M5 | v0.1.0 MCP Server | 6 | 6 | #44-49 |
| M6 | v0.1.0 CLI + Explanation | 8 | 8 | #50-57 |
| M7-M8 | v0.1.0 Field + Ship | 19 | 0 | #58-76 |
| M19-M22 | v0.1.0 Enhancements | 12 | 12 | #123-134 |
| M23 | v0.1.0 SWE-bench | 1 | 0 | #135 |
| M24 | v0.1.0 Docker + Tests | 5 | 0 | #137-141 |
| M20 (extra) | v0.1.0 Rate limits | 1 | 1 | #136 |
| M9-M18 | v0.2.0 All remaining | 44 | 17 | #77-122 |
| M24 | v0.1.0 Docker + Tests | 5 | 0 | #137-141 |
| **Total** | | **142** | **86** | #1-141 |

## v0.1.0 Milestone Summary

> **Status: v0.1.0 M1-M6 + M19-M22 Complete (86/141 closed). M23 (SWE-bench) + M24 (Docker) + M7-M8 (Field/Ship) pending.**

| M# | Name | Features | CUJs | Exit gate |
|----|------|----------|------|-----------|
| M1 | Core Engine | F-01-F-05, F-07, F-12, F-20-F-22, F-89(P0) | CUJ 1, 9, 11 | Code review, >95% coverage, lint strict, 40-cell matrix — **COMPLETE ✅ (commit `4649365`)** |
| M2 | Policy Manager | F-06, F-10, F-60, F-63, F-65-F-67, F-70, F-72 | CUJ 4, 8 | Code review, >95% coverage, lint strict, OPA parity — **COMPLETE ✅ (commit `1b1c4dd`)** |
| M3 | Audit Logger | F-30, F-31, F-33 | CUJ 6 | 3 sinks verified, CLI audit working — **COMPLETE ✅** |
| M4 | Integration Adapters | F-40-F-42 | CUJ 2 | 6 adapters pass integration tests — **COMPLETE ✅** |
| M5 | MCP Server | F-11, session state, /audit HTTP | CUJ 2 | Server starts, 3 tools, session tracking, audit emitted — **COMPLETE ✅** |
| M6 | CLI + Explanation | F-23, F-51, F-52, F-74, F-85 | CUJ 3, 8 | All CLI commands working, quickstart verified, CUJ 3 actionability passes — **COMPLETE ✅** |
| M7 | Field Tests | F-75 | CUJ 7, 11 | 10-agent sweep, 300 assertions pass |
| M8 | Demo + Hardening + Ship | F-50, F-91 | All P0 CUJs | PyPI v0.1.0, OpenSSF Silver, OWASP 5/10 |
| **M19** | **Security Depth** | Scanner, Output inspector, OWASP 9/10 | — | **v0.1.0 pull-forward (#123-125)** |
| **M20** | **Observability** | OTel, Rate limits, CI regression | — | **v0.1.0 pull-forward (#126-128)** |
| **M21** | **Extensibility & UX** | Arg validators, Custom dims, test runner | — | **v0.1.0 pull-forward (#129-132)** |
| **M22** | **Governance** | Reports, Tamper-evident audit | — | **v0.1.0 pull-forward (#133-134)** |
| **M23** | **SWE-bench** | Wrapper + 5 task runs | — | **v0.1.0 pull-forward (#135)** |
| **M24** | **Docker + Container Tests** | Dockerfile, Makefile, smoke, SSE integration, CI | — | **#137-141** |

## Exit Gate Checklist (Every Milestone)

- [ ] Code review passed on all files
- [ ] Every `.py` file has module-level and function-level docstrings with Args/Returns/Raises
- [ ] Test coverage >95% (`pytest --cov=agent_tooltrust --cov-fail-under=95`)
- [ ] Ruff clean: `ruff check . --select ALL` → 0 errors
- [ ] Mypy strict clean: `mypy --strict` → 0 errors