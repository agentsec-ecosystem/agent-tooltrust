"""autogen build_agent — real AutoGen/AG2 agents guarded by ToolTrust."""

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


def build_agent(agent_id: str = "ag-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a real AutoGen (AG2) ``AssistantAgent`` for the given roster agent.

    Tools are guarded with :class:`~agent_tooltrust.adapters.autogen.AutoGenAdapter`.

    Args:
        agent_id: Roster agent id (ag-01 .. ag-08).
        payload: Optional overrides (engine, policy).

    Returns:
        An ``autogen_agentchat.agents.AssistantAgent`` with a tool client
        wired to the local endpoint.
    """
    try:
        from autogen_agentchat.agents import AssistantAgent
        from autogen_core.models import ModelInfo
        from autogen_ext.models.openai import OpenAIChatCompletionClient
    except ImportError as exc:
        raise MissingFrameworkError(
            "autogen shim requires autogen-agentchat + autogen-ext; "
            "install with `pip install 'autogen-agentchat' 'autogen-ext[openai]'`"
        ) from exc

    from agent_tooltrust.adapters.autogen import AutoGenAdapter

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    adapter = AutoGenAdapter(engine=engine)

    model_client = OpenAIChatCompletionClient(
        model=MODEL,
        base_url=ENDPOINT,
        api_key=API_KEY,
        model_info=ModelInfo(
            vision=False,
            function_calling=True,
            json_output=False,
            structured_output=False,
            family="unknown",
        ),
    )

    tools = [
        adapter.wrap_tool(_tool_arg(name, name), agent_id=agent_id)
        for name in _agent_tools(agent_id)
    ]

    for spec in (payload or {}).get("scenarios", []):
        entry = scenario_bound_tools(engine, [spec], agent_id)[0]
        tools.append(entry["fn"])

    agent = AssistantAgent(
        name=agent_id.replace("-", "_"),
        model_client=model_client,
        system_message="You are a helpful assistant with a few tools.",
        tools=tools,
        reflect_on_tool_use=True,
    )
    agent._tool_names = _agent_tools(agent_id)  # type: ignore[attr-defined]
    return agent


def _agent_tools(agent_id: str) -> list[str]:
    return {
        "ag-01": ["get_weather"],
        "ag-02": ["add"],
        "ag-03": ["get_weather", "get_current_time"],
        "ag-04": ["add", "get_current_time"],
        "ag-05": ["query_logs"],
        "ag-06": ["get_weather", "add"],
        "ag-07": ["add", "get_weather", "echo"],
        "ag-08": ["search_docs", "get_current_time"],
    }.get(agent_id, ["get_weather"])
