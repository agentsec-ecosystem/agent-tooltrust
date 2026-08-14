"""Tests for the Operator Console API endpoints (/api/sessions, /api/analytics,
/api/baselines) registered on the FastMCP server."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from starlette.testclient import TestClient

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.sink import AuditSink
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.analytics_routes import register_analytics_routes
from agent_tooltrust.server.baselines_routes import register_baselines_routes
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore
from agent_tooltrust.server.sessions_routes import register_sessions_routes


class MemorySink(AuditSink):
    """In-process audit sink isolating tests from the shipped JSONL file."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def write(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def query(self, session_id: str | None = None) -> list[AuditEntry]:
        if session_id is None:
            return list(self._entries)
        return [e for e in self._entries if e.session_id == session_id]


class TestSessionsRoutes:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"))
        session_store = SessionStore()
        audit_logger = AuditLogger(MemorySink())
        return ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)

    @pytest.fixture
    def client(self, core: ServerCore) -> TestClient:
        from fastmcp import FastMCP

        mcp = FastMCP("test")
        register_sessions_routes(mcp, core)
        app = mcp.http_app()
        return TestClient(app)

    def test_seeded_session_replays_calls(self, client: TestClient, core: ServerCore) -> None:
        sid = str(uuid.uuid4())
        core.evaluate("query_logs", "read", "staging", "internal", "debug-bot",
                       session_id=sid)
        core.evaluate("deploy_service", "write", "production", "restricted", "release-bot",
                       session_id=sid)

        response = client.get(f"/api/sessions/{sid}")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert data["session_id"] == sid
        assert data["call_count"] == 2
        assert len(data["calls"]) == 2
        assert all(call["session_id"] == sid for call in data["calls"])
        assert data["calls"][0]["tool"] == "query_logs"
        assert data["calls"][1]["tool"] == "deploy_service"

    def test_unknown_session_returns_empty(self, client: TestClient) -> None:
        response = client.get(f"/api/sessions/{uuid.uuid4()!s}")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert data["calls"] == []
        assert data["call_count"] == 0


class TestAnalyticsRoutes:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"))
        session_store = SessionStore()
        audit_logger = AuditLogger(MemorySink())
        return ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)

    @pytest.fixture
    def client(self, core: ServerCore) -> TestClient:
        from fastmcp import FastMCP

        mcp = FastMCP("test")
        register_analytics_routes(mcp, core)
        app = mcp.http_app()
        return TestClient(app)

    def _seed(self, core: ServerCore) -> tuple[str, str]:
        sid = str(uuid.uuid4())
        for _ in range(2):
            core.evaluate("drop_database", "delete", "production", "customer_pii",
                           "release-bot", session_id=sid)
        for _ in range(3):
            core.evaluate("query_logs", "read", "staging", "internal", "debug-bot",
                           session_id=sid)
        return sid, "drop_database"

    def test_analytics_deterministic_aggregates(self, client: TestClient, core: ServerCore) -> None:
        self._seed(core)
        response = client.get("/api/analytics")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()

        assert data["total_decisions"] == 5
        assert data["by_decision"] == {"allow": 3, "deny": 2}
        assert data["by_tool"] == {"query_logs": 3, "drop_database": 2}
        assert data["deny_rate"] == pytest.approx(2 / 5)
        assert data["top_denied_tools"] == ["drop_database"]
        sessions = data["sessions"]
        assert len(sessions) == 1

    def test_analytics_empty_audit(self, client: TestClient) -> None:
        response = client.get("/api/analytics")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert data["total_decisions"] == 0
        assert data["by_decision"] == {}
        assert data["by_tool"] == {}
        assert data["deny_rate"] == 0.0
        assert data["top_denied_tools"] == []
        assert data["sessions"] == {}

    def test_analytics_has_all_keys(self, client: TestClient) -> None:
        response = client.get("/api/analytics")
        data: dict[str, Any] = response.json()
        for key in ("total_decisions", "by_decision", "by_tool",
                    "deny_rate", "top_denied_tools", "sessions"):
            assert key in data


class TestBaselinesRoutes:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"))
        session_store = SessionStore()
        audit_logger = AuditLogger(MemorySink())
        return ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)

    @pytest.fixture
    def client(self, core: ServerCore) -> TestClient:
        from fastmcp import FastMCP

        mcp = FastMCP("test")
        register_baselines_routes(mcp, core)
        app = mcp.http_app()
        return TestClient(app)

    def test_baselines_returns_required_keys(self, client: TestClient) -> None:
        response = client.get("/api/baselines")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()

        assert data["essential"]["status"] == "pass"
        assert data["hardened"]["status"] == "pending"
        assert data["certified"]["status"] == "pending"
        assert data["owasp"] == {"covered": 5, "total": 10}
        assert data["openssf"] == {"status": "silver", "target": "gold"}
        for tier in ("essential", "hardened", "certified"):
            assert isinstance(data[tier]["checks"], list)
