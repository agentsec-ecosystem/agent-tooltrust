"""Tests for the MCP-Data connector (per-data-source authorization)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.mcp_data import DataAccessRequest, authorize_data_source, register_data_source
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore
from agent_tooltrust.taxonomy import domain_for, register_tool


class TestRegisterTool:
    def test_registers_tool_to_domain(self) -> None:
        register_tool("mcp_data.test_src", "db")
        assert domain_for("mcp_data.test_src") == "db"

    def test_blank_tool_raises(self) -> None:
        with pytest.raises(ValueError):
            register_tool("  ", "db")

    def test_unknown_domain_raises(self) -> None:
        with pytest.raises(ValueError):
            register_tool("mcp_data.x", "not_a_domain")


class TestRegisterDataSource:
    def test_registers_source_as_db_tool(self) -> None:
        register_data_source("snowflake_analytics")
        assert domain_for("mcp_data.snowflake_analytics") == "db"

    def test_blank_source_raises(self) -> None:
        with pytest.raises(ValueError):
            register_data_source("  ")


class TestAuthorizeDataSource:
    @pytest.fixture
    def core(self) -> ServerCore:
        engine = Engine(default_policy("balanced"))
        session_store = SessionStore()
        audit_logger = AuditLogger()
        return ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)

    def _core_with_source(self, source_id: str, sensitivity: float = 0.0) -> ServerCore:
        from dataclasses import replace

        policy = replace(
            default_policy("balanced"),
            data_classes={**default_policy("balanced").data_classes, source_id: sensitivity},
        )
        return ServerCore(
            engine=Engine(policy),
            session_store=SessionStore(),
            audit_logger=AuditLogger(),
        )

    def test_registered_source_read_allowed(self) -> None:
        core = self._core_with_source("analytics_shard")
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

    def test_unregistered_source_denies(self, core: ServerCore) -> None:
        result = authorize_data_source(
            DataAccessRequest(
                data_source_id="unknown_warehouse",
                operation="read",
                agent_id="data-sci",
                environment="staging",
            ),
            core,
        )
        assert result["decision"] == "deny"

    def test_write_on_registered_source_not_allow(self) -> None:
        core = self._core_with_source("customer_pii_store", sensitivity=1.0)
        register_data_source("customer_pii_store")
        result = authorize_data_source(
            DataAccessRequest(
                data_source_id="customer_pii_store",
                operation="write",
                agent_id="release-bot",
                environment="production",
            ),
            core,
        )
        assert result["decision"] in ("deny", "escalate")