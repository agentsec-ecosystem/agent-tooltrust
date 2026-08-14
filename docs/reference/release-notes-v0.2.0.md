# Agent ToolTrust v0.2.0 Release Notes

**Status:** Draft — stub for the v0.2.0 release (on `rel-0.2.0`). Finalize during M8 (release readiness steps 6-7).
**Package:** `agent-tooltrust` · **Version:** 0.2.0 (planned)
**Related:** [WBS v0.2.0](../wbs/v0.2.0/wbs-v0.2.0.md) · [decisions-v0.2.0](../design/decisions-v0.2.0.md) · [architecture-v0.2.0](../architecture/architecture-v0.2.0.md)

> **What is this?** This is the release-notes document for v0.2.0. It is seeded with the planned scope; sections are filled in as milestones close. It is NOT the shipped changelog — the authoritative list lives in [CHANGELOG.md](../../CHANGELOG.md).

---

## Planned highlights

### M1 — Policy Model & Rule Engine

- **Argument-level policy** — per-tool argument schema (required fields, forbid-list, bounds, env allowlists) evaluated deterministically before allow/deny. Community feedback: #142.
- **Rule composition** — `and` / `or` / `not` operators and sub-entity grouping (#93).
- **Tool hiding** — per-agent-class `hidden: true` capability filtering (#88).
- **Policy pack format** — `tools.yaml` + `tests.yaml` schema, `tooltrust pack validate` / `pack test` (#91).
- **Permit-with-obligation** — `allow_with_obligation` decision outcome with gatekeeper-enforced side-effects (#147).

### M2 — Resource Scoping & Delegation

- **Resource/environment scoping** — default-deny scope enforcement (staging vs. prod) (#145).
- **Child-agent delegation** — scope-subset invariant via `engine.delegate()` (#108).
- **Dispatcher parser** — canonicalize `bash` / `aws` / `http` calls; unparseable → deny (#106).

### M3 — Escalation & Human Approval

- **EscalationManager** — create/track/approve/deny/expire with TTL, bound to action identity (#84).
- **CLI approve/deny** — `tooltrust approve <id>` / `deny <id> [--reason]` (#85).
- **Action-identity binding** — replay with different args denied (#86).
- **Replay-attempt detection** — same escalation_id reused with different call denied (#95).

### M4 — Threat & Anomaly Detection

- **Deny-storm / probe detection** — session-level analyzer; throttle/lock/pause (#143).
- **URL fetch category guard** — robots.txt, PII stripping, SSRF redirect re-resolution (#146).
- **External verification sink** — agent-unwritable ground truth vs. self-report (#144).

### M5 — Audit, Verification & Observability

- **Session replay from audit** — `tooltrust audit session --replay <id>` (#81).
- **Session-to-session policy analytics** — deny→allow drift learning loop (#148).
- **AgentControlPlane + MCP-Data integration** — fleet PDP + per-data-source authorization (#112).

### M6 — Service & Fleet Access

- **HTTP /authorize** — FastAPI `POST /authorize` for non-Python hosts (#97).
- **Policy packs catalog** — community packs with metadata + test status (#111).
- **OPAL distributed policy sync** — <5s propagation, 3-instance fleet, rollback (#119).
- **Fleet deployment guide** (#120).

### M7 — Compliance & Security Baselines

- **ToolTrust Hardened baseline** (#103), **OWASP 10/10** (#114), **Certified baseline** (#115), **OpenSSF Gold** (#121).

### M8 — Quality Gates, Field Tests & Release

- **6 exit gates** (#83, #89, #100, #107, #110, #113), **v0.2 + v0.3 field test sweeps** (#101, #116), **hardening** (#104), **ship** (#122).

---

## Security posture (v0.2.0)

- Argument schema violations, scope mismatches, delegation exceedances, unparseable dispatcher strings, escalation replays, and SSRF redirects all fail closed with distinct reason codes.
- OWASP Agentic Top 10: 10/10 covered (from 5/10 in v0.1.0).
- OpenSSF: Gold target (from Silver).
- ToolTrust baseline: Essential (v0.1) → Hardened + Certified (v0.2).

## Known limitations / deferred

- Deny-storm thresholds and verification-sink adapters finalized in M4.
- Policy-analytics auto-mutation deferred (human approves suggestions).
- Fleet-scale performance validated only to the 3-instance OPAL test.
