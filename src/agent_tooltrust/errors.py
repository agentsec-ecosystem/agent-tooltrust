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
#: Decision: deny. Dispatcher could not parse the raw command into a canonical call.
DENY_UNPARSEABLE_INPUT = "deny_unparseable_input"
#: Decision: escalate. Approval requested; bound to an action_identity + TTL.
ESCALATE_APPROVAL = "escalate_approval"
#: Decision: allow. Escalation was approved and is within its action identity + TTL.
ALLOW_ESCALATION_APPROVED = "allow_escalation_approved"
#: Decision: deny. Escalation was denied by a human.
DENY_ESCALATION_DENIED = "deny_escalation_denied"
#: Decision: deny. Escalation approval expired (TTL elapsed).
DENY_ESCALATION_EXPIRED = "deny_escalation_expired"
#: Decision: deny. Escalation id is unknown / already resolved.
DENY_ESCALATION_UNKNOWN = "deny_escalation_unknown"
#: Decision: deny. Approval reused for a call with a different action identity.
DENY_ACTION_IDENTITY_MISMATCH = "deny_action_identity_mismatch"
#: Decision: deny. Same escalation id reused for a different call (replay).
DENY_ESCALATION_REPLAY = "deny_escalation_replay"
#: Decision: deny. Session tripped the deny-storm detector (probe/fatigue).
DENY_DENY_STORM = "deny_deny_storm"
#: Decision: deny. URL fetch used a disallowed scheme or had no host.
DENY_URL_SCHEME = "deny_url_scheme"
#: Decision: deny. URL fetch blocked by the site's robots.txt.
DENY_URL_BLOCKED_BY_ROBOTS = "deny_url_blocked_by_robots"
#: Decision: deny. URL fetch resolved (or redirected) to an internal address.
DENY_URL_INTERNAL_ADDRESS = "deny_url_internal_address"
#: Decision: deny. URL fetch host could not be resolved.
DENY_URL_INVALID = "deny_url_invalid"
#: Decision: allow. Agent self-report matched the external verification sink.
ALLOW_VERIFIED = "allow_verified"
#: Decision: deny. Agent self-report contradicted external ground truth.
DENY_VERIFICATION_CONTRADICTED = "deny_verification_contradicted"


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
