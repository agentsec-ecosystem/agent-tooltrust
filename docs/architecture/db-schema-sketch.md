# Database Schema Sketch — Agent ToolTrust

**Version:** 0.1.0
**Date:** 2026-08-08

## Audit Log Tables

### Primary: `audit_entries`

```sql
CREATE TABLE audit_entries (
    id              BIGSERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tool            TEXT NOT NULL,
    tool_category   TEXT,
    action          TEXT NOT NULL,
    action_class    TEXT NOT NULL,
    environment     TEXT NOT NULL,
    data_class      TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    agent_class     TEXT,
    decision        TEXT NOT NULL CHECK (decision IN ('allow', 'audit', 'escalate', 'deny')),
    criticality     TEXT NOT NULL CHECK (criticality IN ('none', 'low', 'medium', 'high', 'critical')),
    reason_code     TEXT NOT NULL,
    explanation     TEXT NOT NULL,
    factors         JSONB,
    policy_version  TEXT NOT NULL,
    dry_run         BOOLEAN NOT NULL DEFAULT FALSE,
    escalation_id   TEXT,
    session_context JSONB,
    arguments_hash  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_session ON audit_entries(session_id, timestamp);
CREATE INDEX idx_audit_agent ON audit_entries(agent_id, timestamp);
CREATE INDEX idx_audit_decision ON audit_entries(decision, timestamp);
CREATE INDEX idx_audit_escalation ON audit_entries(escalation_id) WHERE escalation_id IS NOT NULL;
```

### Escalation: `escalations`

```sql
CREATE TABLE escalations (
    id              TEXT PRIMARY KEY,       -- escalation_id
    session_id      TEXT NOT NULL,
    decision_id     BIGINT REFERENCES audit_entries(id),
    tool            TEXT NOT NULL,
    action          TEXT NOT NULL,
    action_identity TEXT NOT NULL,          -- hash of (tool, action, args) — prevents replay
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
    approver        TEXT,
    approved_at     TIMESTAMPTZ,
    denied_at       TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ NOT NULL,
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_esc_session ON escalations(session_id);
CREATE INDEX idx_esc_status ON escalations(status);
CREATE INDEX idx_esc_expiry ON escalations(expires_at) WHERE status = 'pending';
```

## Policy Store (future, v0.3+)

```sql
CREATE TABLE policy_versions (
    id              SERIAL PRIMARY KEY,
    version         TEXT NOT NULL UNIQUE,
    posture         TEXT NOT NULL,
    policy_yaml     TEXT NOT NULL,
    policy_hash     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE policy_deployments (
    id              SERIAL PRIMARY KEY,
    version         TEXT NOT NULL REFERENCES policy_versions(version),
    environment     TEXT NOT NULL,
    deployed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deployed_by     TEXT
);
```

## Local: `tooltrust.db` (SQLite, v0.1)

```sql
CREATE TABLE audit_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    tool            TEXT NOT NULL,
    action          TEXT NOT NULL,
    environment     TEXT NOT NULL,
    data_class      TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    decision        TEXT NOT NULL,
    criticality     TEXT NOT NULL,
    reason_code     TEXT NOT NULL,
    explanation     TEXT NOT NULL,
    factors         TEXT,
    policy_version  TEXT NOT NULL,
    dry_run         INTEGER NOT NULL DEFAULT 0,
    escalation_id   TEXT
);

CREATE INDEX idx_audit_session ON audit_entries(session_id);
```

## JSONL (default, v0.1 — no schema)

```
{"session_id":"sess_abc123","timestamp":"2026-08-08T19:45:00Z","tool":"deploy_service",...}
{"session_id":"sess_abc123","timestamp":"2026-08-08T19:45:01Z","tool":"query_logs",...}
```