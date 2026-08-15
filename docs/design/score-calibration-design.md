# Score Calibration & Shadow Mode

**Version:** 1.0 (Approved)
**Date:** 2026-08-14
**Status:** Approved
**Issue:** [agent-tooltrust #162](https://github.com/anomalyco/agent-tooltrust/issues/162)

## Problem

The scoring model needs calibration — operators don't know if thresholds are too strict or too loose, and there's no feedback loop between decisions and human outcomes.

## Design

Four pieces in one implementation:

### 1. Counterfactual Threshold

Add `counterfactual: float` to `Decision` and `AuditEntry`. Computed as the nearest band boundary (0.25, 0.5, 0.75) that would change the decision. For score-based decisions (allow/audit/escalate), this is the boundary between the current band and the next higher or lower band. For rule-based deny decisions, `counterfactual` is `None`.

### 2. Human Reversal Tracking

Escalation approve/deny already records an `approver` on the escalation entry. Calibration uses the escalation outcome to classify each escalated decision as:
- `false_escalate` — engine escalated, human approved (engine was too strict)
- `correct_escalate` — engine escalated, human denied (engine was right)
- `false_allow` — engine allowed, but human reviewing the audit log reversed it

### 3. Per-Dimension False Rates

New CLI `tooltrust calibrate report` and HTTP `GET /api/analytics/calibration` that compute false-allow and false-escalate rates bucketed by tool, environment, and data_class.

### 4. Shadow-Mode Documentation

A process doc describing how to run `tooltrust calibrate report` against a production audit snapshot with candidate thresholds, compare rates, and promote.

## Files
- `engine/score.py` — `_counterfactual_threshold()` function
- `audit/models.py` — `counterfactual` field on `AuditEntry`
- `engine/explain.py` — wire counterfactual into `Decision`
- `cli/calibrate.py` — calibration report CLI
- `server/analytics_routes.py` — calibration HTTP endpoint
- `tests/test_calibrate.py`