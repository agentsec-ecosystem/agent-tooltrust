# Stale-Credential Audit Classification

**Version:** 1.0 (Approved)
**Date:** 2026-08-14
**Issue:** [agent-tooltrust #161](https://github.com/anomalyco/agent-tooltrust/issues/161)

## Problem

A stale or out-of-scope credential resolved at call time shows up as a confusing `not-available` variant: the engine says `allow`, the tool call still fails, and the audit trail collapses that failure into the wrong semantic bucket.

## Design

- Added `credential_status` field to `AuditEntry` (optional str `"stale"` when a post-allow credential rejection happens).
- `AuditLogger.log()` accepts optional `credential_status` param that callers set when logging post-execution results.
- Decisions stay `allow` (the engine allowed it); the audit entry tags *why* the call still failed.
- Call-time credential resolution: resolving credentials fresh at decision time from a vault scoped to the specific tool+action removes the entire class of failure. See `docs/design/real-agent-integration/call-time-credential-resolution.md`.

## Files
- `audit/models.py` — `credential_status` field
- `audit/logger.py` — `credential_status` param on `log()`
- `tests/test_stale_credential.py` — 3 tests