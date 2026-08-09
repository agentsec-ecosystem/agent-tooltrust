# WBS — Agent ToolTrust v0.4.0

> **Milestones covered:** v0.4.0 (M17-M18)
> **PRD:** [PRD.md](../design/PRD.md)

---

## v0.4.0 — Governance Reports, Distributed Sync

**Goal:** Fleet-scale operational maturity. Governance reports for compliance, distributed policy sync, OpenSSF Gold aspirational.

---

### Milestone 17: Governance Reports + Policy Sync

**PRD coverage:** Governance reports (roadmap), distributed policy sync (OPAL)

#### M17 Task Checklist

| # | Task | Exit criteria |
|---|------|---------------|
| 1 | Governance report generator: `tooltrust report --type compliance --period 2026-Q3`. Aggregates decisions by agent, tool category, risk level, approval rates | Report generates valid PDF/HTML |
| 2 | Decision analytics: risk heatmap per agent, denial rate trends, escalation approval SLA tracking, policy exception tracking | Analytics dashboard or CLI report |
| 3 | Policy sync via OPAL: ToolTrust PDP instances subscribe to policy updates. Policy change → push to all instances within seconds | 3 PDP instances, change policy → all three updated within 5s |
| 4 | Fleet deployment guide: how to run ToolTrust as a fleet PDP service with policy sync, audit aggregation, and monitoring | Guide covers: deployment topology, OPAL config, monitoring, scaling |
| 5 | Policy rollback: versioned policy store; `tooltrust policy rollback --version 1.2.0` | Rollback restores policy; all instances updated |

#### M17 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] Governance report generates valid compliance output
- [ ] Policy sync pushes to all instances within 5s
- [ ] Policy rollback works correctly
- [ ] Fleet deployment guide complete

---

### Milestone 18: OpenSSF Gold + v0.4.0 Ship

| # | Task | Exit criteria |
|---|------|---------------|
| 1 | OpenSSF Gold assessment: verify all Gold criteria. 2+ independent reviewers (community requirement) | Gold badge or documented path to Gold |
| 2 | v0.4.0 field test sweep: full regression on all 10 agents | Field test green |
| 3 | Hardening + ship: code review, >95% coverage, lint clean, PyPI v0.4.0, GitHub release | `pip install agent-tooltrust==0.4.0` |

#### M18 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] OpenSSF Gold criteria assessed
- [ ] Full field test sweep green
- [ ] PyPI v0.4.0 published
- [ ] GitHub release created

---

## Cross-Milestone Success Metrics (All Versions)

| Metric | v0.1 Target | v0.2 Target | v0.3 Target | v0.4 Target |
|--------|-------------|-------------|-------------|-------------|
| **PRD features shipped** | 35+ P0 features | 20+ P1 features | 8+ P2 features | 3+ P3 features |
| **CUJs covered** | 1-9, 11 (10 CUJs) | 10 (escalation) | All 11 | All 11 |
| **Framework adapters** | 6 adapters v0.1 | — | — | — |
| **Field test agents** | 10 agents | 10 agents (regression) | 10 agents (regression) | 10 agents (regression) |
| **Decision matrix** | 300 assertions | 350+ assertions | 400+ assertions | 400+ assertions |
| **Test coverage** | >95% | >95% | >95% | >95% |
| **OWASP Agentic Top 10** | 5/10 | 9/10 | 10/10 | 10/10 |
| **OpenSSF Badge** | Silver | Silver | Silver+ | Gold aspirational |
| **ToolTrust Baseline** | Essential | Hardened | Certified | Certified |
| **Stars target** | 25+ | 50+ | 100+ | 150+ |