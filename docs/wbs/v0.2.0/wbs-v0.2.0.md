# WBS — Agent ToolTrust v0.2.0

> **Milestones covered:** v0.2.0 (M1-M8 + parallel M7.5) — full plan re-baselined on `rel-0.2.0` branch.
> **PRD:** [PRD.md](../design/PRD.md) | **Architecture:** [architecture-v0.1.0.md](../architecture/architecture-v0.1.0.md) (v0.2 architecture to follow)
> **Issue tracking:** All 52 v0.2.0 issues live in GitHub Milestones [M1-M8](../../../issues?q=is%3Aissue+milestone%3A%22M1+%E2%80%94+Policy+Model+%26+Rule+Engine%22) and [M7.5 — Operator Console & Web Dashboard](../../../issues?q=is%3Aissue+milestone%3A%22M7.5+%E2%80%94+Operator+Console+%26+Web+Dashboard%22) and the [v0.2.0 release milestone](../../../issues?q=is%3Aissue+milestone%3A%22v0.2.0%22).
> **Source of features:** v0.1.0 pull-forward backlog + 7 dev.to community feedback features (#142-#148) + operator console web UI (M7.5, #149-#157) + 7 dev.to follow-up feedback issues (#158-#164).
> **Status:** M1-M3 tasks complete ✅ · **M4 complete ✅** (deny-storm #143, fetch guard #146, verification sink #144 — all closed, 100% module coverage, repo-wide 91.08%) · M5 in progress (Task 1 of 6 done ✅ — session replay #81) · M7.5 complete ✅

---

## Cross-Milestone Quality Bar (Every Milestone)

Every milestone — before it is declared complete — must pass ALL of the following. These are checked in the per-milestone Exit Gate.

| # | Gate item | Command / Evidence | Failure action |
|---|-----------|--------------------|----------------|
| 1 | **Code review** | At least one peer/self review pass on all code merged since the previous milestone | Reviewer sign-off recorded; no merge until addressed |
| 2 | **Test coverage > 90%** | `pytest --cov=agent_tooltrust --cov-fail-under=90` | Add tests for uncovered paths before exit |
| 3 | **Lint strict clean** | `ruff check . --select ALL` → 0 errors | Fix all warnings/errors before exit |
| 4 | **Mypy strict clean** | `mypy --strict` → 0 errors | Fix all type errors before exit |
| 5 | **Code comments** | Every new/edited `.py` file has module-level + function-level docstrings (Args/Returns/Raises) and inline comments where logic is non-obvious | Add before milestone finishes |
| 6 | **CI green** | Full `.github/workflows/ci.yml` run passes | Investigate and fix before exit |
| 7 | **Field-test gate** (M7+) | `tooltrust field-test` deterministic matrix green | No ship without green field tests |

> **Note on coverage:** the v0.1.0 exit gates required >95%. For v0.2.0 the floor is **>90%** at milestone close; final release target remains **>95%** (see M8).

---

## M1 — Policy Model & Rule Engine

**Objective:** Harden and extend the core policy layer. Ship argument-level validation (dev.to feedback), boolean rule composition, tool hiding per agent class, a shareable policy pack format, permit-with-obligation decisions (dev.to feedback), and hardened deny-explanation + premise-validation controls (dev.to follow-up feedback).

**GitHub milestone:** [M1 — Policy Model & Rule Engine](https://github.com/deghosal-2026/agent-tooltrust/milestone/5)
**Issues:** #88, #91, #93, #142, #147, #159, #160

### M1 Task Checklist

| # | Task | Feature ID | Issue | Verification |
|---|------|------------|-------|--------------|
| 1 | **Rule composition:** `and`/`or`/`not` operators + sub-entity grouping in policy rules | F-64 | #93 | ✅ Combined rules produce correct allow/deny decisions; truth-table unit tests pass (`tests/test_rule_composition.py`) |
| 2 | **Tool hiding:** policy marks tools `hidden: true` for specific agent classes; engine filters the capability list | F-83 | #88 | ✅ Admin sees full list; read-only agent sees only its permitted subset (`tests/test_tool_hiding.py`, `Engine.capabilities`) |
| 3 | **Policy pack format:** `tools.yaml` + `tests.yaml` schema; `tooltrust pack validate` + `tooltrust pack test` | F-61 | #91 | ✅ One-page contribution guide (`packs/README.md`); `pack validate`/`pack test` pass (`tests/test_pack.py`) |
| 4 | **Argument-level policy:** per-tool args schema (required fields, forbid-list, row limits, env allowlists) evaluated before allow/deny | dev.to (Kartik) | #142 | ✅ Delete with no/empty filter denied; disallowed env denied; unbounded row limit denied (`tests/test_argument_policy.py`) |
| 5 | **Permit-with-obligation:** extend decision outcome to `{allow, deny, allow_with_obligation}`; obligations enforced by the gatekeeper | dev.to (Skillselion) | #147 | ✅ First-use sign-off, auto-notify, signed audit entry fire even if agent does not cooperate (`tests/test_obligations.py`)
| 6 | **Configurable deny-reason exposure:** three tiers (`none`/`reason-only`/`detail`) for the deny/explain response; default `reason-only` so agents can replan without reverse-engineering the rule set | dev.to (suraj09) | #160 | ✅ Each tier returns expected rationale depth; `reason-only` omits rule IDs/thresholds/match tree (`tests/test_deny_exposure.py`) |
| 7 | **Premise/staleness validation:** catch schema-valid + permission-valid but semantically wrong calls (moved paths, wrong-tool-with-plausible-args); gate-side signal or audit-side tag | dev.to (mansio, tom_jones) | #159 | ✅ Canonical `read_file(path=<moved>)` case flagged/tagged; design doc captures schema-vs-correctness boundary (`tests/test_premise_validation.py`) |

### M1 Exit Gate

- [x] Code review passed on all M1 code (review recorded in session 2026-08-13)
- [ ] Test coverage > 90% — *M1 modules all ≥91% (argument_policy 98%, obligations 100%, pack 91%, models 96%, schema 99%); repo-wide total 86% — needs lift before M1 close*
- [x] Ruff clean (project config `ruff check src/ tests/` → 0 errors)
- [x] Mypy strict clean (`mypy --strict` → 0 errors, 76 files)
- [x] Code comments / docstrings added on all new `.py` files
- [ ] CI green — *pending workflow run on commit*

**Dependency:** v0.1.0 shipped engine + policy manager
**Produces:** deterministic, testable argument + rule + obligation engine for all later milestones

---

## M2 — Resource Scoping & Delegation

**Objective:** Enforce resource and environment boundaries. Confine agents to their declared scope (staging vs prod), prevent child-agent privilege escalation, and catch smuggled tool calls via the dispatcher parser.

**GitHub milestone:** [M2 — Resource Scoping & Delegation](https://github.com/deghosal-2026/agent-tooltrust/milestone/6)
**Issues:** #106, #108, #145

### M2 Task Checklist

| # | Task | Feature ID | Issue | Verification |
|---|------|------------|-------|--------------|
| 1 | **Resource/environment scoping:** resource-scoped identities + env tags; session scoped to an environment; default-deny on out-of-scope resolution | dev.to (Tae Kim) | #145 | ✅ Prod entity rejected from a staging-scoped session; cross-env attempt blocked and audited (`tests/test_scoping.py`, `SessionScope`, `DENY_OUT_OF_SCOPE`) |
| 2 | **Child-agent delegation:** `engine.delegate(child_id, parent, scope_subset)`; child scope ⊆ parent scope allowed, exceeding denied | F-88 | #108 | ✅ Subset allowed; superset denied; audit log shows delegation chain (`tests/test_delegation.py`, `DelegationManager`) |
| 3 | **Dispatcher parser:** parse `bash`/`aws`/`http` args to canonical `(tool, action, args)`; evaluate against same policy; unparseable → deny | F-87 | #106 | ✅ `git push --force` denied when `git.push` denied; unparseable input denied (`tests/test_dispatcher.py`, `DispatcherError`, `DENY_UNPARSEABLE_INPUT`) |

### M2 Exit Gate

- [x] Code review passed on all M2 code (reviewed with author in session 2026-08-13)
- [ ] Test coverage > 90% — *M2 modules 100% (scoping) / 100% (delegation) / 96% (dispatcher); repo-wide 86% — needs lift before M2 close*
- [x] Ruff strict clean (`ruff check src/ tests/` → 0 errors)
- [x] Mypy strict clean (`mypy --strict` → 0 errors, 79 files)
- [x] Code comments / docstrings added on all new `.py` files
- [ ] CI green — *pending workflow run on commit*

**Dependency:** M1 (policy model)
**Produces:** multi-environment-safe scoping + delegation invariant + smuggled-call detection

---

## M3 — Escalation & Human Approval

**Objective:** Build the human-in-the-loop escalation round-trip: create, track, approve/deny/expire escalations, bind approvals to the exact action identity, and block replay attempts.

**GitHub milestone:** [M3 — Escalation & Human Approval](https://github.com/deghosal-2026/agent-tooltrust/milestone/7)
**Issues:** #84, #85, #86, #95

### M3 Task Checklist

| # | Task | Feature ID | Issue | Verification |
|---|------|------------|-------|--------------|
| 1 | **EscalationManager:** create escalation, track status, bind to action_identity, enforce TTL; approve → execute, deny → agent gets deny | F-09, F-90 | #84 | ✅ Approve executes; deny blocks; expired TTL denies; engine registers escalations on `escalate` (`tests/test_escalation.py`, `engine/escalation.py`) |
| 2 | **CLI approve/deny:** `tooltrust approve <id>` / `tooltrust deny <id> [--reason]`; records approver + timestamp + reason | F-90 | #85 | ✅ CLI round-trip works; audit records approver, time, reason (`tests/test_escalation_cli.py`, `cli/escalation.py`) |
| 3 | **Action-identity binding:** escalate bound to `hash(tool, action, args)`; different args → `deny('action_identity_mismatch')` | F-09 | #86 | ✅ `action_identity(tool, action, args)` hash; `resolve()` denies `deny_action_identity_mismatch` on different args; approval TTL enforced |
| 4 | **Replay-attempt detection:** same `escalation_id` reused with a different call → deny | F-89(P1) | #95 | ✅ Already-resolved id → `deny_escalation_replay`/unknown; one attest per call (`EscalationManager.resolve|attest`) |

### M3 Exit Gate

- [ ] Code review passed on all M3 code — *EscalationManager + CLI done; pending full-milestone review*
- [x] Test coverage > 90% — *repo-wide 90.8% (≥90% bar); escalation engine 98%, CLI 99%*
- [x] Ruff strict clean (`ruff check src/ tests/` → 0 errors)
- [x] Mypy strict clean (`mypy --strict` → 0 errors, 81 files)
- [x] Code comments / docstrings added on all new `.py` files
- [ ] CI green — *pending workflow run on commit*

**Dependency:** M1 (policy model)
**Produces:** complete escalation round-trip with anti-replay guarantees

---

## M4 — Threat & Anomaly Detection

**Objective:** Make the gatekeeper actively defensive. Detect deny-storms / policy probing (dev.to feedback), guard arbitrary URL fetches (dev.to feedback), and verify agent outcomes against agent-unwritable external sinks (dev.to feedback).

**GitHub milestone:** [M4 — Threat & Anomaly Detection](https://github.com/deghosal-2026/agent-tooltrust/milestone/8)
**Issues:** #143, #144, #146

### M4 Task Checklist

| # | Task | Feature ID | Issue | Verification |
|---|------|------------|-------|--------------|
| 1 | **Deny-storm / probe detection:** async session-level analyzer (deny rate, consecutive denies, escalation frequency, tool-set entropy); throttle/lock/pause on threshold | dev.to (Skillselion, Igor) | #143 | ✅ Dense deny run triggers action; legit replan burst does not false-positive; entropy-based lock avoids replay-burst FPs (`tests/test_deny_storm.py`, `engine/deny_storm.py`, wired into `Engine` with opt-in enforcement) |
| 2 | **URL fetch category guard:** robots.txt enforced, PII stripped before context, redirect re-resolution against internal-address blocklist (RFC 1918, loopback, link-local, cloud metadata) | dev.to (iwasinnam2) | #146 | ✅ robots.txt obeyed; PII removed; SSRF redirect to internal address blocked incl. protocol-relative `//169.254.169.254` bypass (`tests/test_fetch_guard.py`, `engine/fetch_guard.py`) |
| 3 | **External verification sink:** read-only hooks to agent-unwritable systems (API counters, VCS state, billing snapshots); diff against self-report | dev.to (473185670, Edu) | #144 | ✅ False "completed" report caught; commit verified against VCS (GitHook, read-only); self-critique checked externally (`tests/test_verify_sink.py`, `engine/verify.py`) |

### M4 Exit Gate

- [x] Code review passed on all M4 code — *self-review + dispatched reviewer; 1 critical (SSRF `//` redirect bypass) + 3 important/minor findings fixed before close*
- [x] Test coverage > 90% — *deny_storm 100%, fetch_guard 100%, verify 100%; repo-wide 91.08% (≥90% bar)*
- [x] Ruff strict clean (`ruff check src/ tests/` → 0 errors)
- [x] Mypy strict clean (`mypy --strict` → 0 errors, 90 files)
- [x] Code comments / docstrings added on all new `.py` files
- [ ] CI green — *pending workflow run on push*

**Dependency:** M1 (policy model), M3 (escalation)
**Produces:** probing/fatigue protection, safe fetch, ground-truth verification

---

## M5 — Audit, Verification & Observability

**Objective:** Make the audit log trustworthy and usable: replayable session state, cross-session policy analytics (dev.to feedback), fleet/control-plane integration for observability, and audit redaction + calibration + credential-freshness hardening (dev.to follow-up feedback).

**GitHub milestone:** [M5 — Audit, Verification & Observability](https://github.com/deghosal-2026/agent-tooltrust/milestone/9)
**Issues:** #81, #112, #148, #158, #161, #162

### M5 Task Checklist

| # | Task | Feature ID | Issue | Verification |
|---|------|------------|-------|--------------|
| 1 | **Session replay from audit:** `tooltrust audit session --replay <id>` reconstructs session state from audit entries | F-08d | #81 | ✅ Replays cumulative risk identical to live `SessionStore` (shared `session_risk_increment` in `engine/explain`); empty session → zero risk; ordering stable across sinks (`tests/test_audit_replay.py`; `audit/replay.py`). Integrity: sinks persist `chain_hash`/`prev_hash` at write time; `audit verify` + `audit session` recompute links and fail loudly (exit 1) on modified/missing/unchained entries (`tests/test_governance.py`, `tests/test_audit_cli.py`, `audit/tamper_proof.py`) |
| 2 | **AgentControlPlane + MCP-Data integration:** ToolTrust PDP service for fleet manager + MCP-Data connector for per-data-source authorization | — | #112 | Integration tests pass end-to-end |
| 3 | **Session-to-session policy analytics:** batch analyzer over audit + traces — correlate deny patterns, flag deny→allow transitions, surface dead/over-hit rules | dev.to (Igor) | #148 | Recurring benign needs surfaced; suspicious transitions flagged |
| 4 | **Audit redaction:** sink-level redaction of PII/secrets in audit-mode (and all) decisions; default deny-list + `args.redact` override; `redacted: true` flag | dev.to (mansio) | #158 | Secrets never appear in persisted log; nested args covered (`tests/test_audit_redaction.py`) |
| 5 | **Stale-credential classification:** distinct audit tag for allowed-but-credential-rejected calls, separate from `not-available`; design note on call-time credential resolution | dev.to (cailab) | #161 | Stale-credential failure classified distinctly and queryable (`tests/test_stale_credential.py`) |
| 6 | **Score calibration + shadow mode:** counterfactual threshold logging, human-reversal capture, false-allow/false-escalate rates by tool/env/data class, shadow-mode replay against production distribution | dev.to (russlanramdowar) | #162 | Calibration report/API surfaces rates; counterfactual logged per decision |

### M5 Exit Gate

- [ ] Code review passed on all M5 code
- [ ] Test coverage > 90%
- [ ] Ruff strict clean
- [ ] Mypy strict clean
- [ ] Code comments / docstrings added on all new `.py` files
- [ ] CI green

**Dependency:** M4 (verification sink), M2 (scoping)
**Produces:** replayable audit, fleet observability, policy-learning analytics

---

## M6 — Service & Fleet Access

**Objective:** Expose ToolTrust beyond Python: an HTTP authorization service, a community policy pack catalog, distributed policy sync across fleet instances, and a fleet deployment guide.

**GitHub milestone:** [M6 — Service & Fleet Access](https://github.com/deghosal-2026/agent-tooltrust/milestone/10)
**Issues:** #97, #111, #119, #120

### M6 Task Checklist

| # | Task | Feature ID | Issue | Verification |
|---|------|------------|-------|--------------|
| 1 | **HTTP /authorize service:** FastAPI `POST /authorize` accepting JSON tool call → Decision JSON | F-43 | #97 | Endpoint returns correct Decision JSON; malformed input → 4xx |
| 2 | **Policy packs catalog:** community packs listed in `packs/` with metadata, domains, tool count, tests_passing, last_updated | F-61 | #111 | 5+ packs in catalog; metadata accurate |
| 3 | **Distributed policy sync — OPAL:** policy change pushed to all PDP instances within 5s; 3-instance fleet test; `tooltrust policy rollback --version <v>` | — | #119 | Change propagates <5s; rollback works |
| 4 | **Fleet deployment guide:** deployment topology, OPAL config, monitoring, scaling | — | #120 | Complete, reproducible guide committed |

### M6 Exit Gate

- [ ] Code review passed on all M6 code
- [ ] Test coverage > 90%
- [ ] Ruff strict clean
- [ ] Mypy strict clean
- [ ] Code comments / docstrings added on all new `.py` files
- [ ] CI green

**Dependency:** M5 (fleet observability)
**Produces:** language-agnostic access, shareable packs, fleet-wide sync + deployment guidance

---

## M7 — Compliance & Security Baselines

**Objective:** Reach security completeness: OWASP Agentic Top 10 10/10, ToolTrust Hardened + Certified baselines, and OpenSSF Gold assessment.

**GitHub milestone:** [M7 — Compliance & Security Baselines](https://github.com/deghosal-2026/agent-tooltrust/milestone/11)
**Issues:** #103, #114, #115, #121

### M7 Task Checklist

| # | Task | Feature ID | Issue | Verification |
|---|------|------------|-------|--------------|
| 1 | **ToolTrust Hardened baseline:** `tooltrust baseline check hardened` → all items pass; checklist verified | — | #103 | Hardened checklist fully verified; self-service compliance unlocked |
| 2 | **OWASP 10/10 final audit:** all 10 Agentic Top 10 risks covered; SECURITY.md with 10/10 coverage map | — | #114 | Coverage map complete; A03 covered by output inspection |
| 3 | **ToolTrust Certified baseline:** hardened + tamper-evident + output inspection + external review; `tooltrust baseline check certified` | — | #115 | Certified checklist verified; external-review ready |
| 4 | **OpenSSF Gold assessment:** all Gold criteria with 2+ independent reviewers; badge or documented path to Gold | — | #121 | Gold badge achieved or documented path |

### M7 Exit Gate

- [ ] Code review passed on all M7 code
- [ ] Test coverage > 90%
- [ ] Ruff strict clean
- [ ] Mypy strict clean
- [ ] Code comments / docstrings added on all new `.py` files
- [ ] CI green
- [ ] **Field-test gate:** deterministic `tooltrust field-test` matrix green

**Dependency:** all prior milestones
**Produces:** OWASP 10/10, Hardened + Certified baselines, OpenSSF Gold posture

---

## M7.5 — Operator Console & Web Dashboard

> **Milestones covered:** M7.5 — a parallel milestone (GH #13) that surfaces the
> operator console web UI across v0.2.0. It is *not* a phase of M1-M8; it runs
> alongside them, mounting pages that read the features M1-M7 already produce.
> **Status: Complete ✅** (all 9 issues #149-#157 closed; suites + UI E2E + docker green)
> **UI test plan:** [docs/test/web-ui-test-plan.md](../../../docs/test/web-ui-test-plan.md)

**Objective:** Every decision ToolTrust makes is machine-auditable; M7.5 makes it
*humanly* inspectable. The operator console is a single-page web app mounted on
ServerCore that lets a human reviewer see pending escalations and respond, browse
the audit trail, drill into a session's decision chain, and read policy/compliance
analytics — without touching a terminal.

The UI is a **read-plus-one-action** surface: it reads what the engine records
(everything) and performs exactly one write action per surface (approve/deny an
escalation). It never re-authorizes or bypasses policy; the engine remains the
single enforcement point. The UI is a release gate: no green Playwright sweep,
no committed screenshots, no v0.2.0 ship.

### M7.5 Cross-Milestone Quality Bar

| # | Gate item | Command / Evidence | Failure action |
|---|-----------|--------------------|----------------|
| 1 | **API contract tests pass** | `pytest` on `tests/test_ui_api*.py` (A1-A7) | Fix before exit |
| 2 | **Playwright E2E green** | `playwright test` (C1-C5, E1-E4, J1-J6) | Fix before exit |
| 3 | **Screenshots committed** | `docs/reference/ui-*.png` regenerated + committed | Regenerate before exit |
| 4 | **Backend suite green** | `pytest` + `ruff` + `mypy --strict` still pass | Reconcile before exit |
| 5 | **No console errors / axe clean** | Playwright collects page errors + a11y smoke | Fix before exit |

### M7.5 Task Checklist

| # | Task | Issue | API surface | UI plan ref | Verification |
|---|------|-------|-------------|-------------|--------------|
| 1 | **Operator console shell & nav** — SPA shell on ServerCore, nav across Escalations/Audit/Sessions/Analytics/Baselines, decision-colored badges, tables, filter bar, loading/empty/error states | #149 | mounts the other pages | C1, E1-E4 | Nav reaches every surface; empty/loading/backend-down states render without JS errors |
| 2 | **Escalation approval page** — list pending escalations; approve (action-identity bound) / deny (with reason); expired shown as deny | #150 | `GET /api/escalations`, `POST /api/escalations/<id>/approve`, `POST .../deny` | C2, J1-J4 | Approve executes only for matching action_identity; deny recorded; expired → deny |
| 3 | **Audit event viewer page** — filterable/searchable audit entries with decision badges | #151 | `GET /api/audit` | C3, A4 | Filter by decision/session/agent; empty → `[]`; badges rendered per contract |
| 4 | **Session inspection page** — replay a session's decision chain (cumulative risk at each call); surface delegations/approvals | #152 | `GET /api/sessions/<id>` | C4, J5 | Timeline reproduces identical cumulative risk at each call (F-08d) |
| 5 | **Policy analytics page** — M5 session analytics (#148) + M4 deny-storm/probe alerts (#143) | #153 | `GET /api/analytics` | analytics tiles | Deny patterns, deny→allow transitions, dead/over-hit rules, alerts surfaced |
| 6 | **Compliance & baseline page** — ToolTrust tiers, OWASP 10/10 map, OpenSSF status | #155 | `GET /api/baselines` | C5, A6 | Tier/status reflect `tooltrust baseline check` |
| 7 | **Playwright E2E + screenshots** — suite over `docs/test/web-ui-test-plan.md`; capture `docs/reference/ui-*.png` into guides; `ui` CI job | #154 | — | full plan | Release gate: green sweep + committed screenshots for v0.2.0 |
| 8 | **Docker hosting for the operator console** — one image serving server + `/audit` + `/api/escalations` + dashboard; persisted `~/.tooltrust` volume; healthcheck covers `/audit/health` + `/api/escalations`; documented `docker compose` | #156 | mounts escalation + audit + dashboard | A1-A7 | `docker compose up --wait` serves console; state survives restart; healthcheck green |
| 9 | **Containerized test execution** — build the image, start it, run the API contract + smoke suite against the live container (`test_escalation_routes.py`, `test_audit_routes.py`); `docker` CI job | #157 | — | A1-A7 | `/api/escalations` + `/audit` return correct JSON through the network; approve/deny round-trip works in-container; CI docker job green |

### M7.5 Exit Gate

- [x] All 9 tasks implemented and their verifications pass
- [x] API contract tests (A1-A7) green — `test_escalation_routes.py`, `test_audit_routes.py`, `test_console_api.py`
- [x] Playwright component + journey tests (C1-C5, J1-J6) green — `tests/ui/test_dashboard_e2e.py`
- [x] Empty/loading/error states (E1-E4) pass, no console errors, a11y smoke clean
- [x] Screenshots S1-S5 committed and referenced in `docs/reference/` guides — `ui-dashboard.png`, `ui-audit.png`
- [x] Backend suite (`pytest`, `ruff`, `mypy --strict`) remains green
- [x] Docker console builds and serves; `~/.tooltrust` volume persists state
- [x] Containerized API + smoke tests pass in the `docker` CI job
- [x] `ui` CI job added and green
- [x] Issues #149-#157 closed with commit/screenshot references — **all 9 closed ✅**

**Dependency:** M1-M7 engine/audit/policy surfaces (read-only), M3 escalation
(#84-#86, #95)
**Produces:** a human-reviewable operator console + a Playwright release gate

---

## M8 — Quality Gates, Field Tests & Release

**Objective:** Prove the whole release. Run every per-milestone exit gate review, complete full field test sweeps (v0.1+v0.2+v0.3 scenarios on all 10 agents), harden to >95% coverage, and ship v0.2.0 to PyPI + GitHub.

**GitHub milestone:** [M8 — Quality Gates, Field Tests & Release](https://github.com/deghosal-2026/agent-tooltrust/milestone/12)
**Issues:** #83, #89, #100, #101, #104, #107, #110, #113, #116, #122, #163, #164

### M8 Task Checklist — Exit Gates

| # | Exit gate | Covers | Issue | Verification |
|---|-----------|--------|-------|--------------|
| 1 | **Session state exit gate** | Review + coverage + lint on session state work | #83 | Code review, >90% coverage, ruff+mypy, comments |
| 2 | **Escalation + scan exit gate** | Escalation round-trip, action-identity binding, scanner 10/10, tool hiding | #89 | All sub-verifications pass |
| 3 | **CI + rate + SWE-bench exit gate** | CI policy suite catches drift, SWE-bench 5 tasks, HTTP /authorize, OTel spans | #100 | All pass |
| 4 | **Output + dispatch exit gate** | Output inspector, dispatcher parsing, OWASP A03 | #107 | All pass |
| 5 | **Delegation + audit exit gate** | Subset invariant, verifiable/falsifiable audit chain, OWASP A08 | #110 | All pass |
| 6 | **Packs + integration exit gate** | 5+ packs in catalog, AgentControlPlane+MCP-Data integration | #113 | All pass |

### M8 Task Checklist — Field Tests, Hardening, Ship

| # | Task | Feature ID | Issue | Verification |
|---|------|------------|-------|--------------|
| 7 | **v0.2 field test sweep:** v0.1 matrix + v0.2 scenarios (session risk escalation, argument bypass, escalation round-trip, tool scanning) on all 10 agents | F-75 | #101 | Field test report green |
| 8 | **v0.3 full regression:** all v0.1+v0.2+v0.3 scenarios on all 10 agents | F-75 | #116 | Full regression green |
| 9 | **v0.2.0 hardening:** code review, >95% coverage, ruff strict, mypy strict, CHANGELOG | — | #104 | Coverage >95%; lint clean; changelog committed |
| 10 | **v0.2.0 field test sweep + ship:** full regression on 10 agents, CHANGELOG v0.2.0, PyPI publish, GitHub release | — | #122 | Release live on PyPI + GitHub |
| 11 | **Adversarial field-test sweep:** adversarial parameter payloads + retry sequences added to the 10-agent matrix | dev.to (russlanramdowar) | #163 | Adversarial scenario pack committed; CI gate green |
| 12 | **Discriminative-power field tests:** scenarios the gate cannot pass by construction, measured against realized outcomes | dev.to (473185670) | #164 | >=1 pending-discriminative scenario committed + green |

### M8 Exit Gate (Release Gate)

- [ ] All six per-milestone exit gates (#83, #89, #100, #107, #110, #113) closed
- [x] M7.5 exit gate closed — Playwright E2E green, screenshots committed, docker console serving (#149-#157)
- [ ] Code review passed on all code merged since v0.1.0
- [ ] Test coverage **> 95%** (final release bar)
- [ ] Ruff strict clean (0 errors on `--select ALL`)
- [ ] Mypy strict clean (0 errors)
- [ ] Code comments / docstrings on every `.py` file
- [ ] Field test sweep green (all 10 agents, all scenarios)
- [ ] CHANGELOG.md v0.2.0 entry committed
- [ ] Release notes `docs/reference/release-notes-v0.2.0.md` committed
- [ ] PyPI publish succeeds
- [ ] GitHub release created with tag `v0.2.0`

**Dependency:** M1-M7 (all prior milestones), M7.5 (operator console release gate)
**Produces:** Shipped v0.2.0 — hardenable, verifiable, fleet-ready, OWASP 10/10, OpenSSF Gold

---

## Release Readiness — v0.2.0 Final Steps

Run **after** M8's Release Gate, immediately before and after the tag `v0.2.0`.

| # | Step | Owner | Evidence |
|---|------|-------|----------|
| 1 | **Final full test sweep:** `uv run pytest` (unit + integration) | Maintainer | All tests green; CI green on `rel-0.2.0` |
| 2 | **Final field-test sweep:** `tooltrust field-test` on all 10 agents, Plan A + B | Maintainer | Report green; `FIELD_TEST_REPORT.md` regenerated |
| 3 | **Coverage final check:** `pytest --cov=agent_tooltrust --cov-fail-under=95` | Maintainer | >95% confirmed |
| 4 | **Lint + type final check:** `ruff check . --select ALL` + `mypy --strict` | Maintainer | 0 errors each |
| 5 | **Docstring/comment sweep:** every `.py` file has module + function docstrings | Reviewer | Review pass recorded |
| 6 | **Documentation review:** README, quickstart, API reference, release notes, SECURITY.md, SECURITY_BASELINE.md all current for v0.2.0 | Reviewer | No stale references; OWASP 10/10 map; baseline tiers documented |
| 7 | **CHANGELOG v0.2.0:** features, fixes, known limitations, upgrade notes | Maintainer | Keep-a-Changelog format |
| 8 | **Version bump:** `pyproject.toml` → `0.2.0` | Maintainer | `uv build` produces `agent_tooltrust-0.2.0` wheel |
| 9 | **PyPI publish (trusted publishing):** `uv publish` with Sigstore signing | Maintainer | `pip install agent-tooltrust` installs v0.2.0 in clean venv |
| 10 | **GitHub release:** tag `v0.2.0` + release notes + wheel artifact | Maintainer | Release visible on GitHub |
| 11 | **Branch merge:** merge `rel-0.2.0` → `main` | Maintainer | PR merged; main green |
| 12 | **Post-release verification:** smoke-install in clean venv, run `tooltrust` CLI, run one demo scenario | Maintainer | Smoke test passes |
| 13 | **Community feedback loop:** reply to all dev.to comments; link shipped issues #142-#148 and #158-#164 in replies | Maintainer | Threads closed/acknowledged |

---

## Cross-Version Success Metrics

| Metric | v0.1 Target | v0.2 Target |
|--------|-------------|-------------|
| PRD features shipped | 35+ P0 + 13 enhancements | All M1-M8 tasks (#81-#122) + 7 dev.to features (#142-#148) + operator console M7.5 (#149-#157) + 7 dev.to follow-ups (#158-#164) |
| CUJs covered | 1-9, 11 (10 CUJs) | + CUJ 10 (escalation round-trip) |
| Test coverage | >95% (release) | >90% per milestone, >95% at release |
| Ruff / Mypy | strict clean | strict clean every milestone |
| OWASP Agentic Top 10 | 9/10 | 10/10 |
| OpenSSF Badge | Silver | Gold |
| ToolTrust Baseline | Essential | Hardened + Certified |
| Fleet support | — | OPAL sync, fleet guide, HTTP /authorize |
| Operator console | — | M7.5 web dashboard (#149-#157): escalations, audit, sessions, analytics, baselines; Docker + `ui`/`docker` CI jobs |
| Field test | Plan A 83/83, Plan B 116/123 | All v0.1+v0.2+v0.3 scenarios + adversarial (#163) + discriminative-power (#164) green on 10 agents |
