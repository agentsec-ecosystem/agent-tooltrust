"""M1.5 — the explanation engine.

Turns a verdict + risk score + normalized call into a fully populated
Decision: machine-readable reason_code, a parameterized human explanation,
per-dimension factor breakdown, and a criticality mapping. This is the stage
that makes every decision *explainable* — the reason_code feeds SIEM and
compliance alerting, and the factor list is what a human reviewer reads.
"""

import secrets
from typing import cast

from agent_tooltrust.engine.decide import Verdict
from agent_tooltrust.policy.models import Policy
from agent_tooltrust.types import Criticality, Decision, Factor, NormalizedCall, RiskScore

#: decision → criticality. The canonical severity ladder that SIEM dashboards
#: and the audit store expect (see architecture §3.4).
CRITICALITY_BY_DECISION = {
    "deny": "critical",
    "escalate": "high",
    "audit": "medium",
    "allow": "low",
    "allow_with_obligation": "low",
}

#: Risk added to a session when an accepted (non-deny) call with ``critical``
#: severity completes. Mirrored by the live ``SessionStore`` and the audit
#: replay module (M5 #81) so a replayed session accrues risk identically to
#: live use. Single source of truth for per-call risk accumulation.
RISK_CRITICAL_FALLOFF = 1.0
#: Risk added for any other accepted call.
RISK_DEFAULT_FALLOFF = 0.25


def session_risk_increment(criticality: str) -> float:
    """The risk added to a session when an accepted (non-deny) call completes.

    Denied calls never add risk; the caller decides whether a call is denied
    and skips this. ``critical`` costs more than anything else.

    Args:
        criticality: The decision's severity literal (see ``types.Criticality``).

    Returns:
        ``RISK_CRITICAL_FALLOFF`` for ``critical``, else ``RISK_DEFAULT_FALLOFF``.
    """
    return RISK_CRITICAL_FALLOFF if criticality == "critical" else RISK_DEFAULT_FALLOFF

#: Human-readable explanation templates, keyed by reason_code. The exact
#: wording is a product decision (approved in demo-scenario.md); only the
#: ``{placeholders}`` vary per call.
TEMPLATES = {
    "allow_low_risk": (
        "{tool} ({action}) in {environment} on {data_class} data is within "
        "the allow band. Proceeding."
    ),
    "audit_sensitive_data": (
        "{tool} ({action}) in {environment} on {data_class} data is logged "
        "for review. Proceeding with enhanced audit."
    ),
    "escalate_prod_write": (
        "Write action ({action}) in production on {data_class} data requires "
        "approval. Route to the on-call approver."
    ),
    "escalate_high_risk": (
        "{tool} ({action}) in {environment} on {data_class} data crossed the "
        "approval threshold and requires approval."
    ),
    "deny_critical_op": (
        "{tool} ({action}) in {environment} on {data_class} data is blocked: "
        "destructive operation on sensitive data with irreversible side "
        "effects. Use a read-only alternative or move to a lower-risk "
        "environment."
    ),
    "allow_with_obligation": (
        "{tool} ({action}) in {environment} on {data_class} data is allowed, "
        "with mandatory obligations enforced by the gatekeeper."
    ),
}


def _reason_code_for(verdict: Verdict, call: NormalizedCall) -> str:
    """Pick the canonical reason_code for a verdict.

    The environment comparison is exact (case-sensitive by design): an
    uppercase ``Production`` call never scores as a known production write,
    so it can never be mislabeled ``escalate_prod_write`` and sneak past the
    alerting that greps on that code.
    """
    if verdict.decision == "deny":
        return "deny_critical_op"
    if verdict.decision == "audit":
        return "audit_sensitive_data"
    if verdict.decision == "escalate":
        if call.environment == "production":
            return "escalate_prod_write"
        return "escalate_high_risk"
    if verdict.decision == "allow_with_obligation":
        return "allow_with_obligation"
    return "allow_low_risk"


def _factor_labels(call: NormalizedCall, policy: Policy) -> dict[str, str]:
    """Map each scored dimension to a human-readable value.

    The scorer works in numeric risk values; the explanation layer must show
    the *label* a human recognizes — the tool's domain, the action class, the
    environment name, the data class, and the resolved agent class.
    """
    return {
        "tool_category": call.tool_category,
        "action_class": call.action_class,
        "environment": call.environment,
        "data_sensitivity": call.data_class,
        "agent_class": policy.agent_profile(call.agent_id).agent_class,
    }


def _build_factors(risk_score: RiskScore, call: NormalizedCall, policy: Policy) -> list[Factor]:
    """Project each dimension into a Factor with its weighted contribution.

    Contribution = dimension value (weighted by its configured policy weight;
    a dimension with zero weight still appears, but contributes 0.0). Factors
    are sorted descending so the top risk driver is always first in the audit
    trail.
    """
    weights = policy.risk_weights
    labels = _factor_labels(call, policy)
    factors = [
        Factor(
            dimension=dim,
            value=labels.get(dim, str(dim)),
            contribution=round(value * weights.get(dim, 1.0), 6),
        )
        for dim, value in risk_score.dimensions.items()
    ]
    factors.sort(key=lambda f: f.contribution, reverse=True)
    return factors


def _render(template: str, verdict: Verdict, call: NormalizedCall) -> str:
    """Fill a template with the call's context and quote the matched rule."""
    explanation = template.format(
        tool=call.tool,
        action=call.action,
        environment=call.environment,
        data_class=call.data_class,
    )
    if verdict.source == "rule" and verdict.reason:
        explanation += f" Policy rule: {verdict.reason}"
    return explanation


def explain(
    verdict: Verdict,
    risk_score: RiskScore,
    call: NormalizedCall,
    policy: Policy,
) -> Decision:
    """Assemble the full, auditable Decision from a verdict and its context."""
    reason_code = _reason_code_for(verdict, call)
    explanation = _render(TEMPLATES[reason_code], verdict, call)
    criticality = cast(Criticality, CRITICALITY_BY_DECISION[verdict.decision])
    escalation_id = None
    if verdict.decision == "escalate":
        # Random 32-bit fingerprint, unique per escalation. The approval
        # workflow keys on this id, so it must never repeat.
        escalation_id = "esc_" + secrets.token_hex(4)
    return Decision(
        decision=verdict.decision,
        criticality=criticality,
        reason_code=reason_code,
        explanation=explanation,
        factors=_build_factors(risk_score, call, policy),
        escalation_id=escalation_id,
        dry_run=False,
        policy_version=policy.version,
        obligations=verdict.obligations,
    )
