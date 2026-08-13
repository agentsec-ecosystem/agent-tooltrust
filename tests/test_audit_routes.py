"""Tests for /audit HTTP endpoint registered on FastMCP."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from starlette.testclient import TestClient

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.audit_routes import register_audit_routes
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


class TestAuditRoutes:
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
        register_audit_routes(mcp, core)
        app = mcp.http_app()
        return TestClient(app)

    def test_health_returns_status(self, client: TestClient) -> None:
        response = client.get("/audit/health")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert data["status"] == "ok"
        assert "policy_version" in data
        assert "uptime" in data
        assert "sessions_active" in data

    def test_get_recent_returns_list(self, client: TestClient, core: ServerCore) -> None:
        sid = str(uuid.uuid4())
        core.evaluate("query_logs", "read", "staging", "internal", "debug-bot",
                       session_id=sid)
        core.evaluate("deploy_service", "write", "production", "restricted", "release-bot",
                       session_id=sid)

        response = client.get("/audit")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_get_by_session(self, client: TestClient, core: ServerCore) -> None:
        sid = str(uuid.uuid4())
        core.evaluate("query_logs", "read", "staging", "internal", "debug-bot",
                       session_id=sid)

        response = client.get(f"/audit?session={sid}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["tool"] == "query_logs"

    def test_get_by_decision(self, client: TestClient, core: ServerCore) -> None:
        sid = str(uuid.uuid4())
        core.evaluate("drop_database", "delete", "production", "customer_pii", "release-bot",
                       session_id=sid)

        response = client.get("/audit?decision=deny")
        assert response.status_code == 200
        data = response.json()
        deny_entries = [e for e in data if e["session_id"] == sid]
        assert len(deny_entries) >= 1
        assert deny_entries[0]["decision"] == "deny"

    def test_empty_audit_returns_empty_list(self, client: TestClient) -> None:
        response = client.get(f"/audit?session={uuid.uuid4()!s}")
        assert response.status_code == 200
        assert response.json() == []

    def test_health_sessions_active(self, client: TestClient, core: ServerCore) -> None:
        sid1 = str(uuid.uuid4())
        sid2 = str(uuid.uuid4())
        core.evaluate("query_logs", "read", "staging", "internal", "debug-bot",
                       session_id=sid1)
        core.evaluate("deploy_service", "write", "production", "restricted", "release-bot",
                       session_id=sid2)

        response = client.get("/audit/health")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert data["sessions_active"] >= 2
