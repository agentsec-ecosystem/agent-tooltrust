# WBS — Agent ToolTrust M7.5: Operator Console & Web Dashboard

> **Milestones covered:** M7.5 — a parallel milestone (GH #13) that surfaces the
> operator console web UI across v0.2.0. It is *not* a phase of M1-M8; it runs
> alongside them, mounting pages that read the features M1-M7 already produce.
> **Issue tracking:** `#149`-`#155` in GitHub Milestone
> [M7.5 — Operator Console & Web Dashboard](../../../issues?q=is%3Aissue+milestone%3A%22M7.5+%E2%80%94+Operator+Console+%26+Web+Dashboard%22).
> **UI test plan:** [docs/test/web-ui-test-plan.md](../../../docs/test/web-ui-test-plan.md)

---

## Vision

Every decision ToolTrust makes is machine-auditable; M7.5 makes it *humanly*
inspectable. The operator console is a single-page web app mounted on
ServerCore that lets a human reviewer see pending escalations and respond,
browse the audit trail, drill into a session's decision chain, and read
policy/compliance analytics — without touching a terminal.

The UI is a **read-plus-one-action** surface: it reads what the engine records
(everything) and performs exactly one write action per surface (approve/deny an
escalation). It never re-authorizes or bypasses policy; the engine remains the
single enforcement point. The UI is a release gate: no green Playwright sweep,
no committed screenshots, no v0.2.0 ship.

---

## Cross-Milestone Quality Bar

| # | Gate item | Command / Evidence | Failure action |
|---|-----------|--------------------|----------------|
| 1 | **API contract tests pass** | `pytest` on `tests/test_ui_api*.py` (A1-A7) | Fix before exit |
| 2 | **Playwright E2E green** | `playwright test` (C1-C5, E1-E4, J1-J6) | Fix before exit |
| 3 | **Screenshots committed** | `docs/reference/ui-*.png` regenerated + committed | Regenerate before exit |
| 4 | **Backend suite green** | `pytest` + `ruff` + `mypy --strict` still pass | Reconcile before exit |
| 5 | **No console errors / axe clean** | Playwright collects page errors + a11y smoke | Fix before exit |

---

## M7.5 Task Checklist

| # | Task | Issue | API surface | UI plan ref | Verification |
|---|------|-------|-------------|-------------|--------------|
| 1 | **Operator console shell & nav** — SPA shell on ServerCore, nav across Escalations/Audit/Sessions/Analytics/Baselines, decision-colored badges, tables, filter bar, loading/empty/error states | #149 | mounts the other pages | C1, E1-E4 | Nav reaches every surface; empty/loading/backend-down states render without JS errors |
| 2 | **Escalation approval page** — list pending escalations; approve (action-identity bound) / deny (with reason); expired shown as deny | #150 | `GET /api/escalations`, `POST /api/escalations/<id>/approve`, `POST .../deny` | C2, J1-J4 | Approve executes only for matching action_identity; deny recorded; expired → deny |
| 3 | **Audit event viewer page** — filterable/searchable audit entries with decision badges | #151 | `GET /api/audit` | C3, A4 | Filter by decision/session/agent; empty → `[]`; badges rendered per contract |
| 4 | **Session inspection page** — replay a session's decision chain (cumulative risk at each call); surface delegations/approvals | #152 | `GET /api/sessions/<id>` | C4, J5 | Timeline reproduces identical cumulative risk at each call (F-08d) |
| 5 | **Policy analytics page** — M5 session analytics (#148) + M4 deny-storm/probe alerts (#143) | #153 | `GET /api/analytics` | analytics tiles | Deny patterns, deny→allow transitions, dead/over-hit rules, alerts surfaced |
| 6 | **Compliance & baseline page** — ToolTrust tiers, OWASP 10/10 map, OpenSSF status | #155 | `GET /api/baselines` | C5, A6 | Tier/status reflect `tooltrust baseline check` |
| 7 | **Playwright E2E + screenshots** — suite over `docs/test/web-ui-test-plan.md`; capture `docs/reference/ui-*.png` into guides; `ui` CI job | #154 | — | full plan | Release gate: green sweep + committed screenshots for v0.2.0 |

---

## M7.5 Exit Gate

- [ ] All 7 tasks implemented and their verifications pass
- [ ] API contract tests (A1-A7) green
- [ ] Playwright component + journey tests (C1-C5, J1-J6) green
- [ ] Empty/loading/error states (E1-E4) pass, no console errors, a11y smoke clean
- [ ] Screenshots S1-S5 committed and referenced in `docs/reference/` guides
- [ ] Backend suite (`pytest`, `ruff`, `mypy --strict`) remains green
- [ ] `ui` CI job added and green
- [ ] Issues #149-#155 closed with commit/screenshot references

**Dependency:** M1-M7 engine/audit/policy surfaces (read-only), M3 escalation
(#84-#86, #95)
**Produces:** a human-reviewable operator console + a Playwright release gate