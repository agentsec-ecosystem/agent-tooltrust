"""Additional tests for analytics routes and CLI argument parsing."""

from __future__ import annotations

import subprocess
import sys

import pytest
from starlette.testclient import TestClient

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.analytics_routes import register_analytics_routes
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


class TestAnalyticsCoverage:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"), audit_logger=AuditLogger())
        core = ServerCore(engine=engine, session_store=SessionStore(), audit_logger=AuditLogger())
        core.evaluate("query_logs", "read", "staging", "internal", "debug-bot", session_id="s1")
        return core

    @pytest.fixture
    def client(self, core: ServerCore) -> TestClient:
        from fastmcp import FastMCP

        mcp = FastMCP("test")
        register_analytics_routes(mcp, core)
        return TestClient(mcp.http_app())

    def test_calibration_endpoint(self, client: TestClient) -> None:
        resp = client.get("/api/analytics/calibration")
        assert resp.status_code == 200
        data = resp.json()
        assert "by_tool" in data
        assert "by_environment" in data


class TestServeParser:
    def test_serve_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_tooltrust", "serve", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--port" in result.stdout
