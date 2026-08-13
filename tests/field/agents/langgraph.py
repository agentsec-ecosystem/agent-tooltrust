"""langgraph build_agent — real LangGraph agent guarded by ToolTrust.

Builds a ``create_react_agent`` whose tool set is the roster agent's native
tools plus one guarded tool per scenario. Each scenario tool is named
``scn_<scenario-id>`` and its guard evaluates the scenario's *raw* context
(raw tool string including adversarial attacks, action, environment,
data_class) through the shared engine for the roster agent id — so a real LLM
attempting that tool gets the exact engine decision.
"""

from __future__ import annotations

from typing import Any

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from tests.field.agents import (
    API_KEY,
    ENDPOINT,
    MODEL,
    NATIVE_ACTION,
    NATIVE_DATA_CLASS,
    NATIVE_ENVIRONMENT,
    TEMPERATURE,
    MissingFrameworkError,
    _tool_arg,
    scenario_bound_tools,
)

_TOOLS = {
    "lg-01": ["get_weather", "get_current_time"],
    "lg-02": ["add", "get_weather"],
    "lg-03": ["get_weather", "search_docs"],
    "lg-04": ["add", "get_weather", "get_current_time"],
    "lg-05": ["query_logs", "get_current_time"],
    "lg-06": ["add", "echo"],
}


def build_agent(agent_id: str = "lg-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a real LangGraph agent with tooltrust-guarded tools.

    Args:
        agent_id: Roster agent id (lg-01 .. lg-06).
        payload: Optional overrides. ``engine`` supplies the shared policy
            engine; ``scenarios`` binds one guarded tool per scenario.

    Returns:
        A langgraph agent whose tools each evaluate through the engine.
    """
    try:
        from langchain_core.tools import tool as lg_tool
        from langchain_openai import ChatOpenAI
        try:
            from langchain.agents import create_agent as create_react_agent
        except ImportError:
            from langgraph.prebuilt import create_react_agent
    except ImportError as exc:
        raise MissingFrameworkError(
            "langgraph shim requires langgraph + langchain-openai + langchain-core"
        ) from exc

    from agent_tooltrust.adapters.raw import RawAdapter

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    adapter = RawAdapter(engine=engine)

    tools = []
    for name in _TOOLS.get(agent_id, ["get_weather"]):
        fn = _tool_arg(name, name)
        guarded = adapter.guard(
            tool_name=name, action=NATIVE_ACTION,
            environment=NATIVE_ENVIRONMENT, data_class=NATIVE_DATA_CLASS,
            agent_id=agent_id,
        )(fn)
        tools.append(lg_tool(guarded))

    for spec in (payload or {}).get("scenarios", []):
        tools.append(lg_tool(scenario_bound_tools(engine, [spec], agent_id)[0]["fn"]))

    llm = ChatOpenAI(
        model=MODEL, base_url=ENDPOINT, api_key=API_KEY, temperature=TEMPERATURE  # type: ignore[arg-type]
    )
    return create_react_agent(llm, tools)
