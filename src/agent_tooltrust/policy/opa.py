"""M2.6 — OPA/Rego backend (#6, F-10, F-63).

``opa_evaluate`` calls ``opa eval`` as a subprocess with the normalized call as
JSON input and a Rego policy. The result is mapped to a native ``Decision``.

Fail-closed: an unreachable OPA binary, a non-zero exit, or unparseable output
all raise :class:`OpaUnavailableError` with reason
``DENY_OPA_BACKEND_DOWN``.
"""

from __future__ import annotations

import json
import subprocess

from agent_tooltrust.errors import OpaUnavailableError
from agent_tooltrust.types import Decision, NormalizedCall


def opa_evaluate(
    call: NormalizedCall,
    rego_policy_path: str,
    opa_binary: str = "opa",
    timeout_seconds: int = 5,
) -> Decision:
    """Evaluate *call* against a Rego policy via ``opa eval``.

    Args:
        call: Normalized call to evaluate (serialized as JSON input).
        rego_policy_path: Path to a Rego file or bundle directory.
        opa_binary: Name or path of the ``opa`` executable.
        timeout_seconds: Subprocess timeout.

    Returns:
        A :class:`Decision` mirroring the Rego rule evaluation.

    Raises:
        :class:`OpaUnavailableError`: OPA binary not found, non-zero exit,
            or output could not be parsed.

    The Rego policy must define a rule at ``data.tooltrust.decision`` that
    returns an object with ``decision``, ``reason_code``, ``explanation``,
    and optionally ``risk_score`` and ``criticality`` fields.
    """
    normalized = {
        "tool": call.tool,
        "tool_category": call.tool_category,
        "action": call.action,
        "action_class": call.action_class,
        "environment": call.environment,
        "data_class": call.data_class,
        "agent_id": call.agent_id,
        "agent_class": call.agent_class,
    }

    try:
        result = subprocess.run(  # noqa: S603 — opa_binary is a controlled path, not user input
            [
                opa_binary,
                "eval",
                "--format",
                "json",
                "--data",
                rego_policy_path,
                "--input",
                json.dumps(normalized),
                "data.tooltrust.decision",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise OpaUnavailableError(f"OPA binary not found: {opa_binary!r}") from exc
    except OSError as exc:
        raise OpaUnavailableError(f"OPA subprocess error: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise OpaUnavailableError(f"OPA evaluation timed out after {timeout_seconds}s") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise OpaUnavailableError(f"OPA evaluation failed (exit {result.returncode}): {stderr}")

    return _parse_opa_output(result.stdout, call)


def _parse_opa_output(raw: str, call: NormalizedCall) -> Decision:
    """Parse the JSON stdout of ``opa eval`` into a native :class:`Decision`.

    Args:
        raw: Raw stdout from the OPA subprocess.
        call: The original normalized call (used for context, currently unused
            but reserved for future audit enrichment).

    Returns:
        A :class:`Decision` with fields mapped from the Rego output.

    Raises:
        :class:`OpaUnavailableError`: Output is unparseable or the Rego result
            contains invalid decision/criticality values.
    """
    try:
        data = json.loads(raw)
        results = data.get("result", [])
        if not results:
            raise ValueError("no OPA result")
        value = results[0].get("expressions", [{}])[0].get("value", {})
    except (json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
        raise OpaUnavailableError(f"unparseable OPA output: {exc}") from exc

    try:
        if not isinstance(value, dict):
            raise ValueError(f"OPA result must be an object, got {type(value).__name__}")
        decision_str = value.get("decision", "deny")
        return Decision(
            decision=decision_str,
            reason_code=value.get("reason_code", "deny_opa_backend_down"),
            explanation=value.get("explanation", "OPA decision (no explanation provided)"),
            criticality=value.get("criticality", "low"),
        )
    except (ValueError, TypeError, AttributeError) as exc:
        raise OpaUnavailableError(f"invalid OPA result fields: {exc}") from exc
