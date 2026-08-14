"""M2 Task 3 — dispatcher parser (F-87, #106).

Agents frequently smuggle tool calls through a free-form ``bash``/``git``/
``http``/``aws`` command instead of calling a discrete ToolTrust tool. This
module parses those raw command strings into a canonical ``(tool, action,
args)`` triple and evaluates that canonical call against the *same* policy —
so a ``git push --force`` smuggled through a shell is denied the moment the
policy denies a forced push.

If the raw input cannot be parsed into a canonical call, the dispatcher
fails closed: the outcome is a deny, never a silent pass-through. This is the
"dispatcher-bypass" defence (F-87): a call cannot escape policy evaluation
just because it was expressed as an opaque command string.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any

from agent_tooltrust.errors import DENY_UNPARSEABLE_INPUT
from agent_tooltrust.types import NormalizedCall


def _shlex_split(raw: str) -> list[str]:
    """Split a command line into tokens, erroring on unmatched quotes."""
    if not raw or not raw.strip():
        raise DispatcherError("empty command")
    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        raise DispatcherError(f"unparseable quoting: {exc}") from exc
    if not tokens:
        raise DispatcherError("empty command")
    return tokens


class DispatcherException(Exception):
    """Base class for dispatch parsing failures."""


class DispatcherError(DispatcherException):
    """Raised when a raw command cannot be mapped to a canonical call."""


@dataclass(frozen=True)
class ParsedCall:
    """A canonical tool call extracted from a raw command string.

    Attributes:
        tool: The taxonomy tool name the command resolves to.
        action: The canonical action verb (e.g. ``"force_push"``).
        args: The structured arguments extracted from the command line.
        raw: The original un-parsed command string (for audit).
    """

    tool: str
    action: str
    args: dict[str, Any] = field(default_factory=dict)
    raw: str = ""

    def to_normalized_call(
        self, *, environment: str, data_class: str, agent_id: str
    ) -> NormalizedCall:
        """Convert this canonical call into a normalizable call.

        Args:
            environment: The session environment for the call.
            data_class: The data-class label for the call.
            agent_id: The calling agent identity.

        Returns:
            A :class:`NormalizedCall` produced by the engine's normalize stage
            (via ``normalize``), carrying the parsed tool/action and args.
        """
        from agent_tooltrust.engine.normalize import normalize

        return normalize(
            tool=self.tool,
            action=self.action,
            environment=environment,
            data_class=data_class,
            agent_id=agent_id,
            arguments=self.args,
        )


def parse_bash(raw: str) -> ParsedCall:
    """Parse a ``bash`` command into a canonical tool call.

    Supports ``git`` subcommands (mapped onto the git taxonomy tools) and
    generic execution (``execute_shell``). ``git push --force`` maps to
    ``git_push`` with the ``force_push`` action; ``git push`` maps to
    ``git_push`` with the ``push`` action. Anything else is execution.

    Args:
        raw: The raw bash command string.

    Returns:
        The canonical :class:`ParsedCall`.

    Raises:
        DispatcherError: The command is empty or cannot be parsed.
    """
    tokens = _shlex_split(raw)
    first = tokens[0]
    if first == "git":
        strip = tokens[1:]
        if not strip:
            raise DispatcherError("git command missing subcommand")
        return _parse_git(tokens[1:], raw)
    return ParsedCall(
        tool="execute_shell", action="exec", args=_token_args_after(tokens, 0), raw=raw
    )


def parse_git(raw: str) -> ParsedCall:
    """Parse a ``git`` command (optionally without the leading ``git``).

    Args:
        raw: The raw git command string (``"git push --force"`` or ``"push"``).

    Returns:
        The canonical :class:`ParsedCall`.

    Raises:
        DispatcherError: The command is empty or not a known git verb.
    """
    tokens = _shlex_split(raw)
    if tokens and tokens[0] == "git":
        tokens = tokens[1:]
    if not tokens:
        raise DispatcherError("git command missing subcommand")
    return _parse_git(tokens, raw)


def parse_http(raw: str) -> ParsedCall:
    """Parse an ``http`` command (``GET /path``, ``curl -X POST url``, ...).

    Args:
        raw: The raw http/curl command string.

    Returns:
        The canonical :class:`ParsedCall`.

    Raises:
        DispatcherError: The command is empty or has no recognized method.
    """
    tokens = _shlex_split(raw)
    first = tokens[0].upper()
    if first in ("GET", "PUT", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"):
        verb = first.lower()
        return ParsedCall(
            tool=f"http_{verb}", action=verb, args=_token_args_after(tokens, 1), raw=raw
        )
    # curl/httpie style: find an explicit -X METHOD
    if first == "CURL":
        rest = [t for t in tokens[1:] if t not in ("-s", "-S", "-i", "-v", "-L")]
        method = "get"
        for i, tok in enumerate(rest):
            if tok == "-X" and i + 1 < len(rest):
                method = rest[i + 1].lower()
                break
        return ParsedCall(
            tool=f"http_{method}", action=method, args=_token_args_after(rest, 0), raw=raw
        )
    # bare URL with no method → GET
    if "://" in first:
        return ParsedCall(tool="http_get", action="get", args={"url": first}, raw=raw)
    raise DispatcherError(f"unsupported http verb {tokens[0]!r}")


def parse_aws(raw: str) -> ParsedCall:
    """Parse an ``aws`` CLI command into a canonical tool call.

    Supports ``aws s3`` and ``aws ec2`` subcommands; a service call maps onto
    a canonical ``cloud`` tool. The action is derived from the subcommand
    (``get``/``describe``/``list`` → read, ``create``/``put`` → write,
    ``delete``/``remove`` → delete).

    Args:
        raw: The raw aws command string (``"aws s3 cp src dst"``).

    Returns:
        The canonical :class:`ParsedCall`.

    Raises:
        DispatcherError: The command is empty or not a recognized aws shape.
    """
    tokens = _shlex_split(raw)
    if tokens and tokens[0] == "aws":
        tokens = tokens[1:]
    if len(tokens) < 2:
        raise DispatcherError("aws command needs service + subcommand")
    service, sub = tokens[0], tokens[1]
    action = _aws_action(sub)
    args = _token_args_after(tokens, 2)
    args.setdefault("service", service)
    if service == "s3":
        tool = "http_get" if action == "read" else f"cloud_{action}"
    else:
        tool = f"cloud_{action}"
    return ParsedCall(tool=tool, action=action, args=args, raw=raw)


def _aws_action(subcommand: str) -> str:
    """Map an aws subcommand to a canonical action verb."""
    lowersub = subcommand.lower()
    if lowersub.startswith(("delete", "remove", "terminate", "destroy", "drop")):
        return "delete"
    if lowersub.startswith(("create", "put", "write", "upload", "update", "modify", "attach")):
        return "write"
    if lowersub.startswith(("get", "list", "describe", "read", "head", "download")):
        return "read"
    return "write"


def _parse_git(tokens: list[str], raw: str) -> ParsedCall:
    """Map the tokens after a leading ``git`` to a canonical git call."""
    verb = tokens[0] if tokens else ""
    rest = tokens[1:]
    force = "--force" in rest or "-f" in rest or "--force-with-lease" in rest
    args = _token_args_after(tokens, 1)
    if verb == "push":
        action = "force_push" if force else "push"
        return ParsedCall(tool="git_push", action=action, args=args, raw=raw)
    if verb == "pull":
        return ParsedCall(tool="git_pull", action="pull", args=args, raw=raw)
    if verb == "status":
        return ParsedCall(tool="git_status", action="status", args=args, raw=raw)
    raise DispatcherError(f"unsupported git verb {verb!r}")


def _token_args_after(tokens: list[str], index: int) -> dict[str, Any]:
    """Return remaining tokens after *index* as a positional arg list."""
    return {"args": list(tokens[index:])} if index < len(tokens) else {}


def dispatch(
    raw: str,
    *,
    kind: str = "bash",
    environment: str,
    data_class: str,
    agent_id: str,
    engine: Any,
) -> Any:
    """Parse *raw* and evaluate the canonical call against *engine*.

    This is the end-to-end dispatcher entry point: it classifies the command
    kind, parses it into a canonical call, and runs the engine's normal
    evaluation on that canonical call. Unparseable input fails closed to a
    deny.

    Args:
        raw: The raw command string from the agent.
        kind: One of ``"bash"``, ``"git"``, ``"http"``, ``"aws"``.
        environment: Session environment for the evaluated call.
        data_class: Data-class label for the evaluated call.
        agent_id: The calling agent identity.
        engine: The :class:`Engine` to evaluate through.

    Returns:
        The :class:`Decision` from evaluating the canonical call, or a deny
        with ``DENY_UNPARSEABLE_INPUT`` when parsing fails.
    """
    from agent_tooltrust.engine.engine import Engine
    from agent_tooltrust.engine.fail_closed import deny

    if not isinstance(engine, Engine):
        raise TypeError("dispatch() requires an Engine")
    parsers = {"bash": parse_bash, "git": parse_git, "http": parse_http, "aws": parse_aws}
    parser = parsers.get(kind)
    if parser is None:
        return deny(DENY_UNPARSEABLE_INPUT, f"unsupported dispatch kind {kind!r}")
    try:
        parsed = parser(raw)
    except DispatcherError as exc:
        return deny(DENY_UNPARSEABLE_INPUT, f"cannot parse {kind!r} command: {exc}")
    return engine.evaluate(
        tool_name=parsed.tool,
        action=parsed.action,
        environment=environment,
        data_class=data_class,
        agent_id=agent_id,
        arguments=parsed.args,
    )
