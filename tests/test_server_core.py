"""Tests for ServerCore — the shared server state container."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


class TestServerCore:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"))
        session_store = SessionStore()
        audit_logger = AuditLogger()
        return ServerCore(
            engine=engine,
            session_store=session_store,
            audit_logger=audit_logger,
        )

    def test_evaluate_returns_decision(self, core: ServerCore) -> None:
        result = core.evaluate(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="debug-bot",
        )

        assert result["decision"] == "allow"
        assert "criticality" in result
        assert "reason_code" in result
        assert "explanation" in result

    def test_evaluate_tracks_session_risk(self, core: ServerCore) -> None:
        sid = "sess_risk_test"

        result = core.evaluate(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="debug-bot",
            session_id=sid,
        )

        assert "session_risk_score" in result
        assert result["session_risk_score"] >= 0.0
        assert result["session_risk_score"] < 1.0

    def test_evaluate_accumulates_session_risk(self, core: ServerCore) -> None:
        sid = str(uuid.uuid4())
        core.evaluate("query_logs", "read", "staging", "public", "debug-bot", session_id=sid)
        result = core.evaluate(
            "deploy_service", "write", "production", "restricted", "release-bot", session_id=sid
        )

        assert result["session_risk_score"] > 0.0

    def test_evaluate_budget_exceeded_denies(self, core: ServerCore) -> None:
        sid = str(uuid.uuid4())
        result: dict[str, Any] = {}

        for _ in range(3):
            result = core.evaluate(
                "query_logs", "read", "staging", "internal", "debug-bot",
                session_id=sid, call_budget=3,
            )

        assert result["decision"] == "deny"
        assert "budget" in result["reason_code"].lower()

    def test_evaluate_consent_boundary_escalates(self, core: ServerCore) -> None:
        sid = str(uuid.uuid4())

        result = core.evaluate(
            "deploy_service", "write", "production", "internal", "release-bot",
            session_id=sid,
            consent_scopes=[
                {"tool": "query_logs", "env": "staging", "data_class": "internal"}
            ],
        )

        assert result["decision"] == "escalate"
        assert "scope" in result["reason_code"].lower()

    def test_evaluate_within_consent_allows(self, core: ServerCore) -> None:
        sid = str(uuid.uuid4())

        result = core.evaluate(
            "query_logs", "read", "staging", "internal", "debug-bot",
            session_id=sid,
            consent_scopes=[
                {"tool": "query_logs", "env": "staging", "data_class": "internal"}
            ],
        )

        assert result["decision"] == "allow"

    def test_evaluate_without_session_id_works(self, core: ServerCore) -> None:
        result = core.evaluate(
            "query_logs", "read", "staging", "public", "debug-bot",
        )

        assert result["decision"] == "allow"
        assert "session_risk_score" in result

    def test_evaluate_emits_audit_entry(self, core: ServerCore) -> None:
        result = core.evaluate(
            "query_logs", "read", "staging", "internal", "debug-bot",
            session_id="audit_test",
        )

        assert "call_id" in result
        uuid.UUID(result["call_id"])

        entries = core.audit_logger.query("audit_test")
        assert len(entries) == 1
        assert entries[0].tool == "query_logs"

    def test_explain_from_audit_finds_entry(self, core: ServerCore) -> None:
        result = core.evaluate(
            "query_logs", "read", "staging", "internal", "debug-bot",
            session_id="explain_test",
        )
        call_id = result["call_id"]

        explained = core.explain_from_audit(call_id)
        assert explained is not None
        assert explained["explanation"] == result["explanation"]

    def test_explain_from_audit_missing_call_id(self, core: ServerCore) -> None:
        explained = core.explain_from_audit("nonexistent-call-id")
        assert explained is None
