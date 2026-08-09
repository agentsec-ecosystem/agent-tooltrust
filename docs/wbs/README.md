# WBS — Agent ToolTrust

Work Breakdown Structure — milestone plans and task breakdowns for all versions.

> **GitHub Issues:** 122 issues created across 4 milestones. All issues link back to these WBS files.
> **Milestones:** [v0.1.0 (#1-76)](https://github.com/deghosal-2026/agent-tooltrust/milestone/1) | [v0.2.0 (#77-104)](https://github.com/deghosal-2026/agent-tooltrust/milestone/2) | [v0.3.0 (#105-117)](https://github.com/deghosal-2026/agent-tooltrust/milestone/3) | [v0.4.0 (#118-122)](https://github.com/deghosal-2026/agent-tooltrust/milestone/4)

| File | Milestones | Version | GitHub Issues | Status |
|------|-----------|---------|---------------|--------|
| [wbs-v0.1.0-part1-engine.md](wbs-v0.1.0-part1-engine.md) | M1 (Core Engine) + M2 (Policy Manager) | v0.1.0 | #12-23 (M1), #1-11 (M2) | Approved ✅ |
| [wbs-v0.1.0-part2-audit-adapters.md](wbs-v0.1.0-part2-audit-adapters.md) | M3 (Audit Logger) + M4 (Integration Adapters) | v0.1.0 | #24-43 (M3-M4) | Approved ✅ |
| [wbs-v0.1.0-part3-cli-mcp.md](wbs-v0.1.0-part3-cli-mcp.md) | M5 (MCP Server) + M6 (CLI + Explanation) | v0.1.0 | #44-57 (M5-M6) | Approved ✅ |
| [wbs-v0.1.0-part4-field-ship.md](wbs-v0.1.0-part4-field-ship.md) | M7 (Field Tests) + M8 (Demo + Hardening + Ship) | v0.1.0 | #58-76 (M7-M8) | Approved ✅ |
| [wbs-v0.2-v0.3.md](wbs-v0.2-v0.3.md) | M9-M16 (v0.2 + v0.3 milestones) | v0.2.0, v0.3.0 | #77-104 (M9-M12), #105-118 (M13-M16) | Approved ✅ |
| [wbs-v0.4.md](wbs-v0.4.md) | M17-M18 (v0.4 milestones) | v0.4.0 | #119-122 (M17-M18) | Approved ✅ |

## Issue Summary

| Milestone | Version | Issues | Range |
|-----------|---------|--------|-------|
| M1-M2 | v0.1.0 Engine + Policy | 23 | #1-23 |
| M3-M4 | v0.1.0 Audit + Adapters | 20 | #24-43 |
| M5-M6 | v0.1.0 MCP + CLI | 14 | #44-57 |
| M7-M8 | v0.1.0 Field + Ship | 19 | #58-76 |
| M9-M12 | v0.2.0 Session + Security | 28 | #77-104 |
| M13-M16 | v0.3.0 Output + Tamper | 13 | #105-117 |
| M17-M18 | v0.4.0 Governance | 5 | #118-122 |
| **Total** | | **122** | #1-122 |

## v0.1.0 Milestone Summary

> **Status: Approved ✅** — All 18 milestones mapped to PRD features.

| M# | Name | Features | CUJs | Exit gate |
|----|------|----------|------|-----------|
| M1 | Core Engine | F-01-F-05, F-07, F-12, F-20-F-22, F-89(P0) | CUJ 1, 9, 11 | Code review, >95% coverage, lint strict, 40-cell matrix — **COMPLETE ✅ (commit `4649365`)** |
| M2 | Policy Manager | F-06, F-10, F-60, F-63, F-65-F-67, F-70, F-72 | CUJ 4, 8 | Code review, >95% coverage, lint strict, OPA parity — **COMPLETE ✅ (commit `1b1c4dd`)** |
| M3 | Audit Logger | F-30, F-31, F-33 | CUJ 6 | 3 sinks verified, CLI audit working |
| M4 | Integration Adapters | F-40-F-42 | CUJ 2 | 6 adapters pass integration tests |
| M5 | MCP Server | F-11 | CUJ 2 | Server starts, tools work, audit emitted |
| M6 | CLI + Explanation | F-23, F-51, F-52, F-74, F-85 | CUJ 3, 8 | All CLI commands working, quickstart verified |
| M7 | Field Tests | F-75 | CUJ 7, 11 | 10-agent sweep, 300 assertions pass |
| M8 | Demo + Hardening + Ship | F-50, F-91 | All P0 CUJs | PyPI v0.1.0, OpenSSF Silver, OWASP 5/10 |

## Exit Gate Checklist (Every Milestone)

- [ ] Code review passed on all files
- [ ] Every `.py` file has module-level and function-level docstrings with Args/Returns/Raises
- [ ] Test coverage >95% (`pytest --cov=agent_tooltrust --cov-fail-under=95`)
- [ ] Ruff clean: `ruff check . --select ALL` → 0 errors
- [ ] Mypy strict clean: `mypy --strict` → 0 errors