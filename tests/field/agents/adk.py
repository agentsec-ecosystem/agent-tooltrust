"""adk build_agent — real Google ADK agents guarded by ToolTrust."""

from __future__ import annotations

from typing import Any

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from tests.field.agents import (
    API_KEY,
    ENDPOINT,
    MODEL,
    MissingFrameworkError,
    _tool_arg,
    scenario_bound_tools,
)


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

    from google.adk.models.lite_llm import LiteLlm

    from agent_tooltrust.adapters.adk import AdkAdapter

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    adapter = AdkAdapter(engine=engine)

    tools = [
        adapter.wrap_tool(_tool_arg(name, name), agent_id=agent_id)
        for name in _agent_tools(agent_id)
    ]

    for spec in (payload or {}).get("scenarios", []):
        entry = scenario_bound_tools(engine, [spec], agent_id)[0]
        tools.append(entry["fn"])

    agent = Agent(
        name=agent_id.replace("-", "_"),
        model=LiteLlm(model=f"openai/{MODEL}", api_base=ENDPOINT, api_key=API_KEY),
        tools=tools,
    )
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
