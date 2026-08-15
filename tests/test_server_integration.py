"""Integration tests for the full MCP server stack."""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

import pytest
from starlette.testclient import TestClient

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.audit_routes import register_audit_routes
from agent_tooltrust.server.mcp_tools import register_tools
from agent_tooltrust.server.pdp_routes import register_pdp_routes
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


class TestServerIntegration:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"))
        session_store = SessionStore()
        audit_logger = AuditLogger()
        return ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)

    @pytest.fixture
    def client(self, core: ServerCore) -> TestClient:
        from fastmcp import FastMCP

        mcp = FastMCP("test-integration")
        register_tools(mcp, core)
        register_audit_routes(mcp, core)
        app = mcp.http_app()
        return TestClient(app)

    def test_full_flow_evaluate_audit_explain(self, client: TestClient, core: ServerCore) -> None:
        sid = str(uuid.uuid4())

        result1 = core.evaluate(
            "query_logs", "read", "staging", "internal", "debug-bot", session_id=sid,
        )
        assert result1["decision"] == "allow"
        call_id = result1["call_id"]
        uuid.UUID(call_id)

        result2 = core.evaluate(
            "deploy_service", "write", "production", "restricted", "release-bot", session_id=sid,
        )
        assert result2["decision"] in ("escalate", "audit")

        response = client.get(f"/audit?session={sid}")
        assert response.status_code == 200
        entries = response.json()
        assert len(entries) == 2

        explain_response = client.get("/audit/health")
        assert explain_response.status_code == 200
        health: dict[str, Any] = explain_response.json()
        assert health["status"] == "ok"
        assert health["sessions_active"] >= 1

    def test_session_cumulative_risk_grows(self, core: ServerCore) -> None:
        sid = str(uuid.uuid4())

        core.evaluate("query_logs", "read", "staging", "internal", "bot1", session_id=sid)
        state1 = core.session_store.get(sid)
        assert state1 is not None
        risk1 = state1.risk_score

        core.evaluate("deploy_service", "write", "production", "internal", "bot1", session_id=sid)
        state2 = core.session_store.get(sid)
        assert state2 is not None
        assert state2.risk_score >= risk1
        assert state2.tool_call_count == 2

    def test_budget_denies_after_limit(self, core: ServerCore) -> None:
        sid = str(uuid.uuid4())
        result: dict[str, Any] = {}

        for _ in range(6):
            result = core.evaluate(
                "query_logs", "read", "staging", "internal", "bot1",
                session_id=sid, call_budget=5,
            )

        assert result["decision"] == "deny"
        assert "budget" in result["reason_code"].lower()

    def test_consent_blocks_out_of_scope(self, core: ServerCore) -> None:
        sid = str(uuid.uuid4())
        scopes = [{"tool": "query_logs", "env": "staging", "data_class": "internal"}]

        allowed = core.evaluate(
            "query_logs", "read", "staging", "internal", "bot1",
            session_id=sid, consent_scopes=scopes,
        )
        assert allowed["decision"] == "allow"

        blocked = core.evaluate(
            "deploy_service", "write", "production", "internal", "bot1",
            session_id=sid, consent_scopes=scopes,
        )
        assert blocked["decision"] == "escalate"
        assert "scope" in blocked["reason_code"].lower()

    def test_pdp_authorize_end_to_end(self, core: ServerCore) -> None:
        from fastmcp import FastMCP

        mcp = FastMCP("test-pdp")
        register_pdp_routes(mcp, core)
        client = TestClient(mcp.http_app())

        response = client.post(
            "/authorize",
            json={
                "tool_name": "query_logs",
                "action": "read",
                "environment": "staging",
                "data_class": "internal",
                "agent_id": "debug-bot",
            },
        )
        assert response.status_code == 200
        assert response.json()["decision"] in ("allow", "audit")

    def test_connector_authorize_end_to_end(self) -> None:
        from agent_tooltrust.mcp_data import (
            DataAccessRequest,
            authorize_data_source,
            register_data_source,
        )

        policy = replace(
            default_policy("balanced"),
            data_classes={**default_policy("balanced").data_classes, "analytics_shard": 0.0},
        )
        core = ServerCore(
            engine=Engine(policy),
            session_store=SessionStore(),
            audit_logger=AuditLogger(),
        )
        register_data_source("analytics_shard")
        result = authorize_data_source(
            DataAccessRequest(
                data_source_id="analytics_shard",
                operation="read",
                agent_id="data-sci",
                environment="staging",
            ),
            core,
        )
        assert result["decision"] == "allow"
        assert "call_id" in result
