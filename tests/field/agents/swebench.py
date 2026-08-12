"""swebench build_agent — SWE-bench Lite tasks guarded by the M23 wrapper."""

from __future__ import annotations

from typing import Any

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from tests.field.agents import MissingFrameworkError


def build_agent(agent_id: str = "swe-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a SWE-bench-style coding agent for the given roster agent.

    Reuses the M23 :class:`~agent_tooltrust.integrations.swe_bench.SWEBenchRunner`
    with the bundled 5-task fixture; each roster agent maps to a task group.

    Args:
        agent_id: Roster agent id (swe-01 .. swe-05).
        payload: Optional overrides (engine, policy).

    Returns:
        A ``SWEBenchRunner`` configured for the agent's task group. If
        ``yaml`` fixture loading fails, returns a lightweight task holder.
    """
    try:
        from agent_tooltrust.integrations.swe_bench import SWEBenchRunner
    except ImportError as exc:  # pragma: no cover
        raise MissingFrameworkError("SWE-bench wrapper unavailable") from exc

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    group = _task_group(agent_id)
    runner = SWEBenchRunner(engine=engine)

    def _fixture_path() -> str:
        from pathlib import Path

        return str(Path(__file__).resolve().parents[2] / "fixtures" / "swe_bench_tasks.yaml")

    runner._task_group = group  # type: ignore[attr-defined]
    runner._fixture_path = _fixture_path  # type: ignore[attr-defined]
    return runner


def _task_group(agent_id: str) -> int:
    return int(agent_id.split("-")[1]) % 5
