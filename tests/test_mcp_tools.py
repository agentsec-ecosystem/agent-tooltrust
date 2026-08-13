"""Tests for MCP tool functions (evaluate, explain, session_status)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.mcp_tools import register_tools
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


class TestMCPTools:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"))
        session_store = SessionStore()
        audit_logger = AuditLogger()
        return ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)

    @pytest.fixture
    def tools(self, core: ServerCore) -> dict[str, Any]:
        from fastmcp import FastMCP

        mcp = FastMCP("test")
        return register_tools(mcp, core)

    def test_evaluate_returns_decision(self, tools: dict[str, Any]) -> None:
        result = tools["tooltrust.evaluate"](
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

    def test_evaluate_denies_destructive(self, tools: dict[str, Any]) -> None:
        result = tools["tooltrust.evaluate"](
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="customer_pii",
            agent_id="release-bot",
        )
        assert result["decision"] == "deny"

    def test_explain_returns_breakdown(self, tools: dict[str, Any]) -> None:
        result = tools["tooltrust.explain"](
            tool_name="deploy_service",
            action="write",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )
        assert "explanation" in result
        assert "factors" in result
        assert "reason_code" in result

    def test_explain_by_call_id(self, core: ServerCore, tools: dict[str, Any]) -> None:
        eval_result = core.evaluate(
            "query_logs", "read", "staging", "internal", "debug-bot",
            session_id="explain_cid_test",
        )
        call_id = eval_result["call_id"]

        result = tools["tooltrust.explain"](call_id=call_id)
        assert result is not None
        assert result["explanation"] == eval_result["explanation"]

    def test_explain_by_call_id_not_found(self, tools: dict[str, Any]) -> None:
        result = tools["tooltrust.explain"](call_id="nonexistent-call-id")
        assert "error" in result

    def test_session_status_returns_state(self, core: ServerCore, tools: dict[str, Any]) -> None:
        sid = str(uuid.uuid4())
        core.evaluate("query_logs", "read", "staging", "internal", "debug-bot", session_id=sid)

        result = tools["tooltrust.session_status"](session_id=sid)

        assert result["session_id"] == sid
        assert result["risk_score"] >= 0.0
        assert result["tool_call_count"] >= 1

    def test_session_status_not_found(self, tools: dict[str, Any]) -> None:
        result = tools["tooltrust.session_status"](session_id="nonexistent")
        assert "error" in result

    def test_evaluate_captures_call_id(self, core: ServerCore, tools: dict[str, Any]) -> None:
        result = tools["tooltrust.evaluate"](
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="debug-bot",
            session_id="call_id_test",
        )
        assert "call_id" in result
        uuid.UUID(result["call_id"])

    def test_evaluate_handles_missing_required_fields(self, tools: dict[str, Any]) -> None:
        result = tools["tooltrust.evaluate"](
            tool_name="",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="debug-bot",
        )
        assert result["decision"] == "deny"
        assert "reason_code" in result
