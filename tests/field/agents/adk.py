"""adk build_agent — real Google ADK agents guarded by ToolTrust."""

from __future__ import annotations

from typing import Any

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from tests.field.agents import MODEL, MissingFrameworkError, _tool_arg


def build_agent(agent_id: str = "adk-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a real Google ADK Agent for the given roster agent.

    Tools are plain functions guarded with :class:`~agent_tooltrust.adapters.adk.AdkAdapter`.

    Args:
        agent_id: Roster agent id (adk-01 .. adk-08).
        payload: Optional overrides (engine, policy).

    Returns:
        A ``google.adk.agents.Agent`` with guarded tool functions.
    """
    try:
        from google.adk.agents import Agent
    except ImportError as exc:
        raise MissingFrameworkError(
            "adk shim requires google-adk; install with `pip install google-adk`"
        ) from exc

    from agent_tooltrust.adapters.adk import AdkAdapter

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    adapter = AdkAdapter(engine=engine)

    tools = [
        adapter.wrap_tool(_tool_arg(name, name), agent_id=agent_id)
        for name in _agent_tools(agent_id)
    ]

    agent = Agent(name=agent_id, model=MODEL, tools=tools)
    agent._tool_names = _agent_tools(agent_id)  # type: ignore[attr-defined]
    return agent


def _agent_tools(agent_id: str) -> list[str]:
    return {
        "adk-01": ["get_weather"],
        "adk-02": ["add"],
        "adk-03": ["get_weather", "get_current_time"],
        "adk-04": ["add", "get_weather", "echo"],
        "adk-05": ["query_logs"],
        "adk-06": ["run_query", "read_file"],
        "adk-07": ["deploy_service", "query_logs"],
        "adk-08": ["search_docs", "http_get"],
    }.get(agent_id, ["get_weather"])
