# Agent ToolTrust — Product Requirements Document (PRD)

**Version:** 1.0 (Approved)
**Date:** 2026-08-08
**Status:** Approved ✅
**Owner:** Debashish Ghosal
**Repo:** `deghosal-2026/agent-tooltrust` (private → OSS)
**Package:** `agent-tooltrust`

---

## 1. Executive Summary

Agent ToolTrust is a **contextual risk and permission engine for tool-using AI agents**. Before an agent's tool call executes, ToolTrust scores the action across risk dimensions (tool type, action class, environment, data sensitivity, agent/principal identity) and returns one of four decisions — **allow, audit, escalate (human approval), or deny** — each with a human-readable explanation artifact and a machine-recorded audit trail.

The insight that justifies the project: **flat allow-lists are a reachability control, not an authorization decision.** The same tool is harmless in staging and dangerous in production; the same read is fine on public docs and risky on customer data. Tool permissions that ignore this context force teams to choose between "over-privileged agents" (dangerous) and "approve-everything UX" (useless). ToolTrust gives a third option: deterministic, explainable, context-aware decisions with repeatable policy.

This PRD defines **why** the product exists (business rationale), **who** it serves, **what** it delivers (CUJs — critical user journeys — and the feature set), and how it deliberately pursues five quality bets: **platform-neutral compatibility, ease of use, ease of integration, readability of decisions/criticality, and extensibility.** It reflects community research into the current landscape (Section 4) and intentionally positions ToolTrust as the adoption-first, learnable implementation of this pattern.

**Scoping snapshot (decided 2026-08-08):** Python library + MCP client wrapper + ToolTrust MCP server; full 4-state decisions; JSON/YAML policy + OPA/Rego parity; 3 posture presets (strict/balanced/permissive); adapters for 6 frameworks; optional LLM explanations (off by default); Postgres-ready audit; adversarial resilience; field tests as release gate; 8-10 real agents across platforms; SWE-bench integration; demo reference agent. **Security baselines: OpenSSF Silver → Gold, OWASP Agentic Top 10 full coverage, ToolTrust Essential → Hardened → Certified.**

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

### Policy customization model (user- and org-supplied rules)
The shipped defaults are a **starter template, not the product.** The real value of ToolTrust is that every organization brings its own risk posture. The customization surface is deliberately three-tier:

| Tier | Who | What they provide | Engine role |
|------|-----|-------------------|-------------|
| **Default taxonomy** | Shipped with ToolTrust | Curated tool-category → baseline risk scores; a starter action vocabulary; reasonable escalation thresholds | Evaluates; ships as `default_policy.yaml` with every install |
| **Org overrides** | Platform/Security team | Per-org weights, environment-to-criticality mappings, data-class definitions, approval thresholds — starting from a chosen posture preset, not a blank slate | Overlays on top of defaults; highest-priority input to the scorer |
| **Community packs** | OSS contributors | A reusable `.yaml` pack that maps a specific tool ecosystem (e.g., "GitHub admin tools", "AWS cost ops", "notion.write") onto the canonical taxonomy with their org's risk profile | Validated via `tooltrust pack validate`; installable via `tooltrust pack add` |

An org can start with defaults and incrementally override — the `tooltrust init --posture <strict|balanced|permissive>` scaffold generates a pre-populated `tooltrust.yaml` with the chosen posture's rules, commented for customization. Users never face a blank file. The engine merges (posture default ∨ org overrides ∨ per-call context) at evaluation time.

**Policy versioning and migration:** Every `tooltrust.yaml` carries a `version` field (semver). When an org upgrades, `tooltrust check --migrate` detects breaking changes between versions (removed tools, renamed data classes, threshold shifts) and reports them. A policy version change is recorded in the decision audit — every audit entry includes `policy_version`. This guarantees that "what policy version governed this decision?" is always answerable in a compliance review, even if the policy has since changed.

**Policy deployment and sync (deferred, documented trade-off):** In v0.1, policy lives as a local file or in-memory Python object — no distributed sync. For single-agent or co-located scenarios this is enough; for a fleet, the policy must reach every enforcement point (library instances, MCP wrappers, the MCP server). v0.4 targets distributed policy sync (OPAL or equivalent). Until then, the documented path is: version policies in git, load from a shared location, redeploy on change. This is a deliberate scope trade-off — the engine ships first; fleet-wide coherence ships when AgentControlPlane matures.

### Starter action taxonomy (shipped in `default_policy.yaml`)

The taxonomy is the canonical vocabulary for *what agents do* — a curated, append-only map of domains → verbs → baseline risk. Every tool call from every framework normalizes to one of these verbs. Write one risk rule for `db.query` and it covers PostgreSQL, SQLite, and the MCP database adapter.

| Domain | Verbs | Baseline risk | Notes |
|--------|-------|---------------|-------|
| **fs** (filesystem) | `read`, `write`, `delete`, `list`, `move` | low→high | write=med in staging, high in prod; delete always critical |
| **shell** | `exec`, `pipe` | high | shell exec always high; argument inspection layer catches command smuggling |
| **http** | `get`, `post`, `put`, `delete`, `patch` | low→med | get=low; methods with bodies=med; outbound to unknown hosts raises risk |
| **db** (database) | `query`, `execute`, `migrate`, `drop` | low→critical | SELECT-only=low; DDL=high; DROP=critical |
| **git** (version control) | `status`, `diff`, `log`, `commit`, `push`, `force_push`, `branch`, `merge`, `clone` | low→critical | read-ops=low; push=med; force-push=critical |
| **email** | `read`, `send`, `delete`, `search` | low→high | read=low; send=high (irreversible external comm) |
| **cloud** (infra) | `list`, `describe`, `create`, `update`, `delete`, `scale` | low→critical | list/describe=low; create/update=high; delete=critical |
| **secrets** | `read`, `write`, `rotate`, `revoke` | critical | any secret access at least high; write/revoke=critical |
| **iam** (identity) | `read_role`, `assign_role`, `revoke_role`, `create_key` | high→critical | read=high; assign/revoke/create=critical |
| **payment** | `read`, `refund`, `transfer`, `charge` | med→critical | read=med; refund=high (above threshold=critical); transfer/charge=critical |
| **approval** | `read`, `approve`, `deny`, `delegate` | med→critical | approve/delegate=critical |
| **search** | `query`, `index`, `delete_index` | low→med | read=low; index mutation=med |
| **notify** | `send_slack`, `send_teams`, `send_webhook`, `page` | low→high | slack=low; paging=high; webhook to external=high |

**Risk weight mapping** (shipped default, overridable per org):
| Action weight | Value | Examples |
|---------------|-------|---------|
| `read` | 0 | list, describe, status, diff, log, query, get |
| `write` | 3 | write, create, update, send, post, put, execute |
| `delete` | critical (10) | delete, drop, revoke, force_push |
| `grant` | critical (10) | assign_role, approve, delegate, create_key |

This vocabulary is a **starter**, not the final word. Community packs extend it for specific ecosystems (GitHub Actions, Notion, Jira, etc. — see CUJ 5).

### Design principle (from research)
- **Deterministic by default; the model does not vote.** The policy engine decides. The LLM at most is an *optional* advisor that can narrow scope (flag "arguable," escalate), never widen it. This is the strongest shared conclusion across Permit0, NEXUS, ConLeash, MSFT AGT, and the OPA ecosystem.
- **Context is not just the current call** — it includes what the session has done so far. Omnigent and ConLeash both show that accumulated risk, consent scope, and budgets make the *same* call behave differently early vs. late in a workflow ("the email your sales-org agent sends first thing is safe; the one it sends after reading a customer's confidential folder is not"). This session-state model (F-08 family) is a stated differentiator and a v0.2 commitment.
- **An audit you can't prove is half an audit.** Signed/tamper-evident decision logs (the Permit0 pattern, F-34) turn "we log decisions" into "we can cryptographically show the log is unedited" — the difference that survives a compliance review.

### Terminal-state definition ("done")
A working `v0.1.0` that can be installed with `pip install agent-tooltrust`, initialized with `tooltrust init` (which produces a commented org-policy template), integrated into an agent loop in under ~15 lines, evaluate a matrix of realistic safe/risky/approval-needed tool calls with correct outcomes, allow org-specific overrides via `tooltrust.yaml`, emit explanations, and log a searchable audit trail.

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

Eleven critical journeys, each with an entrance gate / decision / acceptance criteria. These are the north star for the feature set.

### CUJ 1 — Evaluate one tool call ("15 lines to a decision")
As an engineer, I run a small snippet, see all four decision types correctly returned, and understand the output immediately.

**Acceptance criteria (P0):**
| Scenario | Expected decision | Expected explanation |
|----------|-------------------|---------------------|
| Read logs in staging, internal data | `allow` | "Read-only in staging: low risk" |
| Read logs in staging, sensitive data | `audit` | "Read on sensitive data: logged, no block" |
| Write deploy in production, internal data | `escalate` | "Write in production: requires approval" |
| Delete in production, restricted data | `deny` | "Delete in production with restricted data: blocked" |
| Unknown tool name, any context | `deny` | "Unknown tool: default deny" |
| `evaluate()` call on an unreachable engine | `deny` | "Engine unavailable: fail-closed" |

All within ~15 lines of Python, no service, no network call in the hot path.

### CUJ 2 — Wire into an agent framework ("integrate in one afternoon")
As an engineer, I hook ToolTrust into each major framework using an idiomatic wrapper and get safe-by-default without breaking the agent loop.

**Per-framework acceptance criteria (P0):**

| Framework | Integration point | Deny experience |
|-----------|-------------------|-----------------|
| **Raw Python** | `@tooltrust.guard` decorator or `with tooltrust.session():` context | `ToolTrustDecisionError` with `.decision` attribute |
| **MCP client** | Proxy `tools/call` through the wrapper | Tool result returns `isError: true` with the deny reason as content — the model sees it as a tool error it can replan around |
| **LangGraph** | ToolNode pre-call interceptor / callback | Denied tool returns a `ToolMessage(content="[ToolTrust denied] reason...")` — the graph continues, no crash |
| **PydanticAI** | `@tooltrust.guard` on `@agent.tool` | `ModelRetry` or tool-return error surfaced to the agent's next reasoning step |
| **OpenAI Agents SDK** | `tool_input_guardrail` hook | `ToolGuardrailFunctionOutput.deny(reason=...)` — framework-native denial, agent replans |
| **CrewAI** | Tool wrapper / `_run()` interceptor | Denied tool returns error string; agent sees it as a tool output it can handle |

Every framework: audit entry emitted for every decision (allow and deny alike); field-test validated (CUJ 7).

### CUJ 3 — Understand *why* an action was risky ("explainable, not black-box")
As a reviewer, when a request was escalated or denied, I can read the explanation, understand which factor drove the decision within 10 seconds, and know what to change — without reading engine code.

**Acceptance criteria (P0):**
- Decision object carries: `decision` (str), `criticality` (none/low/med/high/critical), `reason_code` (machine-readable), `explanation` (template-generated, human sentence), `factors` (list of `{dimension, value, contribution}`).
- **Actionability test:** "A human given only the explanation text and the original tool call can identify the one change (e.g., approve, move to staging, lower data class) that would change the outcome — without consulting documentation."
- `tooltrust explain '<call-json>'` CLI prints the full factor breakdown.
- Explanations are stored in the audit log; no "denied with no reason" entries.

### CUJ 4 — Adopt incrementally with shadow mode ("trust before you enforce")
As platform lead, I deploy ToolTrust in **observe-only** mode first, monitor decision logs for a real workload, tune the policy against what I see, and only then flip the enforce switch — without changing a single line of agent code.

**Acceptance criteria (P0):**
- `engine.evaluate(..., dry_run=True)` returns the decision, logs it to the audit, but returns `allow` to the caller — the agent never sees the shadow decision.
- After N days of shadow, `tooltrust audit query --dry-run` shows the decisions that *would have* been blocked/escalated.
- Platform lead tunes the policy (`tooltrust.yaml`), reruns shadow until the only blocked actions are genuinely unwanted, then flips `dry_run=False`.
- The difference between shadow and enforced decisions is visible in one diff or audit filter.

### CUJ 5 — Extend ToolTrust without touching the engine ("one pack, one PR")
As a tool platform author, I define a new tool ecosystem (or risk function) using a documented schema, validate it, and the engine scores it — no engine core changes, no rebuild.

**Acceptance criteria (P1):**
- A `tooltrust pack add` flow: create a `tools.yaml` mapping native tool names → canonical action types + risk metadata; write a `tests.yaml` with expected decisions; run `tooltrust pack validate && tooltrust pack test` — all pass without engine changes.
- Custom risk function registered via a pure-function decorator (`@tooltrust.risk_function`), tested in isolation, and correctly fed into the scorer.
- Contribution is one file + one test file → one PR.
- A one-page "how to contribute a pack" doc is the only reference needed.

### CUJ 6 — Prove compliance ("show me the decision log")
As a compliance reviewer, given a `session_id`, I can reconstruct the full chain of decisions for that session, export it in a defensible format, and trace every escalated action back to its human approver.

**Acceptance criteria (P0):**
- `tooltrust audit show --session <id>` prints every decision for that session: timestamp, tool, action, env, data_class, decision, reason_code, explanation, policy_version, approver (if escalated).
- Exportable as JSON and CSV (`--format json|csv`).
- Every escalated action has a linked approval record with: who approved, when, what they approved, expiry.
- Chain-of-decisions for a multi-step agent workflow is reconstructable and traceable in under 5 minutes.

### CUJ 7 — Field test ("it actually works in real agent loops")
As a contributor or reviewer, I watch ToolTrust's decisions in real, running agent loops — not just unit fixtures — across every supported framework. Field tests are a release gate; no green matrix, no ship.

**Acceptance criteria (P0, gating release):**
- A field test harness (`tooltrust field-test`) drives real agents through a scripted scenario matrix: safe/staging-read → allow; prod-write-sensitive → escalate; blocked op → deny; unknown tool → fail-closed; deny → model replan → agent tries a different tool; audit entry emitted for all.
- **8-10 real agents across major agentic platforms** exercised: OpenAI SDK, LangGraph, PydanticAI, CrewAI, raw Python, MCP client, Claude Code via MCP, SWE-bench coding agents, plus at least 2 open-source agent frameworks — not just mocked stubs.
- Every adapter in v0.1 is exercised in its native framework, with decision outcomes asserted per scenario.
- The adversarial sub-matrix (CUJ 11) is part of the field test suite.
- A field test report (`docs/field-test/`) records scenarios × frameworks × expected/actual decision × pass/fail, regenerated on each release.
- Any field-test miss on a P0 scenario blocks the release.

### CUJ 8 — Customize the risk posture to my org ("not a blank slate")
As a platform/security lead, I choose a **policy posture preset** (strict/balanced/permissive), then incrementally override: my environments, my data classifications, my tool categories, my thresholds — without touching engine code. I never start from zero.

**Acceptance criteria (P0):**
- `tooltrust init` offers three postures:

| Posture | Default behavior | Best for |
|---------|-----------------|----------|
| **strict** | Deny-by-default; write=escalate always; read-only in staging; all unknown tools denied | Prod fleets, compliance environments |
| **balanced** (default) | Audited reads; write-to-staging allowed; prod-writes escalate; destructive ops denied | Internal dev platforms |
| **permissive** | Deny only destructive ops (delete/drop); audit everything else; local dev | Local dev, trusted sandboxes |

- Choosing `strict` generates a `tooltrust.yaml` pre-populated with restrictive rules — the user overrides *down* (relaxes specific cases) rather than building up from nothing.
- Custom environments/data classes/weights can be set and the same tool call scores differently in each.
- `tooltrust test` confirms custom overrides don't accidentally permit a dangerous action.
- A `tooltrust diff` shows which defaults were kept, which were overridden, and which gaps remain.
- Policy loads from `TOOLTRUST_POLICY_PATH` and is PR-reviewable.

### CUJ 9 — Degraded and failure modes ("what happens when it breaks")
As an operator, I know exactly what happens in every failure condition: the engine is unreachable, the OPA backend is down, the LLM explainer errors, a malformed policy is loaded, a timeout occurs — and every scenario is safe by default.

**Acceptance criteria (P0):**

| Failure | Behavior | Why |
|---------|----------|-----|
| Policy engine process crashes / import fails | Every `evaluate()` call returns `deny` with reason `engine_unavailable` | Fail-closed: no authorization → no execution |
| OPA backend unreachable (network error, timeout) | Calls routed to the OPA path return `deny` with `opa_backend_unavailable`; native JSON/YAML path unaffected | Dual backend: each fails independently |
| LLM explainer API error or timeout | Explanation falls back to template-generated text; decision is unaffected | LLM is advisory only; the decision was already made deterministically |
| Malformed `tooltrust.yaml` (parse error) | Engine refuses to load; `tooltrust check` reports the parse error at line/column; no policy = all calls deny | Never operate with a broken policy |
| `evaluate()` call exceeds configured timeout | Returns `deny` with `evaluation_timeout` | Safety over latency |
| Audit sink failure (disk full, Postgres down) | Decision stands; audit write failure is logged to stderr; engine continues evaluating | Audit is a side effect, not a gating dependency |

No failure mode silently allows. Every failure reason is logged with a distinct `reason_code` the SIEM can alert on.

### CUJ 10 — Escalation round-trip ("human says yes or no, agent continues")
As an operator, when a tool call is escalated, a human approves or denies it; the agent resumes exactly where it left off, and the approval is audited with an expiry.

**Acceptance criteria (P1):**
- Agent calls tool → engine returns `escalate` + `escalation_id` + reason → agent pauses.
- Human reviews the escalation (via CLI `tooltrust approve <id>` or programmatic callback): sees the tool call, the reason, the context, and approves or denies.
- On **approve:** the engine records an approval event bound to `escalation_id` + `action_identity` (tool+args hash, ensuring the approval can't be replayed for a different call); tool executes; agent resumes.
- On **deny:** engine records the denial; agent receives the deny reason and can replan.
- Approval is time-bounded (default: 5 minutes, configurable); an expired approval is treated as deny.
- An approval for call X cannot be reused for call Y (action-identity binding prevents replay).

### CUJ 11 — Adversarial resilience ("you can't trick the engine")
As a security reviewer, I attempt to bypass ToolTrust using known agent-attack techniques — prompt injection, tool-name obfuscation, OPA policy manipulation, argument smuggling — and the engine blocks every attempt, logs it, and never silently allows.

**Acceptance criteria (P0 for v0.1):**

| Attack vector | Expected defense |
|---------------|-----------------|
| Prompt injection: LLM instructed to call a blocked tool | Engine evaluates the tool call, not the prompt; deny stands; model sees a rejection it can't override |
| Tool-name obfuscation: `"deploy_service "` (trailing spaces), Unicode lookalikes (`dеploy`), case variants | Engine normalizes tool names before matching; unknown normalized name → deny |
| Argument smuggling via dispatcher: `bash: "git push --force"` when `git.push` is denied | Dispatcher input parsed to canonical (tool, action) and evaluated against the same policy (F-87, v0.2) |
| OPA policy tampering: attacker modifies the `.rego` file | Policy version recorded in every decision log; hash mismatch detection (F-34 by v0.3); before that, filesystem integrity is the operator's responsibility |
| Replay attack: reuse an approval token from an earlier escalate | Approval is bound to `action_identity` (tool+args hash); replay with different args fails |
| Flooding: rapid-fire tool calls hoping one slips through | Rate limits (F-86, v0.2) throttle per-session; before that, every call is independently evaluated — no "slip through" path |

Every blocked attack is logged with the distinct `reason_code` for that attack class, making a SIEM dashboard possible. The adversarial sub-matrix is part of the field test suite (CUJ 7).

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
| F-12 | **Degraded/failure mode handling** — every failure path is deny + logged reason (engine crash, OPA unreachable, malformed policy, timeout, audit sink failure) | P0 | CUJ 9; no-fail-open guarantee, SIEM-ready reason codes |

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
| F-65 | **Policy diff/report** — which defaults were kept, which were overridden, which gaps remain | P0 | supports CUJ 8: org customization with auditability |
| F-66 | **Policy posture presets** — `strict` / `balanced` (default) / `permissive` starter policies shipped with ToolTrust | P0 | generated by `tooltrust init --posture <name>`; pre-populated not blank |
| F-67 | **`tooltrust check`** — validate `tooltrust.yaml` for parse errors, unknown keys, missing required sections; return line/column on failure | P0 | CUJ 9: never operate with a broken policy |

### 7.7 Governance/dev tools
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-70 | "shadow mode" (`dry_run=True`) | P0 | **required boundary** for adoption |
| F-71 | Policy test runner (`pack test` / example) | P1 | deterministic |
| F-72 | Policy version in decision log | P0 | auditability |
| F-73 | README case studies / teaching materials per risk level | P1 | "easy to understand criticality" |
| F-74 | Optional LLM explanation endpoint (`tooltrust explain --llm`) | P0 | off by default; non-authoritative |
| F-75 | **Field test harness** (`tooltrust field-test`) | P0 | drives real agents through scenario matrix; publishes `docs/field-test/` report; is a release gate (see CUJ 7) |

### 7.8 Defense-in-depth & safety layers
| ID | Feature | Priority | Notes |
|---|---|---|---|
| F-80 | **Argument-level semantic validation** | P1 | regex/range/path-containment/enum on args — `SELECT`-only SQL, refund capped, URL allow-list (SSRF), path containment, never raw-string shell args (SkillAudit Layer 2) |
| F-81 | **Tool definition scanning** | P1 | scan tool descriptions for hidden instructions/typosquatting/poisoned payloads *before* the model sees them (MSFT AGT pattern) |
| F-82 | **Output/response inspection** | P1P2 | redact secrets (keys/PII), catch injected instructions in tool results returning to the model (SkillAudit Layer 4) |
| F-83 | **Discovery-time tool hiding** | P1 | don't even expose tools an agent can't call — smaller surface, fewer tokens, "you can't misuse a tool you were never shown" |
| F-84 | **CI policy regression suite** | P1 | `tooltrust test` replays recorded decision fixtures (golden sets per env/action/class) on every PR; deterministic drift detection |
| F-85 | **`tooltrust init` scaffold** | P0 | `tooltrust init [--posture strict|balanced|permissive]` generates a commented `tooltrust.yaml` (pre-populated with chosen posture) + adapter + quickstart |
| F-86 | **Session-call rate/burst limits** | P1 | per-session op-count and burst ceilings (SkillAudit Layer 3b) |
| F-87 | **Dispatcher-bypass safety** | P1-P2 | parse coarse tool input to canonical (name, action) and evaluate against the same policy |
| F-88 | **Child-agent delegation scope** | P2 | delegated agent B's scope must be a *subset* of parent A's (confused-deputy protection) |
| F-89 | **Adversarial resilience suite** — tool-name normalization, replay-attempt detection, flood resistance | P0-P1 | CUJ 11; normalization P0 for v0.1 (spaces, case, Unicode lookalikes); replay + rate-limit P1 (v0.2) |
| F-90 | **`tooltrust approve` / `tooltrust deny` CLI** for escalation round-trip | P1 | CUJ 10; time-bounded, action-identity-bound, logged |
| F-91 | **Demo agent reference implementation** | P0 | a `tooltrust-demo` agent with intentionally risky tools (fs, shell, http, db, git) demonstrating all 4 decision types in one narrative; lives in `examples/demo-agent/` |
| F-92 | **SWE-Bench integration** | P1 | ToolTrust governing coding agents running SWE-bench tasks — enforce fs/shell/git tool policies during benchmark runs; decision trace per-task for post-hoc analysis |

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
1. **Adoption friction:** time from `pip install` → first correct `evaluate()` output < 5 min for a reader (target <2 min with `tooltrust init`).
2. **Correctness:** "Does it get the right verdict on a 40-cell matrix of tool×env×action×class?" — target 100% on the acceptance matrix (deterministic).
3. **Explanation usefulness:** reviewers can re-explain the decision in one paragraph (no "ugh, why?"); deny reasons are `actionable` (a test in CI).
4. **Safety:** >90% of the *unsafe-and-suspicious* matrix rows → deny; 0 crafted `allow` for `delete` in prod with class `restricted`.
5. **Field-test green (release gate):** every P0 scenario passes in every framework's real agent loop — safe/staging→allow, prod-write-sensitive→escalate, blocked→deny, unknown-tool→fail-closed, deny→replan round-trips, adversarial sub-matrix (CUJ 11) — with a regenerated `docs/field-test/` report at each release.
6. **Performance:** <2 ms deterministic overhead per call (target <0.5ms).
7. **Extensibility:** a contributor can add a new tool pack + test via one page of docs in one sitting (measure: docs `1 new pack` issue → PR cycle).
8. **Customization:** a platform lead can choose a posture preset (`tooltrust init --posture balanced`), override defaults for their org, and load the result from `tooltrust.yaml` without touching engine code.
9. **Security resilience:** 0 crafted `allow` outcomes on the adversarial sub-matrix (tool-name normalization, injection attempts, unknown-tool probes, replay attempts).

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

## 11. Security Compliance Baseline

ToolTrust targets three concrete, audit-level security baselines. Each is a public checklist — users can self-audit, and the project publishes its compliance status. **Target: medium across all three; high for OWASP (full coverage v0.2).**

### 11.1 OWASP Agentic AI Top 10 — Target: Full Coverage (HIGH)

| OWASP Risk | ToolTrust mitigation | Feature IDs | Coverage |
|------------|---------------------|-------------|----------|
| **A01: Harmful Instructions** | Policy evaluated outside the model; prompt injection cannot alter a decision | F-01, F-04, CUJ 11 | v0.1 ✅ |
| **A02: Tool & Function Misuse** | 4-state decision on every tool call; taxonomy gating; all 13 domains shipped | F-02, F-05, taxonomy | v0.1 ✅ |
| **A03: Data Leakage & Privacy** | Data sensitivity dimension in scoring (v0.1); output inspection (v0.3) | F-03, F-82 | v0.1 partial, v0.3 full |
| **A04: Excessive Agency & Autonomy** | Posture presets (strict/balanced/permissive); deny-by-default; tool hiding (v0.2) | F-66, F-83, F-04 | v0.1 partial, v0.2 full |
| **A05: Supply Chain Vulnerabilities** | Tool definition scanning (v0.2); pack validation | F-81, F-61 | v0.2 |
| **A06: Prompt Injection & Jailbreaking** | Engine outside the model; tool-name normalization; adversarial field tests | F-01, F-89, CUJ 11 | v0.1 ✅ |
| **A07: Insecure Tool Design** | Argument-level validation (v0.2); fail-closed on unknown tool | F-80, F-04 | v0.2 |
| **A08: Multi-Agent Coordination Risks** | Child-agent delegation scope subset (v0.3); per-agent decision log | F-88, CUJ 6 | v0.3 |
| **A09: Inadequate Human Oversight** | Escalation round-trip (v0.2); time-bounded, action-identity-bound approvals | F-90, CUJ 10 | v0.2 |
| **A10: Insufficient Monitoring & Logging** | Decision audit log (JSONL/SQLite/Postgres); exportable; policy version per entry | F-30, F-31, F-33, F-72, CUJ 6 | v0.1 ✅ |

**v0.1: 5/10 full coverage. v0.2: 9/10 full coverage (A03 partial). v0.3: 10/10 full coverage.**

### 11.2 OpenSSF Best Practices Badge — Target: Silver (MEDIUM)

All 6 public repos already achieved **Passing (105%)**. ToolTrust targets **Silver**, with Gold deferred to community phase (requires 2+ independent reviewers).

| Criterion | Requirement | ToolTrust action | Milestone |
|-----------|-------------|------------------|-----------|
| **Passing** (baseline) | Basic OSS hygiene | All shipped in repo scaffold | ✅ Already passing |
| **Dynamic analysis** | Fuzzer/sanitizer in CI | `hypothesis` property-based fuzzer for `evaluate()` input space | v0.1 |
| **Branch protection** | PR review required; no direct push | GitHub branch protection rules on main | v0.1 |
| **Signed releases** | Cryptographically signed artifacts | Sigstore / PyPI trusted publishing | v0.1 |
| **Vulnerability disclosure** | Published process with SLAs | 48h acknowledge / 90d fix SLA in SECURITY.md | v0.1 |
| **Build reproducibility** | Reproducible builds | `uv` lockfile; CI verifies hash match | v0.1 |
| **Gold** (HIGH — aspirational) | 2+ independent reviewers per change | Requires community maturity | Post v0.3 |

### 11.3 Custom ToolTrust Security Baseline — Target: Hardened (MEDIUM)

A self-service checklist shipped as `SECURITY_BASELINE.md`. `tooltrust baseline check` audits a deployment against its chosen tier. **Target Hardened; Certified aspirational.**

| Tier | Posture | Key requirements | Target |
|------|---------|-----------------|--------|
| **Essential** | balanced (default) | Policy on every call; audit log; deny-by-default; shadow mode; OWASP A02/A04/A06/A10 covered; tool-name normalization | v0.1 ✅ |
| **Hardened** (MEDIUM) | strict | All Essential + argument validation (F-80); session-state (F-08); tool hiding (F-83); escalation round-trip (CUJ 10); rate limits; replay detection; poison-tool scanning (F-81); OWASP A01-A10 full coverage | v0.2 |
| **Certified** (HIGH — aspirational) | strict + tamper-evident | All Hardened + tamper-evident audit (F-34); dispatcher-bypass (F-87); child delegation (F-88); output inspection (F-82); OpenSSF Gold; external security review | v0.3+ |

The baseline is auditable: every item maps to a feature ID, a test, or a config flag. The checklist ships in `SECURITY_BASELINE.md` and is regenerated per release.

### Summary: Three Standards, Medium as Floor

| Baseline | v0.1 | v0.2 (MEDIUM target) | Aspirational (HIGH) |
|----------|------|----------------------|---------------------|
| **OWASP Agentic Top 10** | 5/10 covered | 9/10 covered | 10/10 full (v0.3) |
| **OpenSSF Best Practices** | Silver | Silver | Gold (needs community) |
| **ToolTrust Security Baseline** | Essential | Hardened | Certified (v0.3+) |

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

- **v0.1.0 (P0, per scoping):** core engine (F-01-F-12, F-20-F-65), policy posture presets (F-66), `tooltrust check` (F-67), taxonomy + defaults, audit JSON/SQLite/Postgres, adapters (F-41), MCP server (F-11), dry-run/shadow, LLM explain, tool-name normalization (F-89 P0), field test gate (F-75), demo agent (F-91), docs. **OpenSSF Silver, OWASP 5/10, ToolTrust Essential.** Shipped when CUJs 1-9+11 (P0) pass and field-test matrix is green.
- **v0.2.0 (P1):** session/context state (F-08), argument validation (F-80), escalation round-trip (F-90), tool scanning (F-81), tool hiding (F-83), CI policy suite (F-84), rate limits (F-86), replay detection (F-89 P1), SWE-bench integration (F-92), `audit query`, OTel, HTTP `/authorize`. **OWASP 9/10, ToolTrust Hardened.**
- **v0.3.0 (P2):** output inspection (F-82), dispatcher-bypass (F-87), child delegation (F-88), tamper-evident audit (F-34), packs catalog, AgentControlPlane/MCP-Data integration. **OWASP 10/10, ToolTrust Certified aspirational.**
- **v0.4.0 (P3):** governance reports, distributed policy sync. **OpenSSF Gold aspirational.**

---

## 13. Appendix — What adoption requires from users

Realistically the "enable-it" overhead for the operator:
1. install + `import` + builder with (defaults) → starts instantly.
2. adopt w/ default rules;  shadow watch mode; tune.
3. connect the permissions/framework adapter; at go-live time.
4. After ramp: direct core to postgres for audit query; disable engine.

(Alignment with the 6-month plan: ToolTrust is the "Medium 107" in week 4-5 kickoff. This PRD is the engine-brain, its live implementable scope only adjusts to plan cadence.)