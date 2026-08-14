"""Reason codes and exceptions for the ToolTrust decision pipeline.

Every failure path maps to a distinct, machine-readable ``reason_code`` so
that SIEM dashboards and compliance reviews can alert on attack classes
individually. The canonical list ships in ``docs/reference/api.md``.
"""

from __future__ import annotations

#: Decision: allow. Risk below threshold.
ALLOW_LOW_RISK = "allow_low_risk"
#: Decision: audit. Sensitive data read.
AUDIT_SENSITIVE_DATA = "audit_sensitive_data"
#: Decision: escalate. Write in production.
ESCALATE_PROD_WRITE = "escalate_prod_write"
#: Decision: escalate. Aggregate risk crossed threshold.
ESCALATE_HIGH_RISK = "escalate_high_risk"
#: Decision: deny. Destructive operation matched a critical rule.
DENY_CRITICAL_OP = "deny_critical_op"
#: Decision: deny. Tool not in the taxonomy.
DENY_UNKNOWN_TOOL = "deny_unknown_tool"
#: Decision: deny. Input failed normalization.
DENY_MALFORMED_INPUT = "deny_malformed_input"
#: Decision: deny. Engine process crashed.
DENY_ENGINE_UNAVAILABLE = "deny_engine_unavailable"
#: Decision: deny. OPA backend unreachable.
DENY_OPA_BACKEND_DOWN = "deny_opa_backend_down"
#: Decision: deny. Policy file is malformed.
DENY_POLICY_PARSE_ERROR = "deny_policy_parse_error"
#: Decision: deny. Evaluation exceeded the time budget.
DENY_EVALUATION_TIMEOUT = "deny_evaluation_timeout"
#: Decision: deny. A permitted tool was called with unsafe arguments.
DENY_ARGUMENT_POLICY = "deny_argument_policy"
#: Decision: allow with obligation. Call allowed but obligations fire.
ALLOW_WITH_OBLIGATION = "allow_with_obligation"
#: Decision: deny. An obligation runner failed; fail-closed.
DENY_OBLIGATION_FAILED = "deny_obligation_failed"
#: Decision: deny. Call resolved outside the session/identity scope (default-deny).
DENY_OUT_OF_SCOPE = "deny_out_of_scope"
#: Decision: allow. Child-agent delegation registered (scope subset of parent).
ALLOW_DELEGATION = "allow_delegation"
#: Decision: deny. Child-agent delegation references an unknown parent identity.
DENY_DELEGATION_UNKNOWN_PARENT = "deny_delegation_unknown_parent"
#: Decision: deny. Child scope would exceed the parent's scope (confused-deputy).
DENY_DELEGATION_EXCEEDS_SCOPE = "deny_delegation_exceeds_scope"


class ToolTrustError(Exception):
    """Base class for all ToolTrust failures.

    Subclasses carry a ``reason_code`` so the fail-closed handler can emit a
    deny decision with the correct machine-readable cause.
    """

    reason_code: str = DENY_ENGINE_UNAVAILABLE


class UnknownToolError(ToolTrustError):
    """A tool name does not resolve to any domain in the taxonomy."""

    reason_code = DENY_UNKNOWN_TOOL


class MalformedInputError(ToolTrustError):
    """Input failed normalization (blank fields, invalid types)."""

    reason_code = DENY_MALFORMED_INPUT


class PolicyParseError(ToolTrustError):
    """The policy file could not be parsed or validated."""

    reason_code = DENY_POLICY_PARSE_ERROR


class OpaUnavailableError(ToolTrustError):
    """The OPA backend is unreachable or returned an error."""

    reason_code = DENY_OPA_BACKEND_DOWN


class EvaluationTimeoutError(ToolTrustError):
    """Evaluation exceeded its time budget."""

    reason_code = DENY_EVALUATION_TIMEOUT
