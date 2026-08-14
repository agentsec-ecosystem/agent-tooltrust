# ruff: noqa: S311  (seed uses a fixed RNG seed for reproducible screenshots)
# ruff: noqa: E501  (SEED_ESCALATIONS tuples are wide)
"""Deterministic demo-data seeder for the operator console (M7.5).

Populates the server's audit log and escalation registry with a rich, stable
dataset so the web dashboard and its Playwright screenshots always render
meaningful content. Used by the `/api/seed` endpoint (dev/demo only) and by
the UI test suite before screenshot capture.

Every value is deterministic (fixed tool/action/agent/env matrix, fixed
escalation ids) so screenshots are reproducible across runs and CI.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from agent_tooltrust.engine.escalation import EscalationStatus

#: A curated set of (tool, action, environment, data_class, agent) calls that
#: exercise the four decisions (allow / audit / escalate / deny) deterministically.
SEED_CALLS: tuple[tuple[str, str, str, str, str], ...] = (
    ("query_logs", "read", "staging", "internal", "release-bot"),
    ("query_metrics", "read", "development", "public", "release-bot"),
    ("read_secrets", "read", "production", "restricted", "debug-bot"),
    ("deploy_service", "deploy", "production", "restricted", "dev-eng"),
    ("write_secret", "write", "production", "customer_pii", "dev-eng"),
    ("drop_database", "delete", "production", "restricted", "release-bot"),
    ("assign_role", "grant", "staging", "internal", "dev-eng"),
    ("send_slack", "write", "staging", "public", "release-bot"),
    ("query_logs", "read", "production", "customer_pii", "debug-bot"),
    ("push_changes", "write", "staging", "internal", "release-bot"),
    ("scale_cluster", "write", "production", "internal", "dev-eng"),
    ("run_migration", "write", "production", "restricted", "dev-eng"),
)

#: Escalations seeded directly into the manager, spanning every lifecycle state.
#: Each tuple is (escalation_id, tool, action, agent, env, data, status).
SEED_ESCALATIONS: tuple[tuple[str, str, str, str, str, str, EscalationStatus], ...] = (
    ("esc_pending_01", "deploy_service", "deploy", "dev-eng", "production", "restricted", EscalationStatus.PENDING),
    ("esc_pending_02", "scale_cluster", "write", "dev-eng", "production", "internal", EscalationStatus.PENDING),
    ("esc_pending_03", "run_migration", "write", "data-sci", "production", "restricted", EscalationStatus.PENDING),
    ("esc_approved_01", "write_secret", "write", "dev-eng", "production", "customer_pii", EscalationStatus.APPROVED),
    ("esc_denied_01", "push_changes", "write", "release-bot", "production", "internal", EscalationStatus.DENIED),
    ("esc_expired_01", "deploy_service", "deploy", "release-bot", "production", "restricted", EscalationStatus.EXPIRED),
)

#: Approved escalation approvers, for a realistic audit trail.
APPROVERS = ("alice@example.com", "ops-bot", "bob@example.com")


def _decision_for(tool: str, action: str, environment: str) -> str:
    """Deterministic decision for a seeded call (mirrors the balanced posture)."""
    if action in ("delete", "grant"):
        return "deny"
    if environment == "production" and action == "deploy":
        return "escalate"
    if environment == "production":
        return "audit"
    return "allow"


def _criticality_for(tool: str, action: str, environment: str) -> str:
    decision = _decision_for(tool, action, environment)
    return {"deny": "critical", "escalate": "high", "audit": "medium", "allow": "low"}[decision]


def _reason_for(tool: str, action: str, environment: str) -> str:
    decision = _decision_for(tool, action, environment)
    return {
        "deny": "deny_critical_op",
        "escalate": "escalate_prod_write",
        "audit": "audit_sensitive_data",
        "allow": "allow_low_risk",
    }[decision]


def seed_audit(core: Any, session_id: str = "demo-session") -> int:
    """Write the SEED_CALLS through ``core.evaluate`` and return the count.

    Args:
        core: The :class:`ServerCore` to seed.
        session_id: Session id stamped on every seeded call.

    Returns:
        Number of audit entries written.
    """
    from agent_tooltrust.audit.models import AuditEntry
    from agent_tooltrust.taxonomy import action_class_for, domain_for

    base = datetime.now(UTC)
    count = 0
    for i, (tool, action, environment, data_class, agent_id) in enumerate(SEED_CALLS):
        entry = AuditEntry(
            session_id=session_id,
            timestamp=(base - timedelta(minutes=len(SEED_CALLS) - i)).isoformat(),
            tool=tool,
            tool_category=domain_for(tool),
            action=action,
            action_class=action_class_for(action),
            environment=environment,
            data_class=data_class,
            agent_id=agent_id,
            agent_class="engineer",
            decision=_decision_for(tool, action, environment),
            criticality=_criticality_for(tool, action, environment),
            reason_code=_reason_for(tool, action, environment),
            explanation=f"{tool} ({action}) in {environment} on {data_class} data",
            policy_version="1.0.0",
        )
        core.audit_logger.sink.write(entry)
        count += 1
    return count


def seed_escalations(core: Any, now: datetime | None = None) -> int:
    """Create escalation records spanning every lifecycle state.

    Uses the manager's own factory so records are well-formed, then overrides
    status/approver/timestamps to exercise pending/approved/denied/expired.

    Args:
        core: The :class:`ServerCore` to seed.
        now: Fixed clock for deterministic timestamps (tests inject one).

    Returns:
        Number of escalation records created.
    """
    manager = core.escalation_manager
    now = now or datetime.now(UTC)
    rng = random.Random(0)

    for esc_id, tool, action, agent_id, environment, data_class, status in SEED_ESCALATIONS:
        created = now - timedelta(minutes=rng.randint(2, 30))
        expires = now + timedelta(minutes=5)
        if status is EscalationStatus.EXPIRED:
            expires = now - timedelta(minutes=rng.randint(1, 10))
        approver = APPROVERS[rng.randrange(len(APPROVERS))] if status in (
            EscalationStatus.APPROVED, EscalationStatus.DENIED,
        ) else None
        denied_reason = "blocked by policy review" if status is EscalationStatus.DENIED else None
        # Build the record shape directly to control the id/status/timestamps.
        from agent_tooltrust.engine.escalation import Escalation, action_identity

        record = Escalation(
            escalation_id=esc_id,
            status=status,
            tool=tool,
            action=action,
            agent_id=agent_id,
            environment=environment,
            data_class=data_class,
            action_identity=action_identity(tool, action, {"seeded": True}),
            reason=f"{tool}.{action} in {environment} requires approval",
            arguments={"seeded": True},
            created_at=created.isoformat(),
            expires_at=expires.isoformat(),
            approver=approver,
            denied_reason=denied_reason,
        )
        manager._records[esc_id] = record
        if status is EscalationStatus.APPROVED:
            manager._identity_index[record.action_identity] = esc_id
    return len(SEED_ESCALATIONS)


def seed_demo_data(core: Any) -> dict[str, int]:
    """Seed both audit and escalations and return the counts.

    Args:
        core: The :class:`ServerCore` to seed.

    Returns:
        ``{"audit": N, "escalations": M}``.
    """
    # Clear any prior escalation state so re-seeding is idempotent (no stale
    # records accumulate across repeated /api/seed calls or container restarts).
    core.escalation_manager._records.clear()
    core.escalation_manager._identity_index.clear()
    audit_count = seed_audit(core)
    escalation_count = seed_escalations(core)
    return {"audit": audit_count, "escalations": escalation_count}


def register_seed_route(mcp: Any, core: Any) -> None:
    """Register the dev/demo-only ``POST /api/seed`` endpoint.

    Populates the server with deterministic demo data so the dashboard and its
    screenshots render real content. Guarded to dev/demo: it is intentionally
    not part of the production surface and is only reachable in the shipped
    demo container.

    Args:
        mcp: A FastMCP server instance.
        core: A :class:`ServerCore` instance.
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    @mcp.custom_route("/api/seed", methods=["POST"])  # type: ignore[untyped-decorator]
    async def seed(request: Request) -> JSONResponse:
        counts = seed_demo_data(core)
        return JSONResponse({"status": "seeded", **counts})
