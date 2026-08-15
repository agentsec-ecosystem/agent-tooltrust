"""Tests for the PDP POST /authorize HTTP endpoint."""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.pdp_routes import register_pdp_routes
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


class TestPdpRoutes:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"))
        session_store = SessionStore()
        audit_logger = AuditLogger()
        return ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)

    @pytest.fixture
    def client(self, core: ServerCore) -> TestClient:
        from fastmcp import FastMCP

        mcp = FastMCP("test")
        register_pdp_routes(mcp, core)
        app = mcp.http_app()
        return TestClient(app)

    def test_authorize_returns_decision(self, client: TestClient) -> None:
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
        data: dict[str, Any] = response.json()
        assert data["decision"] in ("allow", "audit")
        assert "reason_code" in data
        assert "call_id" in data

    def test_authorize_denies_destructive(self, client: TestClient) -> None:
        response = client.post(
            "/authorize",
            json={
                "tool_name": "drop_database",
                "action": "delete",
                "environment": "production",
                "data_class": "customer_pii",
                "agent_id": "release-bot",
            },
        )
        assert response.status_code == 200
        assert response.json()["decision"] == "deny"

    def test_authorize_matches_engine(self, client: TestClient, core: ServerCore) -> None:
        body = {
            "tool_name": "deploy_service",
            "action": "write",
            "environment": "production",
            "data_class": "restricted",
            "agent_id": "release-bot",
        }
        response = client.post("/authorize", json=body)
        via_route = response.json()
        via_engine = core.evaluate(**body)
        assert via_route["decision"] == via_engine["decision"]
        assert via_route["criticality"] == via_engine["criticality"]

    def test_missing_field_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/authorize",
            json={"tool_name": "query_logs", "action": "read", "agent_id": "debug-bot"},
        )
        assert response.status_code == 400
        assert "error" in response.json()
        assert "environment" in response.json()["error"]
        assert "data_class" in response.json()["error"]

    def test_blank_field_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/authorize",
            json={
                "tool_name": "  ",
                "action": "read",
                "environment": "staging",
                "data_class": "internal",
                "agent_id": "debug-bot",
            },
        )
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_json_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/authorize",
            content=b'{"tool_name": ',
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400
        assert "error" in response.json()
