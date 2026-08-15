# Session-to-Session Policy Analytics

**Version:** 1.0 (Approved)
**Date:** 2026-08-14
**Status:** Approved
**Issue:** [agent-tooltrust #148](https://github.com/anomalyco/agent-tooltrust/issues/148)

## Problem

The gatekeeper generates deny→allow signal across sessions, but nothing turns that signal into learned policy insights: recurring benign needs stay denied, suspicious transitions go unnoticed, and dead or over-hit rules are invisible to operators.

## Design Decisions

- **Surface:** HTTP endpoint (`GET /api/analytics/sessions`) + CLI (`tooltrust analytics sessions`).
- **Architecture:** A pure analyzer module with no server dependency, called by both the route and the CLI.
- **No state:** The analyzer runs on-demand against the current audit log and policy. It is deterministic and idempotent.

## Architecture & Components

### 1. `src/agent_tooltrust/analytics/session_analyzer.py`

Pure analysis module. Imports `AuditEntry` and `Rule` types — no server or FastMCP dependency.

**Dataclasses:**

```python
@dataclass(frozen=True)
class RecurringDenial:
    context: tuple[str, str, str, str, str]  # (tool, action, env, data_class, agent)
    deny_count: int
    sample_reason: str

@dataclass(frozen=True)
class DenyToAllowTransition:
    context: tuple[str, str, str, str, str]
    first_deny_at: str
    first_allow_at: str

@dataclass(frozen=True)
class DeadRule:
    rule_index: int
    decision: str
    tool: str
    action: str
    environment: str
    data_class: str
    reason: str

@dataclass(frozen=True)
class OverHitRule:
    reason_code: str
    match_count: int
    percentile: float

@dataclass(frozen=True)
class AnalyticsFindings:
    recurring_denials: list[RecurringDenial]
    deny_to_allow_transitions: list[DenyToAllowTransition]
    dead_rules: list[DeadRule]
    over_hit_rules: list[OverHitRule]
```

**Function:**

```python
def analyze(
    entries: list[AuditEntry],
    policy: Policy | None = None,
    min_denials: int = 3,
) -> AnalyticsFindings
```

### 2. `server/analytics_routes.py` (extend)

Add `GET /api/analytics/sessions` to the existing route registrar. Accepts optional `?min_denials=3` query param. Calls the analyzer with the full audit log and the engine's policy. Returns the `AnalyticsFindings` as JSON.

### 3. `cli/analytics.py` (new)

`tooltrust analytics sessions [--min-denials 3] [--json]` subcommand. Loads entries from the default audit sink (jsonl/sqlite/postgres), creates an engine from the policy path, runs the analyzer, and prints findings. `--json` outputs raw JSON for piping.

## Data Flow

1. Operator calls `GET /api/analytics/sessions` or `tooltrust analytics sessions`.
2. The auditor loads all audit entries via `core.audit_logger.query(None)`.
3. The analyzer groups entries by `(tool, action, env, data_class, agent)` identity tuple.
4. For each group:
   - Count denials vs allows → recurring denial detection (denials ≥ min_denials, no allows).
   - Sort by timestamp, scan deny→allow → transition detection.
5. For the policy (if available), compare `reason_code` from entries against `rule.reason` → dead rules.
6. Count matches per `reason_code`, compute percentiles → over-hit rules.
7. Return structured `AnalyticsFindings`. JSON is serialized as dict with typed arrays.

## Error Handling

- Empty audit log → empty findings (all fields are empty lists, not errors).
- Policy not available → `dead_rules` is empty list (analysis proceeds without it).
- Corrupted or unparseable entry → the entry is skipped with a warning (fail open for analysis).
- Minimum denials threshold clamped to ≥ 1.

## Acceptance Criteria

- Recurring benign needs (≥3 denials on same context, no allow) are surfaced.
- Same-context deny→allow transitions are flagged with timestamps.
- Dead rules (policy rules that never matched) are reported.
- Over-hit rules (rules above 90th percentile by match count) are reported.
- CLI and HTTP endpoint return consistent results for the same audit log.

## Out of Scope

- Persistent storage of findings or history — analysis is run-on-demand.
- Automatic policy modification or "remediation" — findings are advisory.
- Real-time streaming analysis — batch-only for v0.2.