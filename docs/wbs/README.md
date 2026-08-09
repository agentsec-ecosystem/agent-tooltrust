# WBS — Agent ToolTrust

Work Breakdown Structure — milestone plans and task breakdowns for all versions.

| File | Milestones | Version | Status |
|------|-----------|---------|--------|
| [wbs-v0.1.0-part1-engine.md](wbs-v0.1.0-part1-engine.md) | M1 (Core Engine) + M2 (Policy Manager) | v0.1.0 | Draft |
| [wbs-v0.1.0-part2-audit-adapters.md](wbs-v0.1.0-part2-audit-adapters.md) | M3 (Audit Logger) + M4 (Integration Adapters) | v0.1.0 | Draft |
| [wbs-v0.1.0-part3-cli-mcp.md](wbs-v0.1.0-part3-cli-mcp.md) | M5 (MCP Server) + M6 (CLI + Explanation) | v0.1.0 | Draft |
| [wbs-v0.1.0-part4-field-ship.md](wbs-v0.1.0-part4-field-ship.md) | M7 (Field Tests) + M8 (Demo + Hardening + Ship) | v0.1.0 | Draft |
| [wbs-v0.2-v0.3.md](wbs-v0.2-v0.3.md) | M9-M16 (v0.2 + v0.3 milestones) | v0.2.0, v0.3.0 | Draft |
| [wbs-v0.4.md](wbs-v0.4.md) | M17-M18 (v0.4 milestones) | v0.4.0 | Draft |

## v0.1.0 Milestone Summary

> **Status: Approved ✅** — All 18 milestones mapped to PRD features.

| M# | Name | Features | CUJs | Exit gate |
|----|------|----------|------|-----------|
| M1 | Core Engine | F-01-F-05, F-07, F-12, F-20-F-22, F-89(P0) | CUJ 1, 9, 11 | Code review, >95% coverage, lint strict, 40-cell matrix |
| M2 | Policy Manager | F-06, F-10, F-60, F-63, F-65-F-67, F-70, F-72 | CUJ 4, 8 | Code review, >95% coverage, lint strict, OPA parity |
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