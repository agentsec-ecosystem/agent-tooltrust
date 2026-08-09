# WBS — Agent ToolTrust v0.2.0 + v0.3.0

> **Milestones covered:** v0.2.0 (M9-M12) + v0.3.0 (M13-M16)
> **PRD:** [PRD.md](../design/PRD.md) | **Architecture:** [architecture-v0.1.0.md](../architecture/architecture-v0.1.0.md)

---

## v0.2.0 — Session State, Security Depth, Operational Maturity

**Goal:** Ship the session/context model (Omnigent/ConLeash differentiator), argument-level validation, escalation round-trip, tool security scanning, CI policy testing, SWE-bench integration. **OWASP 9/10, ToolTrust Hardened baseline.**

---

### Milestone 9: Session/Context State + Argument Validation

**PRD coverage:** F-08, F-08a, F-08b, F-08c, F-08d, F-80
**CUJs covered:** OWASP A07, session-state differentiator

#### M9 Task Checklist

| # | Task | Feature ID | Exit criteria |
|---|------|------------|---------------|
| 1 | `SessionState` dataclass: risk_score (cumulative), tool_call_count, budget_remaining, consent_scopes, created_at | F-08 | Typed, serializable, replayable from audit |
| 2 | Cumulative risk accumulator: each call's risk score added to session total. `session.risk_score += call.risk_score` | F-08a | Test: 5 low-risk calls → below threshold; 6th call (same risk) → crosses → escalate |
| 3 | Per-session budgets: token_budget, call_budget, cost_budget. Engine checks before each call. Budget exceeded → deny("budget_exceeded") | F-08b | Budget tests: token ceiling hit → deny; call count ceiling hit → deny |
| 4 | Consent scope tracking: `session.grant_scope(tool, env, data_class)`. Calls within scope → auto-allow. Crosses scope → escalate | F-08c | Test: scoped write auto-permits; write in different project → escalate (ConLeash pattern) |
| 5 | Session replay: `tooltrust audit session --replay <id>` reconstructs session state from audit entries | F-08d | Replay produces same cumulative risk score at each call |
| 6 | Argument-level validation registry: `@tooltrust.arg_validator("regex", pattern=...)`, `@tooltrust.arg_validator("range", min=..., max=...)`, `@tooltrust.arg_validator("path", root=...)`, `@tooltrust.arg_validator("url", scheme=...)` | F-80 | Each validator independently testable |
| 7 | Integration tests: session risk accumulation across real agent session; budget enforcement; consent scope boundaries; argument validation on SQL/URL/path tools | — | 30+ integration scenarios |

#### M9 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] Session risk accumulator correctly escalates after threshold
- [ ] Budget enforcement denies when ceilings hit
- [ ] Consent scope correctly detects boundary crossings (ConLeash lattice pattern)
- [ ] Argument validators pass for valid inputs, deny for invalid
- [ ] Session replay produces correct cumulative state from audit

---

### Milestone 10: Escalation Round-Trip + Security Scanning

**PRD coverage:** F-09, F-23, F-32, F-81, F-83, F-90
**CUJs covered:** CUJ 10 (escalation round-trip), OWASP A05 (supply chain)

#### M10 Task Checklist

| # | Task | Feature ID | Exit criteria |
|---|------|------------|---------------|
| 1 | EscalationManager: create escalation, track status (pending/approved/denied/expired), bind to action_identity, enforce TTL | F-09, F-90 | Test: approve → action executes; deny → agent receives deny; expired → treated as deny |
| 2 | `tooltrust approve <id>` and `tooltrust deny <id>` CLI commands | F-90 | CLI approves/denies pending escalations; records approver + timestamp |
| 3 | Action-identity binding: escalate is bound to hash(tool, action, args). Replay with different args → deny("action_identity_mismatch") | F-09 | Test: approve call X with args A; replay with args B → denied |
| 4 | Tool definition scanner: `tooltrust scan --tool <tool_def>` — regex patterns for hidden instructions, typosquatting, adversarial patterns in tool descriptions | F-81 | Scanner detects: injected system prompts, Unicode lookalikes in tool names, hidden instructions |
| 5 | Discovery-time tool hiding: policy can mark tools as `hidden: true` for specific agent classes. Engine returns capability-filtered tool list | F-83 | Test: admin agent sees all tools; read-only agent sees subset; hidden tools never appear |
| 6 | Full CUJ 10 end-to-end test: agent escalates → human approves → agent resumes → audit records entire chain | — | Complete HITL flow verified |
| 7 | OWASP A05 verification: scanner correctly flags 10 known-adversarial tool definitions | F-81 | 10/10 adversarial definitions caught |

#### M10 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] Escalation round-trip works end-to-end (agent → escalate → human → approve → resume)
- [ ] Action-identity binding prevents replay attacks
- [ ] Tool scanner catches 10/10 adversarial definitions
- [ ] Discovery-time tool hiding correctly filters per agent class
- [ ] Approval TTL enforced (expired → deny)

---

### Milestone 11: CI Policy Testing + Rate Limits + SWE-Bench

**PRD coverage:** F-43, F-44, F-61, F-62, F-64, F-71, F-73, F-84, F-86, F-89(P1), F-92
**CUJs covered:** CUJ 5 (extend tooltrust), OWASP A06 part 2

#### M11 Task Checklist

| # | Task | Feature ID | Exit criteria |
|---|------|------------|---------------|
| 1 | CI policy regression suite: `tooltrust test` replays golden fixtures (tool/env/data → expected decision). Drift detection on PR | F-84 | Test: change policy → CI catches unexpected decision change |
| 2 | Policy pack format finalization: `tools.yaml` + `tests.yaml` schema, `tooltrust pack validate`, `tooltrust pack test` | F-61 | Pack validates; pack tests pass; one-page contribution guide |
| 3 | Custom risk function registry: `@tooltrust.risk_dimension("my_dim")` decorator. Registered functions participate in scoring | F-62 | Custom dim adds to weighted sum; testable in isolation |
| 4 | Rule composition operators: `and`, `or`, `not` in policy rules. Sub-entity grouping | F-64 | Tests: combined rules produce correct decisions |
| 5 | Rate/burst limits: per-session call rate (calls/sec) and burst ceiling | F-86 | Test: rate-limit kicks in after threshold; burst allows short spikes |
| 6 | Replay-attempt detection: same escalation_id reused → deny | F-89(P1) | Test: approve esc_1; replay esc_1 with different call → denied |
| 7 | SWE-Bench integration: ToolTrust wrapper for SWE-bench coding agent runs. Tool policy enforced during benchmark; decision trace per task | F-92 | SWE-bench task run with ToolTrust; all tool calls logged; violations flagged |
| 8 | HTTP /authorize service: FastAPI endpoint accepting JSON tool call, returning Decision | F-43 | POST /authorize → valid Decision JSON |
| 9 | OTel spans: decision evaluation spans exported. Attributes: tool, action, env, decision, reason_code, latency | F-44 | Spans appear in OTel collector |
| 10 | Session rate limit enforcement + burst test | F-86 | Rate limiter correctly throttles |
| 11 | Case studies README section: "Understanding Criticality" with 5 real-world risk scenarios and ToolTrust decisions | F-73 | README section explains risk ladder with examples |
| 12 | Policy test runner: `tooltrust test --policy tooltrust.yaml --fixtures tests.yaml` | F-71 | CI runs policy tests on every PR |

#### M11 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] CI policy regression suite catches drift (intentional break test)
- [ ] Pack format documented + one external pack submitted as PR
- [ ] SWE-bench integration runs ToolTrust on 5 benchmark tasks
- [ ] HTTP /authorize endpoint returns correct Decision
- [ ] OTel spans visible in collector
- [ ] Rate limits + replay detection verified

---

### Milestone 12: v0.2.0 Hardening + Ship

**PRD coverage:** OWASP 9/10, ToolTrust Hardened baseline
**Ship target:** OWASP 9/10 coverage, ToolTrust Hardened baseline passes, field test sweep on v0.2 additions

#### M12 Task Checklist

| # | Task | Exit criteria |
|---|------|---------------|
| 1 | v0.2.0 field test sweep: run v0.1 matrix + new v0.2 scenarios (session risk escalation, argument validation bypass, escalation round-trip, tool scanning adversarial) on all 10 agents | Field test report: v0.2 scenarios pass on all agents |
| 2 | OWASP coverage audit: verify 9/10 risks covered. Remaining: A03 (data leakage — partial, needs output inspection in v0.3) | SECURITY.md updated with 9/10 coverage map |
| 3 | ToolTrust Hardened baseline: run `tooltrust baseline check hardened` → all items pass | Hardened checklist verified |
| 4 | Hardening pass: code review, >95% coverage, ruff strict, mypy strict on all new code | Lint + coverage gates pass |
| 5 | CHANGELOG v0.2.0, release notes, PyPI publish | `pip install agent-tooltrust==0.2.0` |
| 6 | GitHub release v0.2.0 | Release visible |

#### M12 Exit Gate

- [ ] Code review, >95% overall coverage, ruff clean, mypy strict
- [ ] v0.2 field test sweep green on all 10 agents
- [ ] OWASP 9/10 verified
- [ ] ToolTrust Hardened baseline passes
- [ ] PyPI v0.2.0 published
- [ ] Release notes + CHANGELOG committed
- [ ] GitHub release created

---

## v0.3.0 — Output Inspection, Dispatcher Safety, Tamper-Evident Audit

**Goal:** Close the remaining defense-in-depth layers. **OWASP 10/10, ToolTrust Certified aspirational.**

---

### Milestone 13: Output/Response Inspection + Dispatcher Bypass Safety

**PRD coverage:** F-82, F-87
**OWASP coverage:** A03 (data leakage — full)

#### M13 Task Checklist

| # | Task | Feature ID | Exit criteria |
|---|------|------------|---------------|
| 1 | Output inspector: `@tooltrust.output_inspector`. Scans tool results for secrets (key patterns), PII (regex + classifier), injected instructions (heuristic patterns) before returning to model | F-82 | Inspector catches: "sk-..." API keys, SSN patterns, "ignore previous instructions" payloads in tool results |
| 2 | Redaction config: `output_inspection` section in tooltrust.yaml. Patterns, severity, action (redact/warn/block) | F-82 | Config-driven; patterns overridable |
| 3 | Dispatcher parser: `engine/dispatch.py` — parse `bash`, `call_aws`, `http` tool args to extract canonical (tool_name, action, args). Evaluate against the same policy as direct calls | F-87 | Test: `bash: "git push --force"` when git.push is denied → denied; `bash: "git status"` when git.read is allowed → allowed |
| 4 | Dispatcher unknowns: can't parse → deny("unparseable_dispatcher_input"). Don't guess | F-87 | Test: malformed bash → deny; valid but unknown sub-command → deny |
| 5 | Integration tests: output redaction on secrets, PII, injection payloads; dispatcher parsing on bash/aws/http tools | — | 20+ integration scenarios |

#### M13 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] Output inspector catches secrets, PII, and injection payloads
- [ ] Dispatcher parser correctly evaluates smuggled tool calls
- [ ] OWASP A03 marked "covered v0.3"

---

### Milestone 14: Child-Agent Delegation + Tamper-Evident Audit

**PRD coverage:** F-34, F-88
**OWASP coverage:** A08 (multi-agent coordination)

#### M14 Task Checklist

| # | Task | Feature ID | Exit criteria |
|---|------|------------|---------------|
| 1 | Child-agent delegation: `engine.delegate(child_agent_id, parent_session, scope_subset)`. Verifies child scope ⊆ parent scope | F-88 | Test: parent with scope [a,b,c] delegates child with scope [a,b] → allowed; child with scope [a,b,d] → denied |
| 2 | Delegation audit trail: every delegation recorded in audit with parent_agent_id, child_agent_id, scope | F-88 | Audit shows delegation chain (parent → child → call) |
| 3 | Tamper-evident audit chain: hash-chain over decision log entries. `tooltrust audit verify` proves log integrity | F-34 | Test: verify clean log → PASS; modify one entry → verify FAIL with entry index |
| 4 | Hash-chain format: each entry commits to prior entry's hash. ed25519 signing key for root | F-34 | Root signed; chain verifiable; key rotation story documented |
| 5 | Integration tests: child delegation scope enforcement; audit chain verification on 1K-entry log | — | Delegation + verification tests pass |

#### M14 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] Child delegation correctly enforces scope subset invariant
- [ ] Tamper-evident audit chain verifiable and falsifiable
- [ ] OWASP A08 marked "covered v0.3"

---

### Milestone 15: Policy Packs Catalog + AgentControlPlane Integration

**PRD coverage:** F-53, F-61(packs catalog)

#### M15 Task Checklist

| # | Task | Exit criteria |
|---|------|---------------|
| 1 | Policy packs registry: community-submitted packs listed in `packs/` directory with metadata (author, domains, tool count, tests_ passing, last_updated) | 5+ packs in catalog |
| 2 | AgentControlPlane integration: ToolTrust as a PDP service for the AgentControlPlane fleet manager. AgentControlPlane queries ToolTrust for per-agent permissions | Integration test: AgentControlPlane → ToolTrust → Decision back |
| 3 | MCP-Data integration: ToolTrust decisions about data-access tools queried through MCP-Data connector | Integration test: MCP-Data → ToolTrust → per-data-source authorization |
| 4 | Optional local dashboard (React): `tooltrust serve --ui` starts a local dashboard showing recent decisions, risk heatmap, escalation queue | Dashboard renders decision history |

#### M15 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] 5+ community packs in catalog
- [ ] AgentControlPlane + MCP-Data integration tests pass
- [ ] Local dashboard renders correctly

---

### Milestone 16: v0.3.0 Hardening + Ship

**PRD:** OWASP 10/10, ToolTrust Certified aspirational

| # | Task | Exit criteria |
|---|------|---------------|
| 1 | OWASP 10/10 final audit: all 10 risks covered. SECURITY.md published | 10/10 coverage map verified |
| 2 | ToolTrust Certified baseline: run `tooltrust baseline check certified` → all items pass (Hardened + tamper-evident + output inspection + external review ready) | Certified checklist verified |
| 3 | v0.3.0 field test sweep: all scenarios (v0.1 + v0.2 + v0.3) on all 10 agents | Full regression field test green |
| 4 | Hardening + ship: code review, >95% coverage, lint clean, PyPI v0.3.0, GitHub release | `pip install agent-tooltrust==0.3.0` |

#### M16 Exit Gate

- [ ] Code review, >95% coverage, ruff clean, mypy strict
- [ ] OWASP 10/10 verified
- [ ] Certified baseline passes
- [ ] Full field test sweep green
- [ ] PyPI v0.3.0 published
- [ ] GitHub release created