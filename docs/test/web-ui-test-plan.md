# M7.5 UI Test Plan — Operator Console / Web Dashboard

> **Milestone:** M7.5 (Operator Console & Web Dashboard) — [wbs-v0.2.0.md](../../wbs/v0.2.0/wbs-v0.2.0.md)
> **Backend:** `server/` (ServerCore + audit sinks + EscalationManager) | **E2E driver:** Playwright
> **Status:** Draft v1 — pending review

---

## 1. Objective

Validate the web operator console end to end: every page renders from real
backend state, every interactive action (approve/deny an escalation, filter
audit rows, drill into a session) round-trips correctly, and the UI is
defensible for release. A Playwright sweep also **captures screenshots** of
each page for the user guides.

This is a **release gate**: no green UI sweep, no v0.2.0 ship.

### Scope

| In scope | Out of scope (this plan) |
|----------|--------------------------|
| Dashboard shell + nav | Adapter datasource UIs |
| Escalation review (pending/approve/deny/expired) | Policy editors |
| Audit event viewer (list/search/filter) | Workspace/compliance white-label themes |
| Session inspection (decision chain replay) | Mobile-native UX (responsive only) |
| Baseline & compliance status tiles | OTel / tracing dashboards (separate plan) |
| Playwright screenshot capture → user guides | Performance load testing |

---

## 2. Test Environments & Tooling

| Layer | Tool | Notes |
|-------|------|-------|
| E2E browser | **Playwright** (Python) | Chromium + Firefox headless in CI; local headed for review |
| HTTP/API | HTTPX / `requests` against ServerCore | Backend contract tests |
| Backend fixtures | `tests/fixtures/` + seeded audit/escalation data | Deterministic, reproducible |
| Screenshots | Playwright `page.screenshot()` → `docs/reference/*.png` | Re-generated at release |
| CI | GitHub Actions `ui` job | Separate job from `test`/`docker` |

---

## 3. Test Strategy

Four layers, in order:

1. **API contract tests** (pytest + HTTPX) — each `/api/...` endpoint returns the
   documented shape and status codes; independent of the browser.
2. **Component tests** (Playwright test project over a seeded ServerCore) —
   render + core interactions per page.
3. **Empty/error/loading states** — every page verifies zero-state, loading,
   and backend-down (fail-closed) rendering.
4. **E2E journey tests** (Playwright) — cross-surface workflows: can a human
   review an escalation and see the audit entry reflect it?

Screenshots are a by-product of the E2E project (step 4), captured at a fixed
viewport for the guides.

---

## 4. Test Matrix

### 4.1 API contract tests

| # | Endpoint | Method | Verify |
|---|----------|--------|--------|
| A1 | `/api/escalations` | GET | List pending; shape: id, tool, action, agent, environment, reason, created, ttl, status |
| A2 | `/api/escalations/<id>/approve` | POST | 200 + status approved; 404 unknown id; 409 if already resolved |
| A3 | `/api/escalations/<id>/deny` | POST | 200 + denied w/ reason; 404 unknown; 409 already resolved |
| A4 | `/api/audit` | GET | Entries; filter by decision/session/agent; empty → `[]` |
| A5 | `/api/sessions/<id>` | GET | Decision chain + cumulative risk; 404 unknown |
| A6 | `/api/baselines` | GET | Baseline tiers status |
| A7 | malformed input | e.g. bad JSON, bad id | 4xx, never 500 |

### 4.2 Component tests (per page)

| # | Page | Render | Interaction |
|---|------|--------|-------------|
| C1 | Dashboard shell | nav to all surfaces; active state | navigate each tab |
| C2 | Escalations | pending list renders tool/agent/reason/TTL | approve → moves to resolved; deny → resolves; expired shown as deny |
| C3 | Audit | rows with decision badges | filter by decision; paginate; search |
| C4 | Sessions | timeline per session | select audit row → session drill-down shows chain |
| C5 | Baselines | tier tiles (Essential/Hardened/Certified), OWASP 10/10, OpenSSF | refresh status |

### 4.3 Empty / error / loading states

| # | Condition | Verify |
|---|-----------|--------|
| E1 | No escalations | empty-state message, no JS errors |
| E2 | No audit entries | empty-state message |
| E3 | Backend down | fail-closed banner + retry, never stale data shown as live |
| E4 | Slow API | loading indicator, no flash-of-stale |

### 4.4 E2E journeys (human reviewer)

| # | Journey | Verify |
|---|---------|--------|
| J1 | Agent call escalates → reviewer sees it → approves → agent resumes | escalation resolved; audit entry has approver + bound action_identity |
| J2 | Reviewer denies with reason | denial recorded in audit; agent gets deny |
| J3 | Replay attempt: same escalation_id, different args | denied (`action_identity_mismatch`); flagged in audit |
| J4 | Expired approval treated as deny | UI shows expired → deny outcome |
| J5 | Session drill-down: replay matches audit per-call | cumulative risk identical at each call |
| J6 | Decision badge colour fidelity | allow/audit/escalate/deny rendered per CSS contract |

### 4.5 Screenshot capture (user guides)

| # | Page | Target file |
|---|------|-------------|
| S1 | Dashboard home | `docs/reference/ui-dashboard.png` |
| S2 | Escalations (pending) | `docs/reference/ui-escalations.png` |
| S3 | Audit viewer | `docs/reference/ui-audit.png` |
| S4 | Session drill-down | `docs/reference/ui-session.png` |
| S5 | Baselines / compliance | `docs/reference/ui-baselines.png` |

Screenshots seeded with the deterministic fixture dataset and a fixed 1440×900
viewport. Each is wired into the matching guide (`docs/reference/quickstart.md`) with an
`![alt](./ui-*.png)` reference.

---

## 5. Ordering & CI Integration

Proposed CI job (`ui`):

```yaml
uv sync --group dev --group ui     # includes Playwright
uv run pytest       # unit + API contract (existing suites stay green)
uv run playwright install --with-deps
uv run playwright test             # component + E2E + screenshots
```

- API contract tests run in the existing `test` job (no browser needed).
- Component/E2E/screenshot run in a dedicated `ui` job (browser deps).
- Screenshots are regenerated and diff-oversight: any page-anatomy change on a
  guide page fails the sweep until the guide image is refreshed.

### Exit criteria (M7.5 gate)

- [ ] A1–A7 API contract tests pass
- [ ] C1–C5 component tests pass
- [ ] E1–E4 empty/error/loading states pass
- [ ] J1–J6 journey tests pass
- [ ] S1–S5 screenshots regenerated and committed
- [ ] No console errors; axe-style accessibility smoke clean
- [ ] Existing suites (unit + audit + field) stay green

---

## 6. Reporting

- Playwright HTML report is a CI artifact.
- A concise `docs/test/web-ui-test-report-v1.md` records: pass/fail matrix,
  screenshot set, and any leftover state (tracked as issues, e.g. `#<id>`).