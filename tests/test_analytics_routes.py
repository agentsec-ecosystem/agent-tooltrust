"""Tests for the /api/analytics and /api/analytics/sessions HTTP endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.analytics_routes import register_analytics_routes
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


class TestAnalyticsRoutes:
    @pytest.fixture
    def core(self) -> ServerCore:
        audit_logger = AuditLogger()
        engine = Engine(default_policy("balanced"), audit_logger=audit_logger)
        session_store = SessionStore()
        core = ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)
        core.evaluate(
            "query_logs", "read", "staging", "internal", "debug-bot",
            session_id="s1",
        )
        core.evaluate(
            "drop_database", "delete", "production", "customer_pii", "release-bot",
            session_id="s1",
        )
        return core

    @pytest.fixture
    def client(self, core: ServerCore) -> TestClient:
        from fastmcp import FastMCP

        mcp = FastMCP("test")
        register_analytics_routes(mcp, core)
        app = mcp.http_app()
        return TestClient(app)

    def test_analytics_returns_summary(self, client: TestClient) -> None:
        response = client.get("/api/analytics")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert data["total_decisions"] >= 1
        assert "by_decision" in data
        assert "deny_rate" in data

    def test_analytics_sessions_returns_findings(self, client: TestClient) -> None:
        response = client.get("/api/analytics/sessions")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert "recurring_denials" in data
        assert "deny_to_allow_transitions" in data
        assert "dead_rules" in data
        assert "over_hit_rules" in data

    def test_analytics_sessions_respects_min_denials(self, client: TestClient) -> None:
        response = client.get("/api/analytics/sessions?min_denials=1")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert isinstance(data["recurring_denials"], list)

    def test_analytics_sessions_empty_log(self) -> None:
        from agent_tooltrust.audit.models import AuditEntry
        from agent_tooltrust.audit.sink import AuditSink

        class MemorySink(AuditSink):
            def write(self, entry: AuditEntry) -> None:
                pass
            def query(self, session_id: str | None = None) -> list[AuditEntry]:
                return []

        engine = Engine(default_policy("balanced"))
        core = ServerCore(
            engine=engine, session_store=SessionStore(),
            audit_logger=AuditLogger(sink=MemorySink()),
        )
        from fastmcp import FastMCP

        mcp = FastMCP("test-empty")
        register_analytics_routes(mcp, core)
        client = TestClient(mcp.http_app())

        response = client.get("/api/analytics/sessions")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert data["recurring_denials"] == []
        assert data["deny_to_allow_transitions"] == []
