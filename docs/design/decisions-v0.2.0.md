# Design Decisions — Agent ToolTrust v0.2.0

**Version:** 2.0 (Draft — pending approval on `rel-0.2.0`)
**Date:** 2026-08-13
**Depends on:** [PRD.md](prd.md), [design-decisions.md](design-decisions.md) (v0.1.0 ADRs), [architecture-v0.2.0.md](../architecture/architecture-v0.2.0.md)
**Related issues:** M1-M8 (#81-#122) + dev.to community feedback (#142-#148)

> These decisions extend the v0.1.0 ADRs (DD-01…DD-14). Where a v0.1.0 decision is superseded in v0.2.0, it is stated explicitly. DD-XX = v0.2.0 decisions.

## DD-15: Argument-Level Policy as a Second Validation Stage

**Decision:** The gatekeeper validates the *arguments* of every tool call against a per-tool argument schema, in addition to validating tool *selection*. Argument validation is deterministic (regex, type checks, allowlists), not an LLM judgment.

**Alternatives considered:**
- **Selection-only policy (status quo):** Rejected. Tool-selection answers "can the agent call `delete`?" but most real damage comes from the right tool with *wrong or unbounded arguments* — a `DELETE` with no filter, a migration pointed at prod, an unbounded glob. Selection-only is a perimeter, not a constraint engine.
- **LLM-based argument judgment:** Rejected. Non-deterministic, jailbreakable, un-auditable. Violates DD-01.
- **Deep serialization inspection (F-80):** Too invasive for v0.2; argument *schema* validation covers the high-blast-radius cases first.

**Source:** dev.to feedback — #142 (kartik-nvjk).
**Impact:** `DELETE` with empty filter, unbounded row limits, and disallowed-env targets become structurally impossible instead of log-only discoveries.

## DD-16: Deny-Storm / Probe Detection as a Session-Level Signal

**Decision:** Dense runs of denies (or escalations) within a session are a first-class signal, distinct from any individual call. A session-level analyzer (async, off the hot path) tracks rolling deny rate, consecutive-denies, escalation frequency, and attempted-tool entropy, and trips throttle/lock/pause actions when thresholds cross.

**Alternatives considered:**
- **Per-call policy only (status quo):** Rejected. The replan loop becomes a cheap policy *mapper* (try tool, get denied, try next → map the fence), and approval fatigue becomes a DoS vector against the human in the loop. Both are invisible one call at a time.
- **Synchronous detection in the hot path:** Rejected. Violates the strict-and-fast gatekeeper design (DD-01 hot path). Detection belongs in an observer reading audit/traces.

**Source:** dev.to feedback — #143 (Skillselion, Igor).
**Impact:** Closes policy-mapping-by-trial-and-error and approval-fatigue DoS. The gatekeeper stops being a static fence and notices when someone is leaning on it.

## DD-17: External, Agent-Unwritable Verification Sink

**Decision:** A verification layer above the gatekeeper compares the agent's self-report against a source of truth the agent **cannot write to** (API counters, VCS state, billing snapshots). The gatekeeper answers "was this call allowed?"; the verifier answers "did the allowed call actually produce the claimed outcome?"

**Alternatives considered:**
- **Trusting the agent's self-audit (status quo):** Rejected. The self-audit is itself an untrusted tool call — an agent logging "✅" and reading back its own log is auditing inside the same trust boundary it is supposed to check.
- **Relying only on the not-available vs. unexpected-decision distinction:** Rejected. It distinguishes "chose not to self-critique" from "self-critiqued," but cannot prove the critique was *honest*.

**Source:** dev.to feedback — #144 (473185670, Edu Peralta).
**Impact:** The system stops trusting narrative and starts trusting measured reality; the audit trail becomes defensible against fabrication.

## DD-18: Resource / Environment Scoping (Default-Deny)

**Decision:** Policy scopes *which resources* a tool can touch, not just *which tool* can run. Resources are namespaced by environment; each session declares a scope; any call resolving outside the scope is denied. Scope is **default-deny**, not default-open.

**Alternatives considered:**
- **Tool-level policy only (status quo):** Rejected. The same tool can legally touch staging *and* prod; cross-env access is found only in a log after the fact (Tae Kim's real-world case).
- **Environment inference from args:** Rejected as a sole mechanism — fragile and spoofable. Resource tags are the authoritative source.

**Source:** dev.to feedback — #145 (Tae Kim).
**Impact:** Cross-environment access is actively blocked, not logged-and-hoped. Multi-environment deployments become safe.

## DD-19: Tool-Category Guards (Reference: URL Fetch)

**Decision:** Tool *categories* get their own structural guard modules. The reference implementation is the URL-fetch guard: robots.txt actually enforced, PII stripped before content reaches context, and redirects re-resolved against an internal-address blocklist (SSRF). The same plugin interface extends to `shell`, `db`, `http-post`, etc.

**Alternatives considered:**
- **Selection-only fetch policy (status quo):** Rejected. A fetch's danger is not in the call but in *unfiltered content flowing into the model's context* — PII, robots.txt bypass, SSRF redirects.
- **Ad-hoc per-tool checks:** Rejected. No single reusable interface; category guards are testable and composable.

**Source:** dev.to feedback — #146 (iwasinnam2).
**Impact:** Prevents context poisoning, SSRF, and PII leakage into the model — the "boring HTTP call" hole.

## DD-20: Permit-with-Obligation (Three-State Outcome Extension)

**Decision:** Extend the decision outcome from `{allow, deny}` (plus v0.1 `audit`/`escalate`) with **permit-with-obligation**: the call is allowed but carries a mandatory, gatekeeper-enforced side-effect (first-use human sign-off, auto-notify + review ticket, immutable signed audit entry).

**Alternatives considered:**
- **Binary allow/deny (status quo):** Rejected. Forces the choice between over-privileged agents and approval fatigue. XACML called the answer "permit with obligation" two decades ago; SIEM practice has run on it for years.
- **Relying on the agent to attach the side-effect:** Rejected. Obligations are enforced by the policy engine, not by agent cooperation.

**Source:** dev.to feedback — #147 (Skillselion).
**Impact:** Safety of human oversight on rare dangerous moments without the fatigue of reviewing every call; adopts a battle-tested policy pattern rather than inventing one.

## DD-21: Session-to-Session Policy Analytics (Learning Loop)

**Decision:** A batch analyzer over audit logs + distributed traces studies the deny → allow trajectory across sessions: correlates deny patterns to surface recurring benign needs, flags "denied last week, allowed this week" transitions for the same context, and reports dead/over-hit rules.

**Alternatives considered:**
- **Static policy only (status quo):** Rejected. Signal is generated but never converted into learned policy; recurring benign needs stay denied while suspicious drift goes unnoticed.
- **Auto-applying suggestions:** Rejected for v0.2. The analyzer *surfaces* recommendations; a human approves changes. Auto-mutation of security policy is deferred.

**Source:** dev.to feedback — #148 (Igor).
**Impact:** Closes the loop — the gatekeeper evolves policy from its own history; deny-rate drops for legitimate work while anomalies become more visible.

## DD-22: Re-Baselined Milestones M1-M8

**Decision:** v0.2.0 work is organized into **8 thematic milestones** (M1 Policy Model & Rule Engine, M2 Resource Scoping & Delegation, M3 Escalation & Human Approval, M4 Threat & Anomaly Detection, M5 Audit/Verification/Observability, M6 Service & Fleet Access, M7 Compliance & Security Baselines, M8 Quality Gates/Field Tests/Release) mapped to GitHub milestones #5-#12. Every milestone closes only after the shared quality bar: code review, coverage >90%, ruff+mypy strict, code comments, CI green.

**Alternatives considered:**
- **Old M9-M18 scheme:** Superseded. Mixed themes and stale issue references (#117, and header items that no longer exist as issues).
- **Linear build-only sequencing:** Rejected. Thematic milestones keep each deliverable independently shippable and reviewable.

**Source:** 0.2.0 planning session on `rel-0.2.0`.
**Impact:** One WBS (`docs/wbs/v0.2.0/wbs-v0.2.0.md`), 36 issues, 8 GitHub milestones, a uniform exit-gate contract across the release.

## Superseded v0.1.0 Decisions (v0.2.0)

| v0.1.0 ADR | Change in v0.2.0 |
|-----------|------------------|
| DD-09 (argument validation deferred to v0.2) | **Now in scope** — DD-15 implements argument-level policy |
| DD-10 (OPA as subprocess; server mode v0.2) | Server mode evaluation considered under M6 service work |
| DD-13 (no distributed policy sync in v0.1) | **Now in scope** — OPAL integration in M6 (#119) |
| DD-02 (four-state decision set) | Extended by DD-20 (`allow_with_obligation`) |
