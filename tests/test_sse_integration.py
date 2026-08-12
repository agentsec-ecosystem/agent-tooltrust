"""SSE transport integration test — real MCP client over TCP."""

from __future__ import annotations

import asyncio
import subprocess
import time
from typing import Any

import pytest

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy


class TestSSEIntegration:
    SSE_URL = "http://localhost:8000/sse"
    TIMEOUT = 30

    @pytest.fixture(scope="class")
    def engine(self) -> Engine:
        return Engine(default_policy("balanced"))

    @pytest.fixture(scope="class")
    def _server(self) -> Any:
        subprocess.run(
            ["docker", "compose", "up", "--detach", "--wait"],
            check=True,
            timeout=60,
        )
        time.sleep(2)
        yield
        subprocess.run(["docker", "compose", "down"], check=True)

    def test_sse_evaluate_allow(self, engine: Engine) -> None:
        result = _call_sse_sync(
            "tooltrust.evaluate",
            {
                "tool_name": "query_logs",
                "action": "read",
                "environment": "staging",
                "data_class": "internal",
                "agent_id": "debug-bot",
            },
        )
        assert result["decision"] == "allow"

    def test_sse_evaluate_deny(self, engine: Engine) -> None:
        result = _call_sse_sync(
            "tooltrust.evaluate",
            {
                "tool_name": "drop_database",
                "action": "delete",
                "environment": "production",
                "data_class": "customer_pii",
                "agent_id": "bad-bot",
            },
        )
        assert result["decision"] == "deny"

    def test_sse_evaluate_escalate(self, engine: Engine) -> None:
        result = _call_sse_sync(
            "tooltrust.evaluate",
            {
                "tool_name": "deploy_service",
                "action": "write",
                "environment": "production",
                "data_class": "restricted",
                "agent_id": "release-bot",
            },
        )
        assert result["decision"] == "escalate"

    def test_sse_explain(self, engine: Engine) -> None:
        result = _call_sse_sync(
            "tooltrust.explain",
            {
                "tool_name": "deploy_service",
                "action": "write",
                "environment": "production",
                "data_class": "restricted",
                "agent_id": "release-bot",
            },
        )
        assert "explanation" in result
        assert "factors" in result

    def test_sse_session_status(self, engine: Engine) -> None:
        result = _call_sse_sync(
            "tooltrust.session_status",
            {"session_id": "nonexistent"},
        )
        assert "error" in result or "session_id" in result

    def test_sse_audit_endpoint(self) -> None:
        import json
        import urllib.request

        resp = urllib.request.urlopen("http://localhost:8000/audit")
        assert resp.status == 200
        data = json.loads(resp.read())
        assert isinstance(data, list)

    def test_sse_audit_health(self) -> None:
        import json
        import urllib.request

        resp = urllib.request.urlopen("http://localhost:8000/audit/health")
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == "ok"


def _call_sse_sync(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call an MCP tool via SSE transport (sync wrapper).

    Args:
        tool_name: The MCP tool name (tooltrust.evaluate, etc.).
        arguments: Tool arguments.

    Returns:
        The tool's response as a dict.
    """
    return asyncio.run(_call_sse(tool_name, arguments))


async def _call_sse(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from fastmcp.client import Client
    from fastmcp.client.transports import SSETransport

    transport = SSETransport("http://localhost:8000/sse")
    async with Client(transport) as client:
        result = await client.call_tool(tool_name, arguments)
        content = result.content
        if content and hasattr(content[0], "text"):  # type: ignore[union-attr]
            import json
            return json.loads(content[0].text)  # type: ignore[union-attr]
        return {"error": "no content"}
