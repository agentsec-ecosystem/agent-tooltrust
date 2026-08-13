# Design Decisions — Agent ToolTrust

**Version:** 1.0 (Approved)
**Date:** 2026-08-08
**Depends on:** [PRD.md](prd.md), [architecture-v0.1.0.md](../architecture/architecture-v0.1.0.md)

## DD-01: Deterministic Core, Advisory LLM

**Decision:** The decision pipeline is fully deterministic. The LLM is an optional, post-decision explanation enhancer — it can add prose context but cannot change the decision. It is off by default.

**Alternatives considered:**
- **LLM as primary decision-maker:** Rejected. Research (Permit0, NEXUS, ConLeash, OPA ecosystem) unanimously concludes that deterministic engines are the only auditable path. LLMs are jailbreakable, non-deterministic, and cannot produce reproducible compliance evidence.
- **No LLM at all:** Viable, but optional prose explanations are a differentiator for adoption. The guardrail (off by default, advisory only) preserves determinism.

**Impact:** Hot path has no network dependency. LLM explainer runs post-decision, fire-and-forget.

## DD-02: Four-State Decision Set (not three)

**Decision:** `allow` / `audit` / `escalate` / `deny` — four distinct outcomes, not three.

**Alternatives considered:**
- **Three-state (allow/deny/escalate):** Easier to explain, but collapses "read on sensitive data" into either allow (risky) or escalate (noisy). `audit` = allow + enhanced logging fills this gap.
- **Five-state (allow/audit/escalate/block/revise):** NEXUS uses 4-class (allow/block/confirm/revise). `revise` is a semantic split of escalate — the human says "try again differently." v0.1 folds revise into escalate; v0.2 can add it as a sub-state.

## DD-03: YAML + Rego Dual Policy Backend

**Decision:** Policies can be authored in YAML (native) or OPA Rego. Both evaluate the same `NormalizedCall` input and return the same `Decision` contract. The caller chooses the backend per evaluation; failures in one backend never affect the other.

**Alternatives considered:**
- **YAML only:** Simpler, but misses the enterprise OPA ecosystem. Teams with existing Rego policies can't reuse them.
- **Rego only:** Industry standard, but imposes a learning curve that conflicts with the "15-line integration" goal.
- **Cedar:** AWS-native, open-source, simpler than Rego. Less ecosystem maturity in 2026.

**Impact:** `tooltrust init` generates YAML by default (the accessible path). Rego is documented as "for OPA users." The dual-backend isolation (independent failure modes) is a security property, not a feature overhead.

## DD-04: Python-First, Library-First

**Decision:** ToolTrust is a Python library first, not a service. In-process `evaluate()` is the primary integration path. MCP server, HTTP /authorize, and fleet deployment are layered on top.

**Alternatives considered:**
- **Service-first (Go/Rust, standalone binary):** Higher performance, language-agnostic. Rejected because the target audience (Python agent developers) needs a `pip install` + 15-line adoption path. A service requires infrastructure — the library requires nothing.
- **Rust core with Python bindings (Permit0 pattern):** Maximum performance, but adds build complexity, a foreign function boundary, and a harder contribution story.

**Impact:** Performance target is < 0.5 ms for the deterministic path — achievable in pure Python for a 5-dimension weighted sum with no allocations in the hot loop.

## DD-05: Posture Presets (never blank slate)

**Decision:** `tooltrust init --posture <strict|balanced|permissive>` ships three pre-populated policy templates. The user never starts from a blank file.

**Rationale:** Research shows that permission fatigue and blank-slate defaults are the leading cause of permissive configurations. By pre-populating a restrictive default (balanced), the user overrides *down* (relaxes specific cases) rather than building up from nothing. This matches the "default-deny" posture every PDP standard recommends.

## DD-06: Shadow Mode as Adoption Strategy

**Decision:** Shadow mode (`dry_run=True`) is P0 and the primary adoption path. Deploy → observe → tune → enforce, without changing agent code.

**Rationale:** Every major PDP deployment guide (OPA, MSFT AGT, Vercel policy-opa) recommends shadow-first. A mistaken deny blocks real work — shadow mode gives the platform team data to tune before enforcement.

## DD-07: 13-Domain Starter Taxonomy (not 22+)

**Decision:** Ship 13 domains with ~60 verbs as the starter vocabulary, covering the top tool ecosystems (fs, shell, http, db, git, email, cloud, secrets, iam, payment, approval, search, notify). Permit0 ships 22 domains / 159 verbs — we start smaller and grow via community packs.

**Rationale:** 13 domains cover the tools real coding and infrastructure agents use. The remaining 9 Permit0 domains (CRM, HR, legal, etc.) are specialized — they belong in community packs (CUJ 5), not the starter taxonomy. A smaller, well-maintained vocabulary is more trustworthy than a broad, shallow one.

## DD-08: JSONL → SQLite → Postgres Audit Progression

**Decision:** Three audit sinks shipped in v0.1: JSONL (zero-dependency default), SQLite (local query), Postgres (operational). The sink is a pluggable interface — new sinks don't touch the engine.

**Rationale:** JSONL is the lowest-friction start. SQLite enables `tooltrust audit query` without infra. Postgres is the operational answer for compliance. A pluggable `AuditSink` interface keeps the engine independent of storage.

## DD-09: Argument Validation Deferred to v0.2

**Decision:** Per-call argument-level validation (regex, range, path containment, enum — SkillAudit Layer 2) is P1, not P0.

**Rationale:** v0.1 must ship the engine, adapters, MCP server, and field tests. Argument validation is the largest remaining surface (every tool has unique args) and would dominate v0.1 scope. The default posture (deny-by-default for unknown patterns) provides a safety net until arguments are validated per tool.

## DD-10: OPA as Subprocess in v0.1

**Decision:** OPA integration in v0.1 uses `opa eval` subprocess. Server mode (`opa run --server`) is v0.2.

**Rationale:** Subprocess = zero dependency (OPA binary is a standalone install), deterministic, and simple to debug. Latency overhead (~2 ms) is acceptable for the OPA path. Server mode reduces latency but adds operational complexity (process management, health checks) — unnecessary for the "pip install, works locally" guarantee.

## DD-11: Field Tests as Release Gate

**Decision:** Field tests (`tooltrust field-test`) must pass before any release. They run real agents (not mocks) through a scenario matrix across all supported frameworks.

**Rationale:** Deterministic unit tests prove the engine is correct. Field tests prove the adapters work in real agent loops. A mock-based test suite cannot catch the "deny surfaced as a protocol crash instead of a ToolMessage" bugs that real agent integration exposes. This is the same gating pattern used in EvalForge (19-agent sweep) and Agent Observatory (4 real agents, 794 tests).

## DD-12: 8-10 Real Agents in Field Test

**Decision:** The v0.1 field test exercises 8-10 real agents across major platforms, not just the 6 framework adapters.

**Rationale:** Framework adapters prove "it integrates." Real agents (Claude Code via MCP, SWE-bench coding agents, 2+ OSS agent frameworks) prove "it works in the wild." The diversity of platforms catches integration assumptions (tool-call shape differences, error semantics, async/threading models) that per-framework unit tests cannot.

## DD-13: No Distributed Policy Sync in v0.1

**Decision:** Policy sync (OPAL, fleet distribution) is deferred to v0.4. v0.1 policy is a local file or in-memory object.

**Rationale:** Fleet sync is an orchestration problem, not a policy engine problem. ToolTrust's scope is the PDP, not the distribution layer. The documented path (version in git, load from shared location, redeploy on change) works for single-agent and small-fleet scenarios.

## DD-14: Fail-Closed Everywhere

**Decision:** Every failure path — invalid input, unknown tool, policy parse error, OPA unreachable, audit sink failure, engine crash, timeout — returns `deny` with a distinct `reason_code`.

**Rationale:** The alternative (fail-open) means an attacker who can crash the engine or the OPA backend gets unrestricted tool access. Fail-closed is the PDP standard and the only posture that survives an audit. The cost is availability — if the engine is down, no agent can use tools. This is acceptable because: (a) the engine is in-process and trivial to run, (b) the degraded-mode CUJ (CUJ 9) makes every failure visible with SIEM-ready reason codes.