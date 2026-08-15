# Audit Redaction — Prevent PII/Secrets in Audit Log

**Version:** 1.0 (Approved)
**Date:** 2026-08-14
**Status:** Approved
**Issue:** [agent-tooltrust #158](https://github.com/anomalyco/agent-tooltrust/issues/158)

## Problem

Tool-call arguments aren't stored in the audit log today, but they will be — and when they are, secrets like `token`, `password`, `apiKey`, `authorization` must be redacted before any sink persists them. Without redaction, the audit log becomes a secondary breach vector.

## Design

- **Module**: `audit/redact.py` — pure redaction logic, no server dependency.
- **Default deny-list**: `token`, `password`, `apiKey`, `authorization`, `secret`, `key`, `passwd`, `credential`, `access_token`, `private_key`.
- **Per-policy override**: `AuditLogger` accepts optional `redact_keys` param (union of default + extra keys).
- **Entry fields**: add `arguments: dict | None` and `redacted: bool` to `AuditEntry`; update `from_decision`/`to_dict`/`from_dict`.
- **Placeholder**: replaced values become `***REDACTED***`.
- **Nested structures**: recursion into sub-dicts and lists.
- **Fail safe**: if args cannot be redacted (non-dict), the entry stores `{"error": "unredactable"}` with `redacted=True`.

## Files
- Create: `src/agent_tooltrust/audit/redact.py`
- Modify: `src/agent_tooltrust/audit/models.py` (add `arguments`, `redacted` fields)
- Modify: `src/agent_tooltrust/audit/logger.py` (redact in `log()`)
- Tests: `tests/test_audit_redaction.py`