"""Demo Agent — a reference agent showing ToolTrust's four decision types.

Issue F-91 / WBS M8 Task 1. Runs a single guided session with the raw Python
adapter (``@engine.guard``) and prints the outcome of five calls that cover
the full decision spectrum — **allow, audit, escalate, deny, and replan**.

Each tool is decorated with the engine and executed inside a tagged session.
A deny or escalate raises :class:`ToolTrustDecisionError`, which the agent
catches and turns into a user-facing message. The final "replan" step shows
the corrective flow: a blocked destructive write is replanned to a benign
read that the engine allows.

Run: ``python examples/demo-agent/demo.py``
"""

from __future__ import annotations

from collections.abc import Callable

from agent_tooltrust.adapters.raw import RawAdapter, ToolTrustDecisionError
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy


def _banner(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def main() -> None:
    # 1. Build the engine and the raw adapter (the only integration point).
    engine = Engine(default_policy("balanced"))
    adapter = RawAdapter(engine)

    # 2. Define the agent's tools, each guarded by the engine.
    @adapter.guard(
        tool_name="query_logs",
        action="read",
        environment="staging",
        data_class="internal",
    )
    def query_logs(query: str) -> str:
        return f"rows for {query!r}"

    @adapter.guard(
        tool_name="deploy_service",
        action="deploy",
        environment="production",
        data_class="restricted",
    )
    def deploy_service(service: str) -> str:
        return f"deployed {service}"

    @adapter.guard(
        tool_name="drop_database",
        action="delete",
        environment="staging",
        data_class="restricted",
    )
    def drop_database_staging(db: str) -> str:
        return f"dropped {db} in staging"

    @adapter.guard(
        tool_name="drop_database",
        action="delete",
        environment="production",
        data_class="restricted",
    )
    def drop_database_prod(db: str) -> str:
        return f"dropped {db} in production"  # pragma: no cover - never runs

    def execute(
        fn: Callable[..., str],
        meta: dict[str, str],
        *args: object,
        **kwargs: object,
    ) -> None:
        """Show the engine's decision, then run the guarded tool.

        ``meta`` carries the same identity used by the guard so the printed
        decision matches what the guard enforces. An ``audit`` verdict is
        informational here: the call still executes but is logged for review.
        """
        decision = engine.evaluate(
            tool_name=meta["tool_name"],
            action=meta["action"],
            environment=meta["environment"],
            data_class=meta["data_class"],
            agent_id=meta["agent_id"],
        )
        print(f"  decision: {decision.decision.upper()} ({decision.reason_code})")
        print(f"  explain : {decision.explanation}")
        if decision.decision in ("deny", "escalate"):
            print("  -> not executed (engine blocked)")
            return
        try:
            print(f"  -> executed: {fn(*args, **kwargs)}")
        except ToolTrustDecisionError as exc:
            d = exc.decision
            print(f"  -> {d.decision.upper()} (raised) {d.reason_code}")

    _banner("1. ALLOW  - low-risk read in a safe environment")
    with adapter.session(agent_id="ops-bot", session_id="demo-001"):
        execute(
            query_logs,
            {
                "tool_name": "query_logs",
                "action": "read",
                "environment": "staging",
                "data_class": "internal",
                "agent_id": "ops-bot",
            },
            query="SELECT * FROM errors WHERE level='critical'",
        )

    _banner("2. AUDIT  - destructive op, safe env, trusted agent (logged)")
    # Same tool in staging by a low-risk, trusted agent is medium-risk -> audit.
    with adapter.session(agent_id="release-bot", session_id="demo-002"):
        execute(
            drop_database_staging,
            {
                "tool_name": "drop_database",
                "action": "delete",
                "environment": "staging",
                "data_class": "restricted",
                "agent_id": "release-bot",
            },
            db="temp_scratch",
        )

    _banner("3. ESCALATE - write to production requires an approver")
    with adapter.session(agent_id="ops-bot", session_id="demo-003"):
        execute(
            deploy_service,
            {
                "tool_name": "deploy_service",
                "action": "deploy",
                "environment": "production",
                "data_class": "restricted",
                "agent_id": "ops-bot",
            },
            service="checkout-api",
        )

    _banner("4. DENY  - destructive write to production is blocked")
    with adapter.session(agent_id="ops-bot", session_id="demo-004"):
        execute(
            drop_database_prod,
            {
                "tool_name": "drop_database",
                "action": "delete",
                "environment": "production",
                "data_class": "restricted",
                "agent_id": "ops-bot",
            },
            db="users",
        )

    _banner("5. REPLAN - blocked destructive write -> safe read")
    with adapter.session(agent_id="ops-bot", session_id="demo-005"):
        try:
            drop_database_prod(db="archive_2020")
        except ToolTrustDecisionError as exc:
            print(f"  [Denied] {exc.decision.reason_code}")
            print("  [Replan] switching to a benign read...")
        execute(
            query_logs,
            {
                "tool_name": "query_logs",
                "action": "read",
                "environment": "staging",
                "data_class": "internal",
                "agent_id": "ops-bot",
            },
            query="SELECT count(*) FROM archive_2020",
        )


if __name__ == "__main__":
    main()
