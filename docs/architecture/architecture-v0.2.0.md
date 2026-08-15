# Agent ToolTrust — Architecture v0.2.0 (Delta)

**Version:** 2.0 (Draft — pending approval on `rel-0.2.0`)
**Date:** 2026-08-13
**Status:** Draft
**Depends on:** [architecture-v0.1.0.md](architecture-v0.1.0.md) (base architecture, unchanged parts not repeated here), [PRD.md](../design/PRD.md), [decisions-v0.2.0.md](../design/decisions-v0.2.0.md)

> This document describes the **v0.2.0 architectural deltas** on top of the v0.1.0 architecture. Sections absent here reference the v0.1.0 doc. Deltas map one-to-one to v0.2.0 milestones and issues.

---

## 1. High-Level v0.2.0 Additions

v0.2.0 adds five capabilities on top of the v0.1.0 decision pipeline:

1. **Argument-level policy** — a second validation stage on the call payload (M1).
2. **Resource/environment scoping + delegation + dispatcher** — scope enforcement, child-agent subset invariant, smuggled-call parsing (M2).
3. **Escalation round-trip + anti-replay** — human approval lifecycle bound to action identity (M3).
4. **Defensive layers** — deny-storm detection, URL-fetch guard, external verification sink (M4).
5. **Audit/observability + service/fleet** — session replay, analytics, HTTP /authorize, OPAL sync (M5-M6), compliance baselines (M7), release gates + ship (M8).

```
          ┌──────────────────────────────────────────────────────────────┐
          │                     v0.2.0 Additions (layered)              │
          │                                                              │
 Agent →  │  [Scope Check]   [Argument Policy]   [Dispatcher Parser]     │
 Loop     │        │                │                    │               │
          │        ▼                ▼                    ▼               │
          │  ┌──────────────────────────────────────────────────┐        │
          │  │            NORMALIZE → SCORE → DECIDE            │        │
          │  │   (+ escalation, obligation, tool hiding)        │        │
          │  └───────────────┬──────────────────────────────────┘        │
          │                  ▼                                          │
          │  [EscalationManager] ───► human approve/deny/expire (M3)    │
          │                  │                                          │
          │  [External Verification Sink]  [Deny-Storm Analyzer]  (M4)  │
          │                  │                                          │
          │  Audit / traces → Session Replay + Analytics (M5)           │
          └──────────────────┼──────────────────────────────────────────┘
                             ▼
                       Tool Server (execution)
```

---

## 2. Stage 1b: Argument-Level Policy (DD-15) — M1

**Location:** between normalization and scoring — a per-tool argument schema gate.

**Input:** `NormalizedCall` (now carries the full `arguments` payload).
**Output:** schema pass → continue; schema fail → `deny('<reason_code>')`.

| Check | Example |
|-------|---------|
| Required fields present | `delete` must carry a `filter` |
| Forbidden patterns | `filter` cannot be `*`, `1=1`, or empty |
| Bounds | `row_limit` ≤ max; path within allowlist |
| Env allowlists | migration `target_env` ∈ {staging, prod} |

**Policy extension (tools.yaml override vs. pack schema):**

```yaml
tools:
  - name: "db.delete"
    args_policy:
      filter: {required: true, forbid: ["*", "1=1", ""]}
      target_env: {allowed: ["staging", "prod"]}
      row_limit: {max: 1000}
```

**Determinism:** evaluation is pure (regex/allowlist/type checks); identical inputs → identical decision. Shares the DD-01 hot-path budget (< 0.5 ms).

---

## 3. Scope, Delegation, Dispatcher (DD-18) — M2

### 3.1 Resource / Environment Scoping

- Resources carry environment tags (`staging`, `prod`, `sandbox`).
- A session is spawned with a **declared scope**.
- Any call resolving outside the scope → `deny('scope_mismatch')`, audited.
- **Default-deny**: unscoped sessions cannot touch anything.

### 3.2 Child-Agent Delegation (F-88)

- `engine.delegate(child_id, parent, scope_subset)`.
- Invariant: **child scope ⊆ parent scope**. Violation → `deny`.
- Audit records the full delegation chain (parent → child → …).

### 3.3 Dispatcher Parser (F-87)

- Parses free-form `bash`, `aws`, `http` call strings into canonical `(tool, action, args)`.
- Canonical form is evaluated by the *same* policy path (no second language of rules).
- Unparseable input → `deny('unparseable_dispatcher')` (fail-closed, never guess).

---

## 4. Escalation Round-Trip & Anti-Replay (F-09, F-90, F-89-P1) — M3

### 4.1 EscalationManager

```
Agent (escalate) → EscalationManager (create, id, TTL, status)
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
        approve      deny         expire (TTL)
            │            │            │
         execute     return deny   deny
```

- Escalation is bound to **action identity** `hash(tool, action, args)` (F-09).
- Approval is valid only for the exact action identity it was issued for.
- `tooltrust approve <id>` / `tooltrust deny <id> [--reason]` records approver, timestamp, reason (F-90).
- Replay: same `escalation_id` reused with a **different** call → `deny('replay_attempt')` (F-89-P1); different args → `deny('action_identity_mismatch')`.

### 4.2 Permit-with-Obligation (DD-20) — M1/M3

Decision outcome extended:

| Outcome | Behavior |
|---------|----------|
| `allow` | Execute |
| `audit` | Allow + enhanced logging |
| `escalate` | Human approval (M3) |
| `allow_with_obligation` | Execute + gatekeeper-enforced side-effect (first-use sign-off, auto-notify, signed audit) |
| `deny` | Block with reason |

Obligations are enforced by the pipeline, not delegated to the agent.

---

## 5. Defensive Layers (DD-16, DD-17, DD-19) — M4

### 5.1 Deny-Storm / Probe Analyzer

Async observer over audit/traces, **off** the hot path:

| Signal | Meaning |
|--------|---------|
| deny rate (denies / total) | general probe pressure |
| consecutive denies | fence-mapping |
| escalation frequency | approval-fatigue DoS |
| entropy of attempted tool set | probing (many tools) vs. replan (few tools) |

Threshold trip → behavior-level action: throttle, lock session, pause-for-human.

### 5.2 External Verification Sink

Read-only adapters to agent-unwritable systems (API counters, VCS, billing). Post-hoc verifier diffs self-report vs. ground truth.

### 5.3 Tool-Category Guards (URL Fetch reference)

Each tool category registers a guard module. URL-fetch guard:

- robots.txt parsed and **enforced**
- PII stripped before content reaches the model
- redirects re-resolved; final host checked against internal-address blocklist (RFC 1918, loopback, link-local, cloud metadata)

---

## 6. Audit, Observability, Service & Fleet (F-08d, F-43; M5-M6)

### 6.1 Session Replay (F-08d)

`tooltrust audit session --replay <id>` reconstructs session state from audit entries; replay reproduces the same cumulative risk at each call (falsifiable evidence path).

### 6.2 Session-to-Session Analytics (DD-21)

Batch analyzer over audit + traces: correlate deny patterns, flag deny→allow transitions, report dead/over-hit rules. Human-approves changes (auto-mutation deferred).

### 6.3 HTTP /authorize (F-43)

FastAPI `POST /authorize` — JSON tool call → Decision JSON, for non-Python hosts. Same engine, same fail-closed guarantees over HTTP.

### 6.4 OPAL Distributed Policy Sync

Policy change → OPAL push → all PDP instances within **5s**; `tooltrust policy rollback --version <v>`; 3-instance fleet test.

### 6.5 Tool Hiding (F-83)

Policy marks tools `hidden: true` per agent class; engine filters the capability list. Admin sees all; read-only sees subset.

---

## 7. Security Model (v0.2.0 Extensions)

Extends the v0.1.0 fail-closed table:

| Failure / Attack | v0.2.0 Behavior |
|------------------|-----------------|
| Argument schema violation | `deny('argument_policy')` |
| Out-of-scope resource | `deny('scope_mismatch')` |
| Child exceeds parent scope | `deny('delegation_scope_exceeded')` |
| Unparseable dispatcher string | `deny('unparseable_dispatcher')` |
| Escalation replay / identity mismatch | `deny('replay_attempt')` / `deny('action_identity_mismatch')` |
| Deny-storm / probe threshold | throttle / lock / pause |
| PII in fetch response | stripped before context |
| SSRF redirect to internal address | `deny('ssrf_blocked')` |
| Agent self-report contradicted by external sink | flagged in verification report |
| OWASP A08 (unbounded consumption) | delegation scope limit |
| OWASP A03 (excessive agency) | output inspection + argument policy |

**State:** v0.2 adds session/store state (scopes, escalations, analyzer windows). Session state decision from v0.1 open question: in-process default, Postgres-backed for fleet (M6).

---

## 8. Technology Deltas

| v0.1.0 | v0.2.0 addition |
|--------|-----------------|
| Python 3.12+ / uv | unchanged |
| YAML + Rego policy | + `tools.yaml` argument schema, pack format (F-61) |
| JSONL/SQLite/Postgres audit | + OPAL sync (M6), session replay (M5) |
| FastAPI (MCP server) | + HTTP `/authorize` (F-43) |
| pytest / hypothesis / ruff / mypy | unchanged; coverage bar >90% per milestone, >95% at release |

---

## 9. Open Design Questions (v0.2.0)

- **Deny-storm thresholds:** concrete default values for rate, consecutive, entropy (M4).
- **External verification sink adapters:** which sources ship first (API counters / VCS / billing) and how quotas are handled (M4).
- **Verification cadence:** post-hoc batch vs. near-real-time (M4).
- **Obligation semantics:** how `allow_with_obligation` interacts with shadow mode and the eight-state band map (M1/M3).
- **OPAL transport/authz:** token auth between OPAL and PDP instances (M6).