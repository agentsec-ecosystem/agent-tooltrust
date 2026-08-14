"""Compliance baseline HTTP endpoint for the ToolTrust MCP server (M7.5).

Returns a static posture report mapping the project's three compliance tiers
(essential / hardened / certified) to their checks, plus OWASP ASVS and
OpenSSF SLSA coverage. Static today; a live signal can replace it later
without changing the payload shape.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse


def register_baselines_routes(mcp: Any, core: Any) -> None:
    """Register the /api/baselines compliance-posture endpoint.

    Args:
        mcp: A FastMCP server instance.
        core: A :class:`ServerCore` instance (unused; posture is static).
    """
    _register_baselines(mcp, core)


def _register_baselines(mcp: Any, core: Any) -> None:
    @mcp.custom_route("/api/baselines", methods=["GET"])  # type: ignore[untyped-decorator]
    async def baselines(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "essential": {
                    "status": "pass",
                    "checks": ["decision engine", "audit trail", "policy validation"],
                },
                "hardened": {
                    "status": "pending",
                    "checks": ["argument policy", "scope enforcement", "dispatcher parser"],
                },
                "certified": {
                    "status": "pending",
                    "checks": [
                        "tamper-evident audit",
                        "output inspection",
                        "external review",
                    ],
                },
                "owasp": {"covered": 5, "total": 10},
                "openssf": {"status": "silver", "target": "gold"},
            }
        )
