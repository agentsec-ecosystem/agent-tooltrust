"""``tooltrust serve`` — start the ToolTrust MCP server with SSE transport."""

from __future__ import annotations

import argparse
import os
from typing import Any

from agent_tooltrust.cli.errors import CliError


def add_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    """Register the ``serve`` subcommand.

    Args:
        subparsers: The parent ``add_subparsers()`` action.
    """
    parser = subparsers.add_parser(
        "serve",
        help="Start the ToolTrust MCP server (SSE transport)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--policy-path",
        type=str,
        default=None,
        help="Path to tooltrust.yaml (overrides TOOLTRUST_POLICY_PATH env var)",
    )
    parser.add_argument(
        "--posture",
        type=str,
        default="balanced",
        choices=["balanced", "strict", "permissive"],
        help="Policy posture preset (default: balanced)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.set_defaults(func=_serve)


def _serve(args: argparse.Namespace) -> int:
    """Start the MCP server.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 on success).
    """
    try:
        from agent_tooltrust.policy.loader import load_policy
    except ImportError:
        raise CliError("Failed to import policy loader. Is agent-tooltrust installed?") from None

    from agent_tooltrust.audit.logger import AuditLogger
    from agent_tooltrust.engine.engine import Engine
    from agent_tooltrust.engine.escalation import EscalationManager
    from agent_tooltrust.policy.models import default_policy
    from agent_tooltrust.server.analytics_routes import register_analytics_routes
    from agent_tooltrust.server.audit_routes import register_audit_routes
    from agent_tooltrust.server.baselines_routes import register_baselines_routes
    from agent_tooltrust.server.dashboard import register_dashboard_route
    from agent_tooltrust.server.escalation_routes import register_escalation_routes
    from agent_tooltrust.server.mcp_tools import register_tools
    from agent_tooltrust.server.seed import register_seed_route
    from agent_tooltrust.server.server_core import ServerCore
    from agent_tooltrust.server.session_store import SessionStore
    from agent_tooltrust.server.sessions_routes import register_sessions_routes

    policy_path = args.policy_path or os.environ.get("TOOLTRUST_POLICY_PATH")

    if policy_path:
        try:
            policy = load_policy(policy_path)
        except Exception as exc:
            raise CliError(f"Failed to load policy from {policy_path}: {exc}") from exc
    else:
        policy = default_policy(args.posture)

    # Load a persisted escalation store when configured (Docker volume keeps
    # approvals/denials across container restarts).
    esc_file = os.environ.get("TOOLTRUST_ESCALATIONS_FILE")
    escalation_manager = EscalationManager.load(esc_file) if esc_file else EscalationManager()

    engine = Engine(policy, escalation_manager=escalation_manager)
    session_store = SessionStore()
    audit_logger = AuditLogger()
    core = ServerCore(engine=engine, session_store=session_store, audit_logger=audit_logger)

    from fastmcp import FastMCP

    mcp = FastMCP("ToolTrust MCP Server")
    register_tools(mcp, core)
    register_audit_routes(mcp, core)
    register_escalation_routes(mcp, core)
    register_sessions_routes(mcp, core)
    register_analytics_routes(mcp, core)
    register_baselines_routes(mcp, core)
    register_dashboard_route(mcp, core)
    register_seed_route(mcp, core)

    print(f"ToolTrust MCP server starting on http://{args.host}:{args.port}")
    print(f"  Policy: {policy_path or f'preset ({args.posture})'}")
    print(f"  MCP endpoint: SSE at http://{args.host}:{args.port}/sse")
    print(f"  Audit endpoint: http://{args.host}:{args.port}/audit")
    print(f"  Escalations endpoint: http://{args.host}:{args.port}/api/escalations")
    print(f"  Sessions endpoint: http://{args.host}:{args.port}/api/sessions/<id>")
    print(f"  Analytics endpoint: http://{args.host}:{args.port}/api/analytics")
    print(f"  Baselines endpoint: http://{args.host}:{args.port}/api/baselines")
    print(f"  Dashboard: http://{args.host}:{args.port}/dashboard")
    print(f"  Health check: http://{args.host}:{args.port}/audit/health")

    try:
        mcp.run(transport="sse", host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as exc:
        raise CliError(f"Server error: {exc}") from exc

    return 0
