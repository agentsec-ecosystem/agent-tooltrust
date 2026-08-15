"""smolagents build_agent — real smolagents agents guarded by ToolTrust."""

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
    scenario_bound_tools,
)


def build_agent(agent_id: str = "sm-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a real smolagents ``ToolCallingAgent`` for the given roster agent.

    The tool is guarded with :class:`~agent_tooltrust.adapters.smolagents.SmolagentsAdapter`.

    Args:
        agent_id: Roster agent id (sm-01 .. sm-10).
        payload: Optional overrides (engine, policy).

    Returns:
        A smolagents ``ToolCallingAgent`` with a guarded tool.
    """
    try:
        from smolagents import LiteLLMModel, ToolCallingAgent, tool
    except ImportError as exc:
        raise MissingFrameworkError(
            "smolagents shim requires smolagents; install with `pip install smolagents`"
        ) from exc

    from agent_tooltrust.adapters.smolagents import SmolagentsAdapter

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    adapter = SmolagentsAdapter(engine=engine)

    model = LiteLLMModel(
        model_id=f"openrouter/{MODEL}" if "openrouter.ai" in ENDPOINT else f"openai/{MODEL}",
        api_base=ENDPOINT,
        api_key=API_KEY,
        temperature=TEMPERATURE,
    )

    names = _agent_tools(agent_id)

    @tool
    def get_weather(city: str) -> str:
        """Get the current weather for a city.

        Args:
            city: Name of the city to fetch weather for.
        """
        return f"The weather in {city} is sunny at 20C."

    guarded = adapter.wrap_tool(
        get_weather,
        tool_name=names[0],
        action=NATIVE_ACTION,
        environment=NATIVE_ENVIRONMENT,
        data_class=NATIVE_DATA_CLASS,
        agent_id=agent_id,
    )

    tools = [guarded]

    for spec in (payload or {}).get("scenarios", []):
        entry = scenario_bound_tools(engine, [spec], agent_id)[0]
        fn = entry["fn"]

        # Closure factory avoids late-binding; the exposed signature is only
        # `text` — smolagents serializes the signature into the tool schema, so
        # a bound dict param would serialize to {} and break the call.
        def _make_scenario_tool(tool_fn: Any) -> Any:
            @tool
            def _scn(text: str = "x") -> str:
                """Run a single scenario tool call.

                Args:
                    text: The raw input to pass through to the guard.
                """
                try:
                    return str(tool_fn(text=text))
                except Exception as exc:
                    return str(exc)

            return _scn

        scenario_tool = _make_scenario_tool(fn)
        scenario_tool.name = entry["name"]
        tools.append(scenario_tool)

    agent = ToolCallingAgent(
        tools=tools,
        model=model,
        max_steps=6,
    )
    agent._tool_names = _agent_tools(agent_id)  # type: ignore[attr-defined]
    return agent


def _agent_tools(agent_id: str) -> list[str]:
    return {
        "sm-01": ["get_weather"],
        "sm-02": ["add", "get_current_time"],
        "sm-03": ["execute_shell", "read_file"],
        "sm-04": ["get_weather", "search_docs"],
        "sm-05": ["query_logs"],
        "sm-06": ["search_docs", "http_get"],
        "sm-07": ["http_get", "query_logs"],
        "sm-08": ["read_file", "write_file"],
        "sm-09": ["echo"],
        "sm-10": ["http_get", "http_post"],
    }.get(agent_id, ["get_weather"])
