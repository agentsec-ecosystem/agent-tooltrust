"""PDP HTTP endpoint — POST /authorize for fleet managers and gateways.

Accepts a JSON tool call and returns the Decision dict from
``ServerCore.evaluate`` — the language-agnostic policy decision point
contracted for M6 (F-43) and used by the AgentControlPlane fleet manager
(#112). Malformed requests fail with a 400 JSON error.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

_REQUIRED_FIELDS = ("tool_name", "action", "environment", "data_class", "agent_id")


def register_pdp_routes(mcp: Any, core: Any) -> None:
    """Register the POST /authorize PDP route on a FastMCP server.

    Args:
        mcp: A FastMCP server instance.
        core: A :class:`ServerCore` instance.
    """

    @mcp.custom_route("/authorize", methods=["POST"])  # type: ignore[untyped-decorator]
    async def authorize(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "request body must be valid JSON"}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse({"error": "request body must be a JSON object"}, status_code=400)

        missing = [
            field
            for field in _REQUIRED_FIELDS
            if not isinstance(body.get(field), str) or not body[field].strip()
        ]
        if missing:
            return JSONResponse(
                {"error": f"missing or blank required field(s): {', '.join(sorted(missing))}"},
                status_code=400,
            )

        decision = core.evaluate(
            tool_name=body["tool_name"],
            action=body["action"],
            environment=body["environment"],
            data_class=body["data_class"],
            agent_id=body["agent_id"],
            session_id=body.get("session_id"),
            arguments=body.get("arguments"),
            context=body.get("context"),
        )
        return JSONResponse(decision)
