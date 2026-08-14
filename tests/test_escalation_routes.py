"""Tests for /api/escalations HTTP endpoints (M7.5 #150)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.engine.escalation import EscalationManager
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.escalation_routes import register_escalation_routes
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


class TestEscalationRoutes:
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
        register_escalation_routes(mcp, core)
        app = mcp.http_app()
        return TestClient(app)

    def _seed(self, core: ServerCore) -> str:
        """Create one pending escalation via an engine escalate decision."""
        decision = core.engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
        )
        assert decision.decision == "escalate"
        assert decision.escalation_id is not None
        return decision.escalation_id

    def test_pending_empty_list(self, client: TestClient) -> None:
        response = client.get("/api/escalations")
        assert response.status_code == 200
        assert response.json() == []

    def test_pending_lists_seeded(self, client: TestClient, core: ServerCore) -> None:
        esc_id = self._seed(core)
        response = client.get("/api/escalations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["escalation_id"] == esc_id
        assert data[0]["status"] == "pending"

    def test_all_includes_resolved(self, client: TestClient, core: ServerCore) -> None:
        esc_id = self._seed(core)
        core.escalation_manager.approve(esc_id, approver="ops@example.com")
        pending = client.get("/api/escalations").json()
        assert len(pending) == 0
        all_ = client.get("/api/escalations?all=true").json()
        assert len(all_) == 1
        assert all_[0]["status"] == "approved"

    def test_status_filter(self, client: TestClient, core: ServerCore) -> None:
        self._seed(core)
        denied = client.get("/api/escalations?status=denied").json()
        assert denied == []
        pending = client.get("/api/escalations?status=pending").json()
        assert len(pending) == 1

    def test_approve(self, client: TestClient, core: ServerCore) -> None:
        esc_id = self._seed(core)
        response = client.post(
            f"/api/escalations/{esc_id}/approve",
            json={"approver": "ops@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["approver"] == "ops@example.com"

    def test_approve_unknown_id_409(self, client: TestClient) -> None:
        response = client.post("/api/escalations/esc_nope/approve", json={"approver": "x"})
        assert response.status_code == 409
        assert "error" in response.json()

    def test_approve_twice_409(self, client: TestClient, core: ServerCore) -> None:
        esc_id = self._seed(core)
        first = client.post(f"/api/escalations/{esc_id}/approve", json={"approver": "a"})
        assert first.status_code == 200
        second = client.post(f"/api/escalations/{esc_id}/approve", json={"approver": "a"})
        assert second.status_code == 409

    def test_deny_with_reason(self, client: TestClient, core: ServerCore) -> None:
        esc_id = self._seed(core)
        response = client.post(
            f"/api/escalations/{esc_id}/deny",
            json={"approver": "ops@example.com", "reason": "blocked"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "denied"
        assert data["denied_reason"] == "blocked"
        assert data["approver"] == "ops@example.com"

    def test_deny_unknown_id_409(self, client: TestClient) -> None:
        response = client.post("/api/escalations/esc_nope/deny", json={"approver": "x"})
        assert response.status_code == 409

    def test_approver_from_query_param(self, client: TestClient, core: ServerCore) -> None:
        esc_id = self._seed(core)
        response = client.post(f"/api/escalations/{esc_id}/approve?approver=cli-user")
        assert response.status_code == 200
        assert response.json()["approver"] == "cli-user"


def test_core_exposes_escalation_manager() -> None:
    core = ServerCore(
        engine=Engine(default_policy("balanced")),
        session_store=SessionStore(),
        audit_logger=AuditLogger(),
    )
    assert isinstance(core.escalation_manager, EscalationManager)
