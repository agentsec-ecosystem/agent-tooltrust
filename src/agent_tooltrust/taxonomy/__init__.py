"""The canonical taxonomy of what agents do.

This is the starter vocabulary for ToolTrust: a curated, append-only map of
domains → verbs → baseline risk. Every tool call from every framework
normalizes onto these verbs. Writing one risk rule for ``db.query`` covers
PostgreSQL, SQLite, and the MCP database adapter at once.

The taxonomy is loaded by the engine at startup and is the reference for the
normalize stage (tool → domain, action verb → action class). It ships in the
package as Python data; orgs extend it via community packs (v0.3).
"""

from __future__ import annotations

DOMAINS: tuple[str, ...] = (
    "fs",
    "shell",
    "http",
    "db",
    "git",
    "email",
    "cloud",
    "secrets",
    "iam",
    "payment",
    "approval",
    "search",
    "notify",
)

#: Baseline risk (0.0-1.0) per domain, from the PRD starter taxonomy.
#: High-destruction or high-access domains (secrets, iam, payment, approval)
#: are weighted above ordinary write domains.
DOMAIN_BASELINE: dict[str, float] = {
    "fs": 0.3,
    "shell": 0.8,
    "http": 0.3,
    "db": 0.6,
    "git": 0.3,
    "email": 0.6,
    "cloud": 0.6,
    "secrets": 0.9,
    "iam": 0.9,
    "payment": 0.9,
    "approval": 0.9,
    "search": 0.1,
    "notify": 0.3,
}

#: Verbs per domain. Every verb resolves to an action class via ACTION_CLASSES.
DOMAIN_VERBS: dict[str, tuple[str, ...]] = {
    "fs": ("read", "write", "delete", "list", "move"),
    "shell": ("exec", "pipe"),
    "http": ("get", "post", "put", "delete", "patch"),
    "db": ("query", "execute", "migrate", "drop"),
    "git": (
        "status",
        "diff",
        "log",
        "commit",
        "push",
        "force_push",
        "branch",
        "merge",
        "clone",
    ),
    "email": ("read", "send", "delete", "search"),
    "cloud": ("list", "describe", "create", "update", "delete", "scale"),
    "secrets": ("read", "write", "rotate", "revoke"),
    "iam": ("read_role", "assign_role", "revoke_role", "create_key"),
    "payment": ("read", "refund", "transfer", "charge"),
    "approval": ("read", "approve", "deny", "delegate"),
    "search": ("query", "index", "delete_index"),
    "notify": ("send_slack", "send_teams", "send_webhook", "page"),
}

#: Action verb → action class (read | write | delete | grant).
#: Read-family verbs are zero risk; grant verbs are the highest-risk class.
ACTION_CLASSES: dict[str, str] = {
    # read
    "read": "read",
    "list": "read",
    "describe": "read",
    "status": "read",
    "diff": "read",
    "log": "read",
    "query": "read",
    "get": "read",
    "search": "read",
    "read_role": "read",
    # write
    "write": "write",
    "create": "write",
    "update": "write",
    "send": "write",
    "post": "write",
    "put": "write",
    "patch": "write",
    "execute": "write",
    "migrate": "write",
    "scale": "write",
    "commit": "write",
    "push": "write",
    "merge": "write",
    "clone": "write",
    "branch": "write",
    "move": "write",
    "index": "write",
    "rotate": "write",
    "refund": "write",
    "send_slack": "write",
    "send_teams": "write",
    "send_webhook": "write",
    "page": "write",
    "pipe": "write",
    "exec": "write",
    "deny": "write",
    # delete
    "delete": "delete",
    "drop": "delete",
    "revoke": "delete",
    "force_push": "delete",
    "delete_index": "delete",
    # grant
    "assign_role": "grant",
    "revoke_role": "grant",
    "create_key": "grant",
    "approve": "grant",
    "delegate": "grant",
}

#: Known tool names → domain. This is the starter seed; covers the demo
#: scenario calls and common infrastructure/coding agent tools.
KNOWN_TOOLS: dict[str, str] = {
    # search
    "query_logs": "search",
    "query_metrics": "search",
    "search_docs": "search",
    # secrets
    "read_secrets": "secrets",
    "write_secret": "secrets",
    "rotate_secret": "secrets",
    "revoke_secret": "secrets",
    # cloud
    "deploy_service": "cloud",
    "create_ec2": "cloud",
    "describe_instances": "cloud",
    "scale_cluster": "cloud",
    "delete_instance": "cloud",
    # db
    "query_database": "db",
    "run_query": "db",
    "run_migration": "db",
    "drop_database": "db",
    # shell
    "execute_shell": "shell",
    "run_shell": "shell",
    # fs
    "read_file": "fs",
    "write_file": "fs",
    "delete_file": "fs",
    "list_dir": "fs",
    # email
    "send_email": "email",
    "read_email": "email",
    # git
    "commit_changes": "git",
    "push_changes": "git",
    "force_push": "git",
    "clone_repo": "git",
    # http
    "http_get": "http",
    "http_post": "http",
    "http_patch": "http",
    # iam
    "create_api_key": "iam",
    "assign_role": "iam",
    "revoke_role": "iam",
    # payment
    "charge_customer": "payment",
    "refund_customer": "payment",
    "transfer_funds": "payment",
    # approval
    "approve_request": "approval",
    # notify
    "page_oncall": "notify",
    "send_slack": "notify",
}

#: Conservative action-class for a verb we have not seen before. An unknown
#: verb is treated as a write (never an allow-by-default read).
_UNKNOWN_ACTION_CLASS = "write"

#: Baseline risk value per action class (0.0-1.0). Read-family verbs are
#: zero risk; delete and grant are the highest-risk classes.
ACTION_VALUES: dict[str, float] = {
    "read": 0.0,
    "write": 0.3,
    "delete": 1.0,
    "grant": 1.0,
}


def is_known_tool(tool: str) -> bool:
    """Return True if *tool* resolves to a domain in the taxonomy."""
    return tool in KNOWN_TOOLS


def domain_for(tool: str) -> str | None:
    """Return the domain for a known tool, or None if the tool is unknown."""
    return KNOWN_TOOLS.get(tool)


def action_class_for(action: str) -> str:
    """Map an action verb to its action class (read/write/delete/grant).

    Unknown verbs resolve conservatively to ``write`` so that novel actions
    are never scored as zero-risk reads.
    """
    return ACTION_CLASSES.get(action, _UNKNOWN_ACTION_CLASS)


def taxonomy_summary() -> str:
    """Human-readable summary of the taxonomy, one line per domain."""
    lines = [f"ToolTrust taxonomy: {len(DOMAINS)} domains"]
    for domain in DOMAINS:
        lines.append(f"  {domain}: {len(DOMAIN_VERBS[domain])} verbs")
    return "\n".join(lines) + "\n"
