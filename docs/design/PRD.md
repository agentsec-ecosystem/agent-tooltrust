# Agent ToolTrust — Product Requirements Document (PRD)

**Version:** 0.1 (Draft for scoping)
**Date:** 2026-08-08
**Status:** Draft
**Owner:** Debashish Ghosal
**Repo:** `deghosal-2026/agent-tooltrust` (private → OSS)
**Package:** `agent-tooltrust`

---

## 1. Executive Summary

Agent ToolTrust is a **contextual risk and permission engine for tool-using AI agents**. Before an agent's tool call executes, ToolTrust scores the action across risk dimensions (tool type, action class, environment, data sensitivity, agent/principal identity) and returns one of four decisions — **allow, audit, escalate (human approval), or deny** — each with a human-readable explanation artifact and a machine-recorded audit trail.

The insight that justifies the project: **flat allow-lists are a reachability control, not an authorization decision.** The same tool is harmless in staging and dangerous in production; the same read is fine on public docs and risky on customer data. Tool permissions that ignore this context force teams to choose between "over-privileged agents" (dangerous) and "approve-everything UX" (useless). ToolTrust gives a third option: deterministic, explainable, context-aware decisions with repeatable policy.

This PRD defines **why** the product exists (business rationale), **who** it serves, **what** it delivers (CUJs — critical user journeys — and the feature set), and how it deliberately pursues five quality bets: **platform-neutral compatibility, ease of use, ease of integration, readability of decisions/criticality, and extensibility.** It reflects community research into the current landscape (Section 4) and intentionally positions ToolTrust as the adoption-first, learnable implementation of this pattern.

**Scoping snapshot (decided 2026-08-08):** Python library + MCP client wrapper + a ToolTrust MCP server exposing `evaluate`; full 4-state decision set (allow / audit / escalate / deny); JSON/YAML policy with OPA/Rego parity; adapters for all major frameworks (LangGraph, PydanticAI, OpenAI SDK, CrewAI, raw Python, MCP); optional non-authoritative LLM explanations (off by default); Postgres-ready audit sink from day one.

---

## 2. Why (Business Requirements)

### 2.1 The market context

- MCP (Model Context Protocol) standardizes *how* agents discover and invoke tools, but it **does not define a control point** for whether a call should run. Teams connecting agents to real systems (GitHub, cloud, databases, payment rails) face a "gap between the model decided the call and the call was verified as permitted."
- Only an estimated **18% of MCP server deployments implement any access scoping** for tool permissions (NHI research, State of MCP Server Security 2025); reports put **~80% of orgs admitting agent actions beyond intended scope**.
- OWASP Agentic AI Top 10 classifies agent tool misuse as a first-class risk; leading vendors (Microsoft AGT, OPA/Rego tooling) have converged on the **Policy Decision Point (PDP)** pattern — a deterministic engine *outside* the model that answers, per call: *"may this agent call this tool with these arguments, in this context, now?"*
- Safe autonomy is consistently cited as the central blocker to enterprise agent adoption. "Bounded autonomy" and "safe tool use" are named repeatedly as key enterprise blockers.

### 2.2 The pain we remove

| Status quo (today) | Pain |
|---|---|
| Allow/deny server allowlists | Reachability only, no semantic decision |
| "Ask me every time" prompts | Permission fatigue → users auto-approve "durable grants" that silently authorize privilege escalation |
| System-prompt instructions | Rules live in natural text the model can be steered away from — a suggestion, not enforcement |
| Rolling own checks inline in app code | Logic scattered, untested, no audit trail, no explanations |
| Vendor gateways (MS AGT etc.) | Lock-in, heavy, hard to learn, no control over taxonomy & defaults |

### 2.3 Why it matters for the pilot & OSS goals
- **For operators:** deterministic, auditable control plane; defendable in compliance review ("show the decision log").
- **For individual agents** users: permissive-by-default tool access with escalating guardrails; agent safely never sees tools it can't call.
- **For the solo-build OSS portfolio:** a Tier-1, high-engagement problem with strong article series (safe autonomy, governor) and a real access-control gap.

---

## 3. What We Are Building (Core Value)

**A pre-execution, deterministic policy engine for agent tool calls that:**

1. **Normalizes** any tool call (MCP, LangGraph, PydanticAI, OpenAI SDK, CrewAI, raw Python) into a canonical action shape.
2. **Scores** risk across five dimensions — tool category, action class, environment, data sensitivity, agent (and principal to come). Session (context) is an input available from day one.
3. **Decides** one of four outcomes per call: **allow, audit (allow + enhanced logging), escalate (human approval), or deny**.
4. **Explains** the decision (why + which factor drove it + criticality + what to do next) in plain language, with optional LLM-generated prose on request.
5. **Audits** every decision to an append-ony log (JSONL / SQLite / Postgres sink) with the policy version.

**Delivery modes (v0.1):**
- **Library** — import `agent_tooltrust`, call `engine.evaluate(...)` in-process; add a decorator/context-manager.
- **MCP client wrapper** — intercept tool calls from MCP-based agents before they reach the server.
- **MCP server** — ToolTrust exposes its own MCP tools (`evaluate`, `explain`) so any agent can ask "is this call authorized?" through its own tool stack.
- (v0.2+) HTTP `/authorize` service for non-Python hosts.

### Design principle (from research)
- **Deterministic by default; the model does not vote.** The policy engine decides. The LLM at most is an *optional* advisor that can narrow scope (flag "arguable," escalate), never widen it. This is the strongest shared conclusion across Permit0, NEXUS, ConLeash, MSFT AGT, and the OPA ecosystem.
- **Context is not just the current call** — it includes what the session has done so far. Omnigent and ConLeash both show that accumulated risk, consent scope, and budgets make the *same* call behave differently early vs. late in a workflow ("the email your sales-org agent sends first thing is safe; the one it sends after reading a customer's confidential folder is not"). This session-state model (F-08 family) is a stated differentiator and a v0.2 commitment.
- **An audit you can't prove is half an audit.** Signed/tamper-evident decision logs (the Permit0 pattern, F-34) turn "we log decisions" into "we can cryptographically show the log is unedited" — the difference that survives a compliance review.

### Terminal-state definition ("done")
A working `v0.1.0` that can be installed with `pip install agent-tooltrust`, integrated into an agent loop in under ~15 lines, evaluate a matrix of realistic safe/risky/approval-needed tool calls with correct outcomes, emit explanations, and log a searchable audit trail.

---

## 4. Landscape & Identity (from research)

| Project | What it does | Decision | Our wedge |
|---|---|---|---|
| **Permit0** | Rust policy engine; 22-domains/159-verbs taxonomy; risk seeding; signed audit | allow/deny/human | Heavyweight, requires their taxonomy + Rust runtime; less teachable |
| **Microsoft AGT** | OSS governance between MCP client & servers: Rego/OPA, identity four-tier, response class | per-call rules | Opinionated identity layer (SPIFFE) — heavy; not a small self-contained library |
| **Vercel AI SDK `@ai-sdk/policy-opa`** | OPA-backed `toolApproval` callback, wraps plugin | allow/deny/requires-approval | JS-only; couples to one framework's approval API |
| **ConLeash** | Client-side consent middleware, risk lattice (scopebound) | auto-permit / escalate | Research prototype; UX-focused but not a production OSS library |
| **OPA/Rego + gateway** (self-built) | Stand up OPA + write Rego | allow/deny | You write the Rego, you run the PDP, maintain data sync — high effort |
| **NEXUS** (research) | Plan-level safety monitor with risk score | allow/block/confirm/revision | Research; needs structured plans, not per-call gating |

### 4.1 ToolTrust vs the crowd
1. **Python-first library, framework-agnostic, works with a routing gateway:** one codebase the *whole ecosystem* can import (LangGraph, OpenAI, PydanticAI, CrewAI, raw, MCP), rather than a per-framework shim or a heavyweight gateway service.
2. **Local-first, learnable default posture:** a default taxonomy, a sensible concern model and risk ladder, working examples from day one — you get "a working policy on install" narrative.
3. **Explanation as a first-class API:** not just a verdict, but `why`, `which factor`, `suggested action`, and a readable audit record (research consistently confirms that black-box denials get bypassed).
4. **Explicit, small extension surface:** adapters, policy sets, and risk functions that a contributor can write in minutes and submit as OSS (low-barrier to adopt).

---

## 5. Target Users

**Primary persona — Agent Platform Engineer / DevOps** builds or operates internal agent infrastructure (MCP gateways, sandboxed agent runtimes), needs to grant agents meaningful tool access without dangerous over-permission.

**Secondary personas:**
- **Security/Governance:** want defense for "can you prove your agent did not touch data outside its tenant?" via structured decision logs.
- **Application / AI engineer on agentic features:** wants a one-size-fits-all way to keep sensitive data, write, and shell wrappers from running amok without building their own risk model.
- **OSS maintainers:** want safe default for their agent demos / sandboxes.

**Primary non-negotiable for all personas: minimal time-to-first-capability** → low friction install, copyable snippet, generally works, fails closed safely.

---

## 6. Critical User Journeys (CUJs)

Six condition journeys, each with an entrance gate / decision / acceptance criteria. These are the north star for the feature set.

### CUJ 1 — Evaluate one tool call ("is my integration behaving? minimal sanity check")
As an engineer, I run a small snippet that calls `evaluate()` on a realistically risk-contrasted pair of logs and see correct decisions and explanations they understand immediately.

**Acceptance criteria:**
- Safe staging read → `allow`
- Prod write toward a sensitive class → `escalate`
- Blocked action → returns `deny` with message readable by a non-expert
- All within ~15 lines of Python, no service.

### CUJ 2 — Wire into an agent framework ("integrate into my agent in one afternoon")
As an engineer, I hook ToolTrust into each major framework using an idiomatic wrapper and get safe-by-default without racing the agent:

**Acceptance criteria per framework:** the adapter intercepts every tool call before side effects; decisions flow; only allowed calls execute; a deny is surfaced to the model as a tool result (not a protocol crash); audit got it.
- LangGraph (node/`tools` dispatch, callback/tool wrapper)
- PydanticAI (tool interceptor)
- OpenAI Agents SDK (`tool_input_guardrail` / hook)
- CrewAI (tool wrapper)
- Raw Python (decorator / context manager)
- MCP client path (adapter around `tool_call`)

### CUJ 3 — Understand *why* an action was risky ("can you explain what just nearly happened?")
As a user or reviewer, when a request was escalated or denied, I can read one explanation that tells me the decision/risk, which factor (e.g. 'environment=prod' + 'action=delete'), and what it would take to get allowed.

- Every decision object carries `decision`, `criticality` (low/med/high/critical), `reason_code`, `explanation` (template-generated, human-readable), and `factors`.
- Admin can see a `tool trust report` or a summary of which risk classes were / were not consumed.
- Explanations are stored in the audit; no black-box denials.

### CUJ 4 — "Drive my allow/deny/escalate behavior with policy"
As platform lead, I express policy as data (YAML or Python): per-env rules, per-data-class, per-action; choose default posture; set approval thresholds; read outcomes.

- Declarative; a minimal rule set is committed to the repo in under 30 minutes; played with in an `evaluate` CLI/smoke test.
- Support: explicit allow/deny, referenced rule composition, and a threshold for escalation.
- `shadow mode` — run the policy and log decisions without enforcing, so the team sees where it would block before production hard-breaks (industry-recommended adoption path).

### CUJ 5 — "Extend ToolTrust" (a maintainer or operator adds an MCP tool / custom class)
As a tool platform author, I define a new tool (or whole adapter) with a declared risk profile using a small schema/format, register it in the pack, and the engine scores it — no engine core changes.

- Tool metadata schema: probably enough to define env-then-risk without any code.
- A short contribution / how-to → an open PR.
- New packs can be added & validated (`tooltrust pack validate`, `tooltrust pack test`).

### CUJ 6 — "Prove compliance: what did this agent do, and who approved?"
As a compliance interviewer, given a `session_id`, I can reconstruct the full chain of decisions: per-call decision (allow/approve/deny), msg code, timestamp, policy version, approver (for escalate), linked explanations.

---

## 7. Feature Set

> Priority scale: **P0** (v0.1.0): must have; **P1** (v0.2.0); **P2** (v0.3.0+); **P3** backlog.

### 7.1 Core engine
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-01 | `evaluate()` function: tool+op+env+data_class+agent → `Decision` | P0 | Deterministic compute |
| F-02 | Decision type: `allow` / `deny` / `escalate` / `audit` (+reason code, explanation, factors) | P0 | 4-class outcome set |
| F-03 | Risk scoring across 5 dimensions: tool type, action class, environment, data sensitivity, agent class | P0 | Additive weighted model; extends easily |
| F-04 | Fail-closed default (any unknown tool/env/input/error → deny) | P0 | Safety-critical |
| F-05 | Default taxonomy of tools/categories with sane risk defaults | P0 | Seed a practical starter |
| F-06 | Policy: per-category allow / deny lists, escalation threshold | P0 | JSON/YAML + Python configurable |
| F-07 | LLM-based advisory explanations (optional, off by default) | P0 | Non-authoritative; never grant-widening |
| F-08 | Session/context state — accumulating risk score, budgets, consent scope | P1 | Databricks Omnigent + ConLeash pattern |
| F-08a | Cumulative risk policy — actions auto-allow until session risk crosses a threshold, then escalate | P1 | Same email/send early vs late in session behaves differently |
| F-08b | Per-session budgets — token, call-count, and wall-cost ceilings | P1 | "cap a task, not a day" |
| F-08c | Consent scope / boundary tracking — auto-permit in-bounds, escalate on boundary crossing (project→other-project writes) | P1 | Directly from ConLeash's risk-lattice |
| F-08d | Session state replayable from audit — `session_id` reconstructs consent+running state for review | P1 | ties into CUJ 6 |
| F-09 | Approval workflow state (subject, artifact, expiry) — "approval is bound to an action identity" | P1-P2 | HITL; P2 full UI |
| F-10 | OPA/Rego parity — evaluate a Rego policy as a peer backend to native rules | P0 | Same decision contract, dual authoring paths |
| F-11 | ToolTrust MCP server exposing `evaluate` + `explain` tools | P0 | Agents query authorization through their own stack |

### 7.2 Explainability
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-20 | Human-readable explanation per decision (template + text factors) | P0 | |
| F-21 | Machine-readable reason codes | P0 | for SIEM / model replan |
| F-22 | Criticality ladder (none → critical) surfaced in CLI/UI & object copy | P0 | |
| F-23 | `tooltrust explain <call>` CLI | P1 | explain decisions offline |

### 7.3 Audit
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-30 | Append-only decision log (JSONL) | P0 | local file; pluggable |
| F-31 | Audit entries for allow/deny/escalate + policy + timestamp | P0 | |
| F-32 | Export/search/filter (`tooltrust audit query ...`) | P1 | |
| F-33 | Postgres sink integration | P0 | pluggable sink interface + working Postgres sink shipped |
| F-34 | Tamper-evident hash chain over the decision log | P2 | each entry commits to the prior (hash-chain / Merkle); verification command proves unedited history (Permit0 ed25519 pattern) |

### 7.4 Integration & adapters
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-40 | Python library (small public API) — `evaluate`, `module`, `registry` | P0 | same interface across hosts |
| F-41 | Adapters for: raw Python, MCP client, LangGraph, PydanticAI, OpenAI Agents SDK, CrewAI | P0 | all shipped in v0.1 |
| F-42 | MCP client wrapping (proxy its `tools/call`) | P0 | |
| F-43 | HTTP API (`/authorize`) for remote gateways / non-Python hosts | P1 | future |
| F-44 | OpenTelemetry spans/meta on decision | P1 | alignment to observability stack |

### 7.5 Packaging & UX
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-50 | PyPI package `agent-tooltrust` (well-named) | P0 | |
| F-51 | CLI: `tooltrust evaluate`, `explain`, `pack`, `audit`, `check` | P0-P1 | |
| F-52 | Quickstart + runnable examples | P0 | CUJ1/2 drivers |
| F-53 | Optional simple local dashboard (React) | P2 | out of scope v1 |

### 7.6 Policy & extensibility
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-60 | Declarative JSON/YAML policy + Python-native policy as natural options | P0 | |
| F-61 | Pack format: tools yaml, rules, tests, aliases/registry | P1 | for CUJ5 |
| F-62 | Custom risk functions (registry-based; pure functions) | P1 | |
| F-63 | OPA/Rego interop (evaluate a Rego policy as an optional backend) | P0 | parity with native JSON/YAML rules |
| F-64 | Rule composition (`and`/`or`/`not`, sub-entity — group) | P1 | |

### 7.7 Governance/dev tools
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-70 | "shadow mode" (`dry_run=True`) | P0 | **required boundary** for adoption |
| F-71 | Policy test runner (`pack test` / example) | P1 | deterministic |
| F-72 | Policy version in decision log | P0 | auditability |
| F-73 | README case studies / teaching materials per risk level | P1 | "easy to understand criticality" |
| F-74 | Optional LLM explanation endpoint (`tooltrust explain --llm`) | P0 | off by default; non-authoritative |

---

## 8. Non-Goals (v1.0)

- Full IAM / identity provider integration — later.
- Full sandboxing (execution isolation) — that's AgentSandbox; ToolTrust governs the decision, not the runtime.
- Intent classification reliance (IGAC style) — out; do not bind to cryptographic identities/SPIFFE at v1.
- Cross-session correlation and alerting — the audit exposes the data; fleet correlation is a later layer.
- Multi-tenant enterprise compliance suite (v1 is single-tenant-ish).
- Distributed policy sync (OPAL) — later.

---

## 9. Success Criteria & Metrics

Product-level success (by v1.0 & T-1):
1. **Adoption friction:** time from `pip install` → first correct `evaluate()` output < 5 min for a reader.
2. **Correctness:** "Does it get the right verdict on a 40-cell matrix of tool×env×action×class?" — target 100% on the acceptance matrix (deterministic).
3. **Explanation usefulness:** reviewers can re-explain the decision in one paragraph (no "ugh, why?"); deny reasons are `actionable` (a test in CI).
4. **Safety:** >90% of the *unsafe-and-suspicious* matrix rows → deny; 0 answered crafted `allow` for `delete` in prod with class `restricted`.
5. **Performance:** <1 ms deterministic overhead per call (target <0.5ms).
6. **Extensibility:** a contributor can add a new tool pack + test via one page of docs in one sitting (measure: docs `1 new pack` issue → PR cycle).

v0.2 session-state success (when F-08 lands):
- **A same-risk action that auto-`allow`s at session start escalates once the accumulated session risk crosses its threshold** (the Omnigent demo behavior, reproduced deterministically in a test).
- **Consent boundaries:** a write inside a consented scope auto-permits; the same write outside it escalates (ConLeash pattern, 0 live approvals needed for the in-scope path).

OSS community (post-launch):
- stars and PRs, newcomer-friendly contribution paths; (target: 25+ stars, 3 external contributors).

---

## 10. Reliability & Support

- **Fail-closed contract:** any exception, unknown rule input, or disabled engine → `deny` (configurable to audit); default must be deny -> documented.
- **Determinism:** same input/policy → same decision, always.
- No external network dependency in the hot path (the LLM advisor is off by default).
- Support doc, CONTRIBUTING gate (tests/coverage/mypy), CHANGELOG policy.

---

## 11. Risks & Open Questions (for scoping)

- **Choosing the right degree of conservative defaults** — too strict yields false positives, too loose is dangerous; needs operational strategy via `dry_run`/shadow.
- **The model of `audit` vs `escalate`:** which needs human gating vs enhanced logging only? Needs a product decision.
- **Scope of v0.1 is large** (all adapters + OPA parity + MCP server + Postgres + LLM explain). Sequenced internally so the engine is testable before breadth; risk is schedule, not architecture.
- **OPA/Rego parity vs. native JSON/YAML rules:** both are P0 — need a clear "which path is default" story so contributors aren't confused by two authoring models.
- **Fit with the existing tool ecosystem:** keep ToolTrust (engine-only) and lean on MCP-Fabric for the fleet/gateway side rather than reimplementing gateway infra.
- **Language/packaging:** pure Python vs Rust core (Permit0) — we choose Python-first for accessibility.
- **Storage:** JSONL/SQLite default, Postgres sink shipped in v0.1.
- **LLM explanations:** off by default, non-authoritative, never grant-widening; determinism preserved on the default path.
- **How decisions are returned to the model for replanning** needs to be human-verifiable (see CUJ 2).
- **Session-state scope:** the F-08 family (cumulative risk, budgets, consent boundaries) is the biggest live design question after the P0 engine. Decisions needed: where session state lives (in-process vs. passed-in), when it resets, and how much of it the default taxonomy seeds.
- **Tamper-evident audit (F-34) is deliberately P2:** shipping a sound hash-chain correctly (rotation, key management, reader trust) is non-trivial, and a broken "proof" is worse than none. Keep it out of the P0 critical path — but keep the decision log structured so the chain can be retrofitted without a migration.
- **Post-call observable fan-out:** a single tool call can batch into many operations the engine never sees (e.g. `call_aws` batch mode). The engine governs the *proposed* call; the residue endpoint / tool itself must hold the enforcement. Document as a known boundary in the explain layer.

---

## 12. Roadmap (Milestone Sketch)

- **v0.1.0 (P0, per scoping):** core engine (`evaluate`, 4 decisions, fail-closed, taxonomy + defaults, risk scoring, JSON/YAML policy + OPA/Rego parity), audit JSON/SQLite/Postgres, CLI (`evaluate`/`explain`), Python package, **all adapters** (raw, MCP client, LangGraph, PydanticAI, OpenAI SDK, CrewAI), **ToolTrust MCP server**, dry-run/shadow mode, optional LLM explanations, docs; OpenSSF +90%, ruff/mypy strict. **`shipped` when the 15-line integration walk-through works and every CUJ 1-6 acceptance path passes.** (Sequenced internally: engine → policy/OPA → audit → adapters → MCP server → LLM explain → hardening.)
- **v0.2.0 (P1):** session/context state (F-08 family: cumulative risk, budgets, consent scope — the Omnigent/ConLeash differentiator), `audit query`, policy packs + `validate/test`, custom policy functions, OTel spans, HTTP `/authorize` service.
- **v0.3.0 (P2):** approval artifacts & workflow, tamper-evident audit chain (F-34), policy packs catalog, plug into AgentControlPlane & MCP-Data.
- **v0.4.0 (P3):** governance reports, distributed policy sync.

---

## 13. Appendix — What adoption requires from users

Realistically the "enable-it" overhead for the operator:
1. install + `import` + builder with (defaults) → starts instantly.
2. adopt w/ default rules;  shadow watch mode; tune.
3. connect the permissions/framework adapter; at go-live time.
4. After ramp: direct core to postgres for audit query; disable engine.

(Alignment with the 6-month plan: ToolTrust is the "Medium 107" in week 4-5 kickoff. This PRD is the engine-brain, its live implementable scope only adjusts to plan cadence.)