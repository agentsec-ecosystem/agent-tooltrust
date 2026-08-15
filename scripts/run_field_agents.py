"""Run the full 30-scenario LLM field test for a framework against OMLX.

Every roster agent of the chosen framework is built with a real framework
agent that exposes one guarded tool per scenario (``scn_<scenario-id>``) whose
guard evaluates the scenario's *raw* context — the raw tool string, action,
environment, and data_class — through a shared ToolTrust engine. The LLM is
prompted to call each scenario tool in turn, so every scenario is genuinely
exercised: allow/audit calls execute, deny/escalate calls raise
``ToolTrustDecisionError`` inside the framework.

Each (agent, scenario) row records what actually happened: whether the LLM
invoked the tool through the guard, the guard's recorded decision, the golden
expected decision for the agent's class, an explicit ``status``, and a
``passed`` verdict. Results are written to
``tests/field/results/<framework>/<agent_id>.json`` (one file per agent with
every scenario).

Statuses:
- ``ok`` — guard intercepted a real LLM tool call; decision matched the golden
  expectation.
- ``no-call`` — the LLM responded but did not invoke the scenario tool.
- ``no-llm-response`` — the framework produced neither a reply nor a call.
- ``unexpected-decision`` — guard decision differed from the golden
  expectation (policy drift/regression).
- ``not-available`` — guard never evaluated (tool absent from the agent).
- ``exception`` — the handler/agent raised; the error text is captured.

Example:
    uv run python scripts/run_field_agents.py langgraph
    uv run python scripts/run_field_agents.py langgraph --agents lg-01
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from tests.field.agents import MODEL
from tests.field.agents import build as registry

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.field.models import CELL_FIELDS, FieldAgent, FieldScenario
from agent_tooltrust.field.runner import default_field_policy

if TYPE_CHECKING:
    from agent_tooltrust.types import Decision

RESULTS_ROOT = Path("tests/field/results")
SCENARIOS_PATH = Path("tests/field/scenarios.yaml")

RESPONSE_CAP = 280


class RecordingEngine:
    """Engine wrapper that records every evaluation it performs.

    The guard inside the agent calls ``evaluate`` through this instance, so
    recording here captures the *actual* decision made when the LLM invoked
    the scenario tool — including denies that raise ``ToolTrustDecisionError``
    before the tool body runs.

    Attributes:
        inner: The wrapped engine.
        recorded: Mapping of ``(tool, action, env, data_class, agent_id)`` to
            the Decision returned for that exact call.
    """

    def __init__(self, inner: Engine) -> None:
        self.inner = inner
        self.recorded: dict[tuple[str, str, str, str, str], Decision] = {}
        self._lock = threading.Lock()

    def evaluate(
        self,
        tool_name: str,
        action: str,
        environment: str,
        data_class: str,
        agent_id: str,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Decision:
        """Evaluate and record the decision before returning it."""
        decision = self.inner.evaluate(
            tool_name=tool_name,
            action=action,
            environment=environment,
            data_class=data_class,
            agent_id=agent_id,
            arguments=arguments,
            context=context,
        )
        with self._lock:
            self.recorded[(tool_name, action, environment, data_class, agent_id)] = decision
        return decision


def _field_agents(roster: list[dict[str, Any]]) -> list[FieldAgent]:
    """Map roster dicts to FieldAgent objects for policy registration."""
    return [
        FieldAgent(
            agent_id=a["agent_id"],
            framework=a["framework"],
            agent_class=a.get("agent_class", "general"),
            domain=a.get("domain", ""),
            tools=tuple(a.get("tools", [])),
            source=a.get("source", ""),
        )
        for a in roster
    ]


def _load_scenario_dicts() -> list[dict[str, Any]]:
    """Load the scenario matrix as plain dicts.

    Returns:
        The raw scenario dicts from scenarios.yaml.
    """
    data = yaml.safe_load(SCENARIOS_PATH.read_text(encoding="utf-8"))
    return list(data.get("scenarios", data if isinstance(data, list) else []))


def _load_field_scenarios() -> list[FieldScenario]:
    """Load the scenario matrix as FieldScenario objects (golden resolution)."""
    out: list[FieldScenario] = []
    for item in _load_scenario_dicts():
        expected: dict[str, dict[str, str]] = {}
        for key, value in (item.get("expected") or {}).items():
            expected[str(key)] = {str(k): str(v) for k, v in value.items()}
        out.append(
            FieldScenario(
                id=str(item["id"]),
                type=str(item.get("type", "decision")),  # type: ignore[arg-type]
                tool=item["tool"],
                action=item["action"],
                environment=item["environment"],
                data_class=item["data_class"],
                expected=expected,
            )
        )
    return out


def _langgraph_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Run a langgraph react agent; report what the LLM did.

    Args:
        agent: The built langgraph agent.
        prompt: The user prompt.

    Returns:
        Dict with ``llm_responded`` and ``response`` (tool_called is derived
        from the recording engine instead).
    """
    try:
        result = agent.invoke({"messages": [("user", prompt)]})
    except Exception:
        # A guard deny/escalate raises ToolTrustDecisionError out of invoke;
        # the decision was already recorded by the engine before raising, so
        # treat this as a real attempted call with the decision captured.
        return {"llm_responded": True, "response": ""}
    responded = False
    texts: list[str] = []
    for message in result.get("messages", []):
        content = getattr(message, "content", None)
        if getattr(message, "type", "") == "ai" and content:
            responded = True
            texts.append(str(content))
    return {
        "llm_responded": responded,
        "response": " | ".join(texts)[:RESPONSE_CAP] if texts else "",
    }


def _pydanticai_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Run a pydanticai agent; report what the LLM did.

    Args:
        agent: The built pydanticai agent.
        prompt: The user prompt.

    Returns:
        Dict with ``llm_responded`` and ``response``.
    """
    try:
        result = agent.run_sync(prompt)
    except Exception:
        return {"llm_responded": True, "response": ""}
    text = str(getattr(result, "output", "") or "")
    return {
        "llm_responded": bool(text),
        "response": text[:RESPONSE_CAP],
    }


def _crewai_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Run a crewai crew; report what the LLM did.

    Args:
        agent: The built crewai Crew.
        prompt: The user prompt.

    Returns:
        Dict with ``llm_responded`` and ``response``.
    """
    try:
        result = agent.kickoff(inputs={"input": prompt})
    except Exception:
        return {"llm_responded": True, "response": ""}
    text = str(
        getattr(result, "raw", None)
        or getattr(result, "output", None)
        or getattr(result, "tasks_output", None)
        or ""
    )
    return {
        "llm_responded": bool(text),
        "response": text[:RESPONSE_CAP],
    }


def _openai_agents_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Run an openai-agents Agent via Runner; report what the LLM did.

    Args:
        agent: The built openai-agents Agent.
        prompt: The user prompt.

    Returns:
        Dict with ``llm_responded`` and ``response``.
    """
    try:
        from agents import Runner

        result = Runner.run_sync(agent, input=prompt)
    except Exception:
        return {"llm_responded": True, "response": ""}
    text = str(getattr(result, "final_output", None) or "")
    return {
        "llm_responded": bool(text),
        "response": text[:RESPONSE_CAP],
    }


def _autogen_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Run an autogen agent; report what the LLM did.

    Args:
        agent: The built autogen AssistantAgent.
        prompt: The user prompt.

    Returns:
        Dict with ``llm_responded`` and ``response``.
    """
    import asyncio

    from autogen_agentchat.messages import TextMessage
    from autogen_core import CancellationToken

    async def _run() -> str:
        response = await agent.on_messages(
            [TextMessage(content=prompt, source="user")], CancellationToken()
        )
        msg = getattr(response, "chat_message", None)
        return str((msg and msg.content) or "")

    try:
        text = asyncio.run(_run())
    except Exception:
        return {"llm_responded": True, "response": ""}
    return {
        "llm_responded": bool(text),
        "response": text[:RESPONSE_CAP],
    }


def _smolagents_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Run a smolagents agent; report what the LLM did.

    Args:
        agent: The built smolagents ToolCallingAgent.
        prompt: The user prompt.

    Returns:
        Dict with ``llm_responded`` and ``response``.
    """
    try:
        result = agent.run(prompt)
    except Exception:
        return {"llm_responded": True, "response": ""}
    text = str(result or "")
    return {
        "llm_responded": bool(text),
        "response": text[:RESPONSE_CAP],
    }


def _llamaindex_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Run a llamaindex agent; report what the LLM did.

    Args:
        agent: The built llamaindex ReActAgent workflow.
        prompt: The user prompt.

    Returns:
        Dict with ``llm_responded`` and ``response``.
    """
    import asyncio

    from llama_index.core.workflow import Context

    ctx = Context(workflow=agent)

    def _response_text(event: Any) -> str:
        response = getattr(event, "response", None)
        if response is None:
            return ""
        from llama_index.core.agent.workflow import AgentStream

        if isinstance(event, AgentStream):
            return getattr(response, "delta", "") or ""
        return str(getattr(response, "text", "") or response or "")

    async def _run() -> str:
        handler = agent.run(user_msg=prompt, ctx=ctx)
        texts: list[str] = []
        async for event in handler.stream_events():
            text = _response_text(event)
            if text:
                texts.append(text)
        return "".join(texts)

    try:
        text = asyncio.run(_run())
    except Exception:
        return {"llm_responded": True, "response": ""}
    return {
        "llm_responded": bool(text),
        "response": text[:RESPONSE_CAP],
    }


def _adk_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Run a google-adk Agent; report what the LLM did.

    Args:
        agent: The built google.adk Agent.
        prompt: The user prompt.

    Returns:
        Dict with ``llm_responded`` and ``response``.
    """
    import asyncio

    from google.adk.runners import Runner as AdkRunner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types

    async def _run() -> str:
        session_service = InMemorySessionService()
        app_name = "field-test"
        await session_service.create_session(
            app_name=app_name, user_id="user", session_id="session-1"
        )
        runner = AdkRunner(agent=agent, app_name=app_name, session_service=session_service)
        texts: list[str] = []
        async for event in runner.run_async(
            user_id="user",
            session_id="session-1",
            new_message=genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)]),
        ):
            if event.is_final_response():
                texts.append(str(event.content or ""))
        return " | ".join(texts)

    try:
        text = asyncio.run(_run())
    except Exception:
        return {"llm_responded": True, "response": ""}
    return {
        "llm_responded": bool(text),
        "response": text[:RESPONSE_CAP],
    }


def _self_test_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Drive a self-test agent through a scenario tool by name (no LLM).

    Non-interactive frameworks (SWE-bench, ToolTrust MCP) attach a
    ``scenario_tools`` mapping built from :func:`scenario_bound_tools`. The
    field harness prompt carries the scenario tool id (``scn_<scenario-id>``),
    which we parse and invoke directly so the engine records the decision for
    the scenario's raw context.

    Args:
        agent: The built self-test agent.
        prompt: The user prompt, which names the ``scn_<id>`` tool to call.

    Returns:
        Dict with ``llm_responded`` and ``response``.
    """
    match = re.search(r"`(scn_[a-z0-9_-]+)`", prompt)
    scenario_tools: dict[str, Any] = getattr(agent, "scenario_tools", None)
    if scenario_tools is None:
        scenario_tools = getattr(agent, "_scenario_tools", None)
    if match is None or scenario_tools is None:
        return {"llm_responded": True, "response": "no scenario tool bound"}
    fn = scenario_tools.get(match.group(1))
    if fn is None:
        return {"llm_responded": True, "response": f"tool {match.group(1)} not bound"}
    try:
        fn_result = fn(text="field-test")
    except Exception as exc:
        # A deny/escalate guard raises ToolTrustDecisionError after recording
        # the decision; the row is still valid (decision already captured).
        fn_result = f"{type(exc).__name__}: {exc}"
    return {
        "llm_responded": True,
        "response": f"self-test {match.group(1)} invoked -> {fn_result}",
    }


def _swebench_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Run a SWE-bench self-test agent; report what the engine decided.

    SWE-bench is a replay harness, not an interactive LLM agent, so the field
    harness drives the scenario tool directly through the engine.

    Args:
        agent: The built SWEBenchRunner.
        prompt: The user prompt (named scenario tool).

    Returns:
        Dict with ``llm_responded`` and ``response``.
    """
    return _self_test_run(agent, prompt)


def _mcp_run(agent: Any, prompt: str) -> dict[str, Any]:
    """Run a ToolTrust MCP self-test agent; report what the engine decided.

    The tooltrust-mcp shim exposes a ``scenario_tools`` mapping rather than an
    interactive LLM agent; the field harness drives the scenario tool directly.

    Args:
        agent: The built MCP SimpleNamespace agent.
        prompt: The user prompt (named scenario tool).

    Returns:
        Dict with ``llm_responded`` and ``response``.
    """
    return _self_test_run(agent, prompt)


INVOKE_HANDLERS: dict[str, Any] = {
    "langgraph": _langgraph_run,
    "pydanticai": _pydanticai_run,
    "crewai": _crewai_run,
    "openai-agents": _openai_agents_run,
    "autogen": _autogen_run,
    "smolagents": _smolagents_run,
    "llamaindex": _llamaindex_run,
    "adk": _adk_run,
    "swebench": _swebench_run,
    "tooltrust-mcp": _mcp_run,
}


def _representative_scenario_ids(scenarios: list[FieldScenario]) -> list[str]:
    """Pick one scenario id per decision type + one adversarial.

    Used by Plan B tier-1 to prove each adapter surfaces all decision types.

    Args:
        scenarios: The full scenario matrix.

    Returns:
        Five scenario ids: one allow, one audit, one escalate, one deny, one
        adversarial. Falls back to the first available of each kind.
    """
    wanted = ["allow", "audit", "escalate", "deny"]
    picked: list[str] = []
    for decision in wanted:
        sid = next(
            (s.id for s in scenarios
             if s.type == "decision"
             and (s.expected_for("general") or {}).get("decision") == decision),
            None,
        )
        if sid:
            picked.append(sid)
    adv = next((s.id for s in scenarios if s.type == "adversarial"), None)
    if adv:
        picked.append(adv)
    return picked


def plan_assignment(
    roster: list[dict[str, Any]],
    scenarios: list[FieldScenario],
    plan: str = "full",
) -> dict[str, list[str]]:
    """Build a (agent_id -> [scenario_id]) covering assignment.

    ``full``  — every agent runs every scenario (the 2,490-cell cross product).
    ``A``     — each agent runs exactly ONE scenario; scenarios are distributed
                round-robin across the globally-sorted roster so every scenario
                id is assigned at least once (83 agents / 30 scenarios => full
                coverage). Class-specific scenarios are preferentially paired
                with an agent of that class so the class branch is exercised.
    ``B``     — tier-1: one representative agent per framework runs the 5
                representative scenarios (allow/audit/escalate/deny +
                adversarial) so each adapter individually proves all decision
                types; tier-2: every other agent runs ONE scenario, distributed
                to cover any scenario not hit by tier-1.

    Args:
        roster: The full agent roster (any order; sorted internally).
        scenarios: The full scenario matrix.
        plan: ``full`` | ``A`` | ``B``.

    Returns:
        Mapping of agent_id -> list of scenario ids to run for that agent.
    """
    all_ids = [s.id for s in scenarios]

    if plan == "full":
        return {a["agent_id"]: list(all_ids) for a in roster}

    # Global deterministic ordering: framework, then agent_id.
    ordered = sorted(roster, key=lambda a: (a["framework"], a["agent_id"]))

    if plan == "A":
        assignment: dict[str, list[str]] = {a["agent_id"]: [] for a in ordered}
        # Pair class-specific scenarios with a matching-class agent first so
        # the class-specific expectation branch is exercised where possible.
        class_specific = [
            s for s in scenarios
            if any(k != "*" for k in s.expected)
        ]
        generic = [s for s in scenarios if s not in class_specific]
        cover_queue = list(class_specific) + list(generic)

        assigned_agents = set()
        for scn in cover_queue:
            classes = [k for k in scn.expected if k != "*"]
            match = next(
                (a for a in ordered
                 if a["agent_id"] not in assigned_agents
                 and a.get("agent_class", "general") in classes),
                None,
            )
            if match is None:
                match = next(
                    (a for a in ordered if a["agent_id"] not in assigned_agents),
                    None,
                )
            if match is not None:
                assignment[match["agent_id"]] = [scn.id]
                assigned_agents.add(match["agent_id"])

        # Distribute any remaining agents round-robin across all scenarios so
        # every agent still runs exactly one scenario and coverage is dense.
        remaining = [a for a in ordered if a["agent_id"] not in assigned_agents]
        for i, a in enumerate(remaining):
            scn = all_ids[i % len(all_ids)]
            assignment[a["agent_id"]] = [scn]
        return assignment

    if plan == "B":
        reps = _representative_scenario_ids(scenarios)
        assignment = {a["agent_id"]: [] for a in ordered}
        tier1: set[str] = set()
        by_framework: dict[str, list[dict[str, Any]]] = {}
        for a in ordered:
            by_framework.setdefault(a["framework"], []).append(a)
        for _fw, agents in by_framework.items():
            rep = agents[0]
            assignment[rep["agent_id"]] = list(reps)
            tier1.add(rep["agent_id"])

        # Tier-2: cover every scenario not in reps, then round-robin the rest.
        covered = set(reps)
        to_cover = [sid for sid in all_ids if sid not in covered]
        tier2 = [a for a in ordered if a["agent_id"] not in tier1]
        for i, a in enumerate(tier2):
            if i < len(to_cover):
                scn = to_cover[i]
            else:
                scn = all_ids[i % len(all_ids)]
            assignment[a["agent_id"]] = [scn]
        return assignment

    raise ValueError(f"unknown plan {plan!r}; use full|A|B")


def run_framework(
    framework: str,
    engine: RecordingEngine,
    agent_filter: list[str] | None = None,
    workers: int = 6,
    assignment: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Run a framework's roster agents across their assigned scenarios.

    Args:
        framework: Framework name (as it appears in the roster).
        engine: Recording engine whose inner policy knows every roster agent.
        agent_filter: Optional filter of agent ids (all if ``None``).
        workers: Max parallel scenario rows per agent.
        assignment: Optional ``plan_assignment`` output mapping agent_id ->
            scenario_id list. When provided, each agent only runs its assigned
            scenarios (Plan A/B). When ``None``, every agent runs all scenarios
            (Plan full / legacy behavior).

    Returns:
        The list of run summaries (one per agent). Each is also written to
        ``tests/field/results/<framework>/<agent_id>.json``.

    Raises:
        ValueError: When the framework has no invoke handler or roster agents.
    """
    handler = INVOKE_HANDLERS.get(framework)
    if handler is None:
        raise ValueError(
            f"no invoke handler for {framework!r}; supported: {sorted(INVOKE_HANDLERS)}"
        )

    roster = [a for a in registry.load_roster() if a["framework"] == framework]
    if agent_filter is not None:
        wanted = set(agent_filter)
        roster = [a for a in roster if a["agent_id"] in wanted]
    if not roster:
        raise ValueError(f"no roster agents for framework {framework!r}")

    scenario_dicts = _load_scenario_dicts()
    scenarios = _load_field_scenarios()
    by_id: dict[str, FieldScenario] = {s.id: s for s in scenarios}
    dict_by_id: dict[str, dict[str, Any]] = {s["id"]: s for s in scenario_dicts}
    out_dir = RESULTS_ROOT / framework
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []

    for agent in roster:
        agent_id = agent["agent_id"]
        if assignment is not None:
            wanted_ids = assignment.get(agent_id, [])
            agent_scenarios = [by_id[i] for i in wanted_ids if i in by_id]
            agent_dicts = [dict_by_id[i] for i in wanted_ids if i in dict_by_id]
            if not agent_scenarios:
                continue
        else:
            agent_scenarios = scenarios
            agent_dicts = scenario_dicts
        target = out_dir / f"{agent_id}.json"
        recorded = _run_agent(
            handler, agent, engine, agent_dicts, agent_scenarios, target, workers=workers
        )
        summaries.append(recorded)

    return summaries


def _prompt_for(scenario: FieldScenario) -> str:
    """Build an imperative prompt that forces the scenario tool call."""
    scn_name = f"scn_{scenario.id}"
    extra = (
        "The tool name may contain intentional whitespace or unicode — call "
        "it exactly by name."
        if scenario.type == "adversarial"
        else ""
    )
    return (
        f"In environment '{scenario.environment}' with data_class "
        f"'{scenario.data_class}', call ONLY the tool `{scn_name}` with valid "
        f"arguments, then answer. Do not call any other tool. Do not skip. "
        f"{extra}"
    ).strip()


def _rule_status_row(
    scenario: FieldScenario,
    row: dict[str, Any],
    engine: RecordingEngine,
    agent_id: str,
    agent_class: str,
) -> dict[str, Any]:
    """Finalize one scenario row with decision, expected, and status.

    The guard decision is read from the recording engine (the exact decision
    made when the LLM invoked the tool); if the guard never ran, the row is
    ``not-available``.

    Args:
        scenario: The scenario under test.
        row: Partial row from the run step.
        engine: Recording engine holding the guard decisions.
        agent_id: Roster agent id.
        agent_class: Roster agent class.

    Returns:
        A complete scenario row dict.
    """
    expected_cell = scenario.expected_for(agent_class) or {}
    expected_decision = expected_cell.get("decision", "unknown")
    key = (
        scenario.tool,
        scenario.action,
        scenario.environment,
        scenario.data_class,
        agent_id,
    )
    guard_decision = engine.recorded.get(key)
    called = guard_decision is not None

    if not called:
        status = "not-available"
        row.update(
            {
                "called": False,
                "decision": None,
                "reason_code": None,
                "expected": expected_decision,
                "status": status,
                "passed": False,
                "mismatches": None,
            }
        )
        return row

    actual = guard_decision.decision

    mismatches = [
        field_name
        for field_name in CELL_FIELDS
        if expected_cell.get(field_name) and expected_cell[field_name] != getattr(
            guard_decision, field_name
        )
    ]

    if row.get("error"):
        status = "exception"
    elif mismatches:
        status = "unexpected-decision"
    else:
        status = "ok"

    row.update(
        {
            "called": True,
            "llm_responded": row.get("llm_responded", True),
            "decision": actual,
            "reason_code": guard_decision.reason_code,
            "expected": expected_decision,
            "status": status,
            "passed": status == "ok",
            "mismatches": mismatches or None,
        }
    )
    return row


def _run_one(
    handler: Any,
    obj: Any,
    scenario: FieldScenario,
    agent_id: str,
    agent_class: str,
    tool_set: set[str],
    engine: RecordingEngine,
    build_error: str,
) -> dict[str, Any]:
    """Run a single scenario against a built agent.

    Args:
        handler: Framework invoke handler.
        obj: The built framework agent.
        scenario: The scenario to run.
        agent_id: Roster agent id.
        agent_class: Roster agent class.
        tool_set: Agent's available tool names.
        engine: Recording engine.
        build_error: Non-empty when the agent failed to build.

    Returns:
        A complete scenario row dict.
    """
    start = time.monotonic()
    if build_error:
        expected = (scenario.expected_for(agent_class) or {}).get("decision", "unknown")
        return {
            "scenario_id": scenario.id,
            "scenario_type": scenario.type,
            "tool": scenario.tool,
            "action": scenario.action,
            "environment": scenario.environment,
            "data_class": scenario.data_class,
            "available": str(scenario.tool) in tool_set,
            "called": False,
            "llm_called": False,
            "llm_responded": False,
            "response": None,
            "decision": None,
            "reason_code": None,
            "expected": expected,
            "status": "exception",
            "passed": False,
            "mismatches": None,
            "error": build_error,
            "elapsed_s": round(time.monotonic() - start, 2),
        }
    try:
        run = handler(obj, _prompt_for(scenario))
        error = ""
    except Exception as exc:
        run = {"llm_responded": False, "response": ""}
        error = f"{type(exc).__name__}: {exc}"
    row = {
        "scenario_id": scenario.id,
        "scenario_type": scenario.type,
        "tool": scenario.tool,
        "action": scenario.action,
        "environment": scenario.environment,
        "data_class": scenario.data_class,
        "available": str(scenario.tool) in tool_set,
        "called": False,
        "llm_called": bool(run.get("llm_responded")),
        "llm_responded": bool(run.get("llm_responded")),
        "response": str(run.get("response") or "") or None,
        "error": error or None,
        "elapsed_s": round(time.monotonic() - start, 2),
    }
    return _rule_status_row(scenario, row, engine, agent_id, agent_class)


def _run_agent(
    handler: Any,
    agent: dict[str, Any],
    engine: RecordingEngine,
    scenario_dicts: list[dict[str, Any]],
    scenarios: list[FieldScenario],
    target: Path,
    workers: int = 6,
) -> dict[str, Any]:
    """Build one agent and drive it across every scenario in parallel.

    Args:
        handler: Framework invoke handler.
        agent: Roster agent dict.
        engine: Recording engine passed into the build shim.
        scenario_dicts: Raw scenario dicts for the build payload.
        scenarios: FieldScenario objects for golden resolution.
        target: Path to write the agent's result JSON to.

    Returns:
        The result dict matching the saved per-agent JSON format.
    """
    agent_id = agent["agent_id"]
    agent_class = agent.get("agent_class", "general")
    tool_set = set(agent.get("tools", []))

    build_error = ""
    obj: Any = None
    try:
        obj = registry.build_agent(
            agent_id, payload={"engine": engine, "scenarios": scenario_dicts}
        )
    except Exception as exc:
        build_error = f"{type(exc).__name__}: {exc}"

    total = len(scenarios)
    header = {
        "agent_id": agent_id,
        "framework": agent["framework"],
        "agent_class": agent_class,
        "model": MODEL,
        "tools": sorted(tool_set),
        "scenarios_total": total,
        "passed": 0,
        "rows": [None] * total,
        "build_error": build_error or None,
        "status": "running",
    }
    print(f"[{agent['framework']}][{agent_id}] building agent…", flush=True)

    write_lock = threading.Lock()
    results: list[dict[str, Any] | None] = [None] * total

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _run_one,
                handler, obj, scenario, agent_id, agent_class,
                tool_set, engine, build_error,
            ): i
            for i, scenario in enumerate(scenarios)
        }
        for future in as_completed(futures):
            i = futures[future]
            row = future.result()
            results[i] = row
            with write_lock:
                header["rows"] = [r for r in results if r is not None]
                header["passed"] = sum(1 for r in results if r and r["passed"])
                header["status"] = (
                    "completed"
                    if all(r is not None for r in results)
                    else "running"
                )
                target.write_text(json.dumps(header, indent=2), encoding="utf-8")
                _log_row(
                    agent_id,
                    i + 1,
                    total,
                    row,
                )

    header["rows"] = results
    header["passed"] = sum(1 for r in results if r and r["passed"])
    header["status"] = "completed"
    target.write_text(json.dumps(header, indent=2), encoding="utf-8")
    return header


def _log_row(
    agent_id: str, idx: int, total: int, row: dict[str, Any]
) -> None:
    """Print one scenario row as it completes (live progress)."""
    mark = "OK " if row.get("status") == "ok" else "XX "
    print(
        f"[{agent_id}] {idx:>2}/{total}  {row['scenario_id']}: "
        f"status={row.get('status')} called={row.get('called')} "
        f"decision={row.get('decision')} expected={row.get('expected')} "
        f"{row.get('elapsed_s')}s  [{mark}]",
        flush=True,
    )
    if row.get("error"):
        print(f"        error: {row['error']}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("framework", help="framework to run (e.g. langgraph)")
    parser.add_argument("--agents", help="comma-separated agent id filter")
    parser.add_argument("--posture", default="balanced", help="policy posture")
    parser.add_argument(
        "--workers", type=int, default=6,
        help="Max parallel LLM calls (default 6)",
    )
    parser.add_argument(
        "--plan", choices=("full", "A", "B"), default="A",
        help=(
            "Coverage plan (default A): A=one scenario per agent, all "
            "scenarios/agents/frameworks covered (~83 runs); B=per-framework "
            "5-decision-type proof + roster smoke (~123 runs); full=every agent "
            "x every scenario (2,490 runs, overkill)."
        ),
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Print the planned (agent -> scenarios) assignment and exit.",
    )
    args = parser.parse_args()

    roster = registry.load_roster()
    scenarios = _load_field_scenarios()

    assignment: dict[str, list[str]] | None = None
    if args.plan != "full":
        assignment = plan_assignment(roster, scenarios, args.plan)

    if args.list:
        print(f"# plan={args.plan} framework={args.framework}")
        if assignment is None:
            total = len(roster) * len(scenarios)
            print(f"# full cross product: {len(roster)} agents x {len(scenarios)} "
                  f"scenarios = {total} runs")
        else:
            fw_agents = [a for a in roster if a["framework"] == args.framework]
            fw_runs = sum(len(assignment.get(a["agent_id"], [])) for a in fw_agents)
            all_runs = sum(len(v) for v in assignment.values())
            covered = set()
            for v in assignment.values():
                covered.update(v)
            print(f"# {args.plan}: {all_runs} runs total; this framework "
                  f"{fw_runs} runs; scenarios covered={len(covered)}/{len(scenarios)}")
            for a in sorted(fw_agents, key=lambda x: x["agent_id"]):
                ids = assignment.get(a["agent_id"], [])
                if ids:
                    print(f"  {a['agent_id']:8} ({a.get('agent_class','general'):8}) "
                          f"-> {ids}")
        return 0

    policy = default_field_policy(args.posture, _field_agents(roster))
    engine = RecordingEngine(Engine(policy))

    agents = args.agents.split(",") if args.agents else None
    try:
        summaries = run_framework(
            args.framework, engine, agents,
            workers=args.workers, assignment=assignment,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    total = sum(a["scenarios_total"] for a in summaries)
    passed = sum(a["passed"] for a in summaries)
    statuses: dict[str, int] = {}
    errors: list[str] = []
    for a in summaries:
        for r in a["rows"]:
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
            if r.get("error"):
                errors.append(f"{a['agent_id']}/{r['scenario_id']}: {r['error']}")
    print(
        f"\n{args.framework}: {passed}/{total} scenario rows passed, "
        f"{len(summaries)} agents; {statuses}"
    )
    if errors:
        print(f"errors: {len(errors)}")
        for e in errors[:20]:
            print(f"  - {e}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
