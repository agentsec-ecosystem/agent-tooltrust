"""MCP tool registrations for the ToolTrust server.

Provides :func:`register_tools` which decorates and registers the three MCP
tools (``tooltrust.evaluate``, ``tooltrust.explain``,
``tooltrust.session_status``) on a FastMCP server instance. Returns the
tool functions for test access.
"""

from __future__ import annotations

from typing import Any


def register_tools(
    mcp: Any,
    core: Any,
) -> dict[str, Any]:
    """Register ToolTrust MCP tools on a FastMCP server.

    Args:
        mcp: A FastMCP server instance.
        core: A :class:`ServerCore` instance wrapping Engine + SessionStore + AuditLogger.

    Returns:
        A dict mapping tool names (``tooltrust.evaluate``, etc.) to the
        registered tool function objects for test access.
    """

    @mcp.tool(  # type: ignore[untyped-decorator]
        name="tooltrust.evaluate",
        description=(
            "Evaluate whether a proposed tool call should be allowed, audited, "
            "escalated for human approval, or denied. Returns a Decision with "
            "risk factors, criticality, reason code, and explanation."
        ),
    )
    def evaluate(
        tool_name: str,
        action: str,
        environment: str,
        data_class: str,
        agent_id: str,
        session_id: str | None = None,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return core.evaluate(  # type: ignore[no-any-return]
            tool_name=tool_name,
            action=action,
            environment=environment,
            data_class=data_class,
            agent_id=agent_id,
            session_id=session_id,
            arguments=arguments,
            context=context,
        )

    @mcp.tool(  # type: ignore[untyped-decorator]
        name="tooltrust.explain",
        description=(
            "Explain why a tool call received a particular decision. "
            "Accepts either the same input as evaluate (runs the engine) "
            "or a call_id to look up a prior decision from the audit trail."
        ),
    )
    def explain(
        call_id: str | None = None,
        tool_name: str | None = None,
        action: str | None = None,
        environment: str | None = None,
        data_class: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        if call_id is not None:
            result = core.explain_from_audit(call_id)
            if result is None:
                return {"error": f"No audit entry found for call_id: {call_id}"}
            return result  # type: ignore[no-any-return]

        if not all([tool_name, action, environment, data_class, agent_id]):
            return {
                "error": (
                    "Provide either call_id or all of: "
                    "tool_name, action, environment, data_class, agent_id"
                )
            }

        decision = core.evaluate(
            tool_name=str(tool_name),
            action=str(action),
            environment=str(environment),
            data_class=str(data_class),
            agent_id=str(agent_id),
        )
        return {
            "explanation": decision["explanation"],
            "factors": decision.get("factors", []),
            "reason_code": decision["reason_code"],
            "criticality": decision["criticality"],
        }

    @mcp.tool(  # type: ignore[untyped-decorator]
        name="tooltrust.session_status",
        description=(
            "Query the status of an active session: cumulative risk score, "
            "tool call count, budget state, consent scopes, and recent "
            "decision history."
        ),
    )
    def session_status(session_id: str) -> dict[str, Any]:
        state = core.session_store.get(session_id)
        if state is None:
            return {"session_id": session_id, "error": "Session not found"}
        return {
            "session_id": state.session_id,
            "risk_score": state.risk_score,
            "tool_call_count": state.tool_call_count,
            "token_budget": state.token_budget,
            "call_budget": state.call_budget,
            "consent_scopes": state.consent_scopes,
            "decision_history": state.decision_history[-10:],
            "created_at": state.created_at,
            "last_updated": state.last_updated,
        }

    return {
        "tooltrust.evaluate": evaluate,
        "tooltrust.explain": explain,
        "tooltrust.session_status": session_status,
    }
