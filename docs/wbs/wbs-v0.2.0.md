# WBS — Agent ToolTrust v0.2.0

> **Milestones covered:** v0.2.0 (M9-M18) — remaining features after v0.1.0 pull-forward
> **PRD:** [PRD.md](../design/PRD.md) | **Architecture:** [architecture-v0.1.0.md](../architecture/architecture-v0.1.0.md)
> **Shipped in v0.1.0:** Session state (#77-80), arg validators (#82), tool scanner (#87), CI regression (#90), custom risk dims (#92), rate limits (#94), SWE-bench (#96), OTel (#98), case studies (#99), OWASP 9/10 audit (#102), output inspector (#105), tamper-evident audit (#109), governance reports (#118) — see M19-M23.

---

## M9 — Session State (remaining)

| # | Task | Feature ID | Issue |
|---|------|------------|-------|
| 1 | Session replay from audit: `tooltrust audit session --replay <id>` | F-08d | #81 |

### M9 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] Session replay produces correct cumulative state from audit
- [ ] M9 Exit Gate #83

---

## M10 — Escalation Round-Trip + Security

| # | Task | Feature ID | Issue |
|---|------|------------|-------|
| 1 | EscalationManager: create, track, approve/deny/expire, TTL | F-09, F-90 | #84 |
| 2 | `tooltrust approve <id>` / `tooltrust deny <id>` CLI | F-90 | #85 |
| 3 | Action-identity binding: escalate bound to hash(tool, action, args) | F-09 | #86 |
| 4 | Tool hiding: policy marks tools `hidden: true` per agent class | F-83 | #88 |
| 5 | CUJ 10 end-to-end test: escalate → approve → resume | — | #89 |

### M10 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] Escalation round-trip works end-to-end
- [ ] M10 Exit Gate #89

---

## M11 — CI, Packs, Composition

| # | Task | Feature ID | Issue |
|---|------|------------|-------|
| 1 | Policy pack format: `tools.yaml` + `tests.yaml` | F-61 | #91 |
| 2 | Rule composition: `and`, `or`, `not` operators | F-64 | #93 |
| 3 | Replay-attempt detection: same escalation_id reused → deny | F-89(P1) | #95 |
| 4 | HTTP /authorize service: FastAPI endpoint | F-43 | #97 |
| 5 | M11 Exit Gate | — | #100 |
| 6 | v0.2 field test sweep | — | #101 |
| 7 | ToolTrust Hardened baseline | — | #103 |
| 8 | v0.2 hardening + ship | — | #104 |

### M11 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] Pack format documented
- [ ] HTTP /authorize returns correct Decision
- [ ] Replay detection verified
- [ ] Field test sweep green

---

## M12 — Output & Dispatcher Safety

| # | Task | Feature ID | Issue |
|---|------|------------|-------|
| 1 | Dispatcher parser: parse `bash`, `aws`, `http` args to canonical form | F-87 | #106 |
| 2 | Dispatcher unknowns → deny, don't guess | F-87 | #106 |
| 3 | M12 Exit Gate | — | #107 |

---

## M13 — Child-Agent Delegation

| # | Task | Feature ID | Issue |
|---|------|------------|-------|
| 1 | Child-agent delegation: `engine.delegate()` scope subset invariant | F-88 | #108 |
| 2 | M13 Exit Gate | — | #110 |

---

## M14 — Policy Packs + Integrations

| # | Task | Feature ID | Issue |
|---|------|------------|-------|
| 1 | Policy packs catalog: community packs in `packs/` directory | F-61 | #111 |
| 2 | AgentControlPlane + MCP-Data integrations | — | #112 |
| 3 | M14 Exit Gate | — | #113 |

---

## M15 — OWASP 10/10 + Certified Baseline

| # | Task | Feature ID | Issue |
|---|------|------------|-------|
| 1 | OWASP 10/10 final audit | — | #114 |
| 2 | ToolTrust Certified baseline | — | #115 |
| 3 | v0.3 field test sweep (full regression) | — | #116 |
| 4 | Ship: PyPI + GitHub release | — | #117 |

---

## M16 — Fleet Governance

| # | Task | Feature ID | Issue |
|---|------|------------|-------|
| 1 | Distributed policy sync — OPAL | — | #119 |
| 2 | Fleet deployment guide | — | #120 |

---

## M17 — OpenSSF Gold

| # | Task | Feature ID | Issue |
|---|------|------------|-------|
| 1 | OpenSSF Gold assessment | — | #121 |

---

## M18 — v0.2.0 Ship

| # | Task | Issue |
|---|------|-------|
| 1 | Hardening + ship | #122 |

## Cross-Version Success Metrics

| Metric | v0.1 Target | v0.2 Target |
|--------|-------------|-------------|
| PRD features shipped | 35+ P0 + 13 enhancements | 20+ P1/P2 features |
| CUJs covered | 1-9, 11 (10 CUJs) | 10 (escalation) |
| Framework adapters | 6 adapters | — |
| Test coverage | >95% | >95% |
| OWASP Agentic Top 10 | 9/10 | 10/10 |
| OpenSSF Badge | Silver | Gold |
| ToolTrust Baseline | Essential | Certified |