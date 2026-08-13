"""tooltrust_mcp build_agent — ToolTrust MCP server self-test agents."""

from __future__ import annotations

from typing import Any

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from tests.field.agents import (
    NATIVE_ACTION,
    NATIVE_DATA_CLASS,
    NATIVE_ENVIRONMENT,
    MissingFrameworkError,
    scenario_bound_tools,
)


def build_agent(agent_id: str = "mcp-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a ToolTrust MCP self-test agent for the given roster agent.

    Each returns an ``MCPClient``-like wrapper that routes a bounded tool set
    through :class:`~agent_tooltrust.adapters.mcp.ToolTrustMCPWrapper`.

    Args:
        agent_id: Roster agent id (mcp-01 .. mcp-10).
        payload: Optional overrides (engine, policy).

    Returns:
        A ``SimpleNamespace`` exposing ``evaluate(...)``, ``describe()`` and a
        ``scenario_tools`` mapping (scenario id -> guarded callable) used by the
        field harness to drive every scenario through the engine.
    """
    try:
        from types import SimpleNamespace
    except ImportError:  # pragma: no cover
        raise MissingFrameworkError("stdlib required") from None

    from agent_tooltrust.adapters.mcp import ToolTrustMCPWrapper

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    wrapper = ToolTrustMCPWrapper(_NullMCPClient(), engine)
    tools = _agent_tools(agent_id)

    scenario_tools: dict[str, Any] = {}
    for spec in (payload or {}).get("scenarios", []):
        entry = scenario_bound_tools(engine, [spec], agent_id)[0]
        scenario_tools[entry["name"]] = entry["fn"]

    def evaluate(call: dict[str, Any]) -> Any:
        return engine.evaluate(
            tool_name=str(call.get("tool", "")),
            action=str(call.get("action", NATIVE_ACTION)),
            environment=str(call.get("environment", NATIVE_ENVIRONMENT)),
            data_class=str(call.get("data_class", NATIVE_DATA_CLASS)),
            agent_id=agent_id,
        )

    return SimpleNamespace(
        agent_id=agent_id,
        tools=tools,
        wrapper=wrapper,
        evaluate=evaluate,
        scenario_tools=scenario_tools,
        describe=lambda: {"agent_id": agent_id, "tools": tools},
    )


class _NullMCPClient:  # pragma: no cover — never invoked in self-test
    class tools:
        @staticmethod
        def call(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
            return {"ok": True}


def _agent_tools(agent_id: str) -> list[str]:
    return {
        "mcp-01": ["query_logs", "get_weather"],
        "mcp-02": ["add", "get_current_time"],
        "mcp-03": ["get_weather", "search_docs"],
        "mcp-04": ["get_weather", "get_current_time", "add"],
        "mcp-05": ["query_logs"],
        "mcp-06": ["add", "echo"],
        "mcp-07": ["search_docs", "get_current_time"],
        "mcp-08": ["add", "get_weather", "echo"],
        "mcp-09": ["echo"],
        "mcp-10": ["get_weather", "add"],
    }.get(agent_id, ["get_weather"])
