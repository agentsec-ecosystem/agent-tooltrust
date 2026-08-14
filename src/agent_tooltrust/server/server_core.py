"""ServerCore — shared state container for the MCP server.

Wraps the Engine, SessionStore, and AuditLogger so both the MCP tools and
the /audit HTTP endpoint share the same instances.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.engine.escalation import EscalationManager
from agent_tooltrust.server.session_store import SessionStore


class ServerCore:
    """Shared server state: Engine + SessionStore + AuditLogger.

    Args:
        engine: The ToolTrust decision engine.
        session_store: In-memory session state tracker.
        audit_logger: Audit sink for persisting and querying decisions.
    """

    def __init__(
        self,
        engine: Engine,
        session_store: SessionStore,
        audit_logger: AuditLogger,
    ) -> None:
        self._engine = engine
        self._session_store = session_store
        self._audit_logger = audit_logger

    @property
    def engine(self) -> Engine:
        """The decision engine."""
        return self._engine

    @property
    def session_store(self) -> SessionStore:
        """The session state tracker."""
        return self._session_store

    @property
    def audit_logger(self) -> AuditLogger:
        """The audit sink."""
        return self._audit_logger

    @property
    def escalation_manager(self) -> EscalationManager:
        """The escalation registry for human approval (M3)."""
        return self._engine.escalation_manager

    def evaluate(
        self,
        tool_name: str,
        action: str,
        environment: str,
        data_class: str,
        agent_id: str,
        session_id: str | None = None,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        call_budget: int | None = None,
        token_budget: int | None = None,
        consent_scopes: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Evaluate a tool call through Engine, track session, audit.

        Args:
            tool_name: The tool being called.
            action: The action verb.
            environment: The deployment environment.
            data_class: The data classification.
            agent_id: The calling agent's identity.
            session_id: Optional session identifier for state tracking.
            arguments: Optional tool arguments.
            context: Optional additional context.
            call_budget: Per-session call budget ceiling (session creation only).
            token_budget: Per-session token budget ceiling (session creation only).
            consent_scopes: Per-session consent scopes (session creation only).

        Returns:
            A dict with decision fields plus ``session_risk_score`` and ``call_id``.
        """
        decision = self._engine.evaluate(
            tool_name=tool_name,
            action=action,
            environment=environment,
            data_class=data_class,
            agent_id=agent_id,
            arguments=arguments,
            context=context,
        )

        decision_dict = decision.to_dict()

        session_risk_score: float = 0.0
        if session_id is not None:
            self._session_store.get_or_create(
                session_id,
                call_budget=call_budget,
                token_budget=token_budget,
                consent_scopes=consent_scopes,
            )

            if decision_dict["decision"] not in ("deny",):
                falloff = 1.0 if decision_dict["criticality"] == "critical" else 0.25
                self._session_store.update(
                    session_id,
                    risk_increment=falloff,
                    call_id="pending",
                )

            exceeded, reason = self._session_store.exceeds_budget(session_id)
            if exceeded:
                decision_dict = dict(decision_dict)
                decision_dict["decision"] = "deny"
                decision_dict["reason_code"] = "budget_exceeded"
                decision_dict["explanation"] = f"Session budget exceeded: {reason}"

            if not exceeded and not self._session_store.within_consent(
                session_id, tool_name, environment, data_class
            ):
                decision_dict = dict(decision_dict)
                decision_dict["decision"] = "escalate"
                decision_dict["reason_code"] = "scope_boundary"
                decision_dict["explanation"] = (
                    "Tool call outside session consent scopes. Escalation required."
                )

            state = self._session_store.get(session_id)
            session_risk_score = state.risk_score if state else 0.0

        entry = AuditEntry(
            session_id=session_id,
            timestamp=datetime.now(UTC).isoformat(),
            tool=tool_name,
            tool_category=None,
            action=action,
            action_class=None,
            environment=environment,
            data_class=data_class,
            agent_id=agent_id,
            agent_class=None,
            decision=decision_dict["decision"],
            criticality=decision_dict["criticality"],
            reason_code=decision_dict["reason_code"],
            explanation=decision_dict["explanation"],
            factors=list(decision.factors),
            policy_version=decision_dict.get("policy_version", "0.0.0"),
            dry_run=decision_dict.get("dry_run", False),
            escalation_id=decision_dict.get("escalation_id"),
        )
        try:
            self._audit_logger.sink.write(entry)
        except Exception as exc:
            print(f"tooltrust audit: log failed: {exc}", file=sys.stderr)

        if session_id is not None and decision_dict["decision"] not in ("deny",):
            self._session_store.patch_last_call_id(session_id, entry.call_id)

        result = dict(decision_dict)
        result["session_risk_score"] = session_risk_score
        result["call_id"] = entry.call_id
        return result

    def explain_from_audit(self, call_id: str) -> dict[str, Any] | None:
        """Look up an explanation from the audit trail by call_id.

        Args:
            call_id: The call_id from a previous evaluate response.

        Returns:
            A dict with explanation, factors, reason_code, and criticality,
            or None if no matching entry is found.
        """
        entries = self._audit_logger.query()
        for entry in entries:
            if entry.call_id == call_id:
                return {
                    "explanation": entry.explanation,
                    "factors": [f.to_dict() for f in entry.factors],
                    "reason_code": entry.reason_code,
                    "criticality": entry.criticality,
                }
        return None
