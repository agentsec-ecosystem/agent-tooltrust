"""Stage 2 of the pipeline: score a normalized call across 5 risk dimensions.

Each dimension is normalized to [0, 1]:

- ``tool_category`` — baseline risk of the tool's domain (from the taxonomy)
- ``action_class`` — read/write/delete/grant risk
- ``environment`` — the org's environment criticality map
- ``data_sensitivity`` — the org's data class sensitivity map
- ``agent_class`` — the agent's trust/role risk

The aggregate is the weighted mean of the five dimensions, normalized so the
result always lands in [0, 1]. Unknown environments and data classes score at
the maximum (1.0) — fail-closed for undeclared configuration.
"""

from __future__ import annotations

from agent_tooltrust.policy.models import Policy
from agent_tooltrust.taxonomy import ACTION_VALUES, DOMAIN_BASELINE
from agent_tooltrust.types import NormalizedCall, RiskBand, RiskScore


def _band_for(aggregate: float) -> RiskBand:
    """Map the aggregate [0,1] score to a risk band.

    Boundaries are frozen (architecture §3.3): <0.25 low, <0.50 medium,
    <0.75 high, >=0.75 critical. These thresholds are NOT configurable per
    policy — keeping them constant makes decisions deterministic and
    auditable across orgs; policy tuning happens via the dimension weights
    and risk maps, not by moving the band lines.
    """
    if aggregate >= 0.75:
        return "critical"
    if aggregate >= 0.5:
        return "high"
    if aggregate >= 0.25:
        return "medium"
    return "low"


def score(call: NormalizedCall, policy: Policy) -> RiskScore:
    """Compute the 5-dimension risk score for a normalized call."""
    values = {
        # Per-dimension values are all normalized to [0, 1]:
        "tool_category": DOMAIN_BASELINE[call.tool_category],  # taxonomy baseline
        "action_class": ACTION_VALUES[call.action_class],  # read/write/delete/grant
        # Unknown environments and data classes fail closed at max risk (1.0)
        # instead of being treated as sandboxed/unknown-safe.
        "environment": policy.environments.get(call.environment, Policy.UNKNOWN_ENVIRONMENT_RISK),
        "data_sensitivity": policy.data_classes.get(
            call.data_class, Policy.UNKNOWN_DATA_CLASS_RISK
        ),
        "agent_class": policy.agent_profile(call.agent_id).risk,
    }

    # Weighted arithmetic mean. A dimension absent from risk_weights defaults
    # to weight 1.0 so an org that declares only some weights still gets a
    # sensible full-average, not an inflated one.
    weights = policy.risk_weights
    weights_total = sum(weights.get(dim, 1.0) for dim in values)
    if weights_total <= 0:
        # Guard against a pathological all-zero weight map (would be a
        # division-by-zero). Defaulting to 1.0 yields a 0.0 aggregate — the
        # caller sees a low-risk score, but zero total weight is a policy
        # authoring error the validator should reject in M2.
        weights_total = 1.0

    aggregate = sum(weights.get(dim, 1.0) * value for dim, value in values.items()) / weights_total
    # Defensive clamp: floating point and misconfiguration can stray a hair
    # outside [0,1]; the band logic below assumes in-range input.
    normalized = max(0.0, min(1.0, aggregate))

    return RiskScore(
        dimensions=values,
        aggregate=normalized,
        band=_band_for(normalized),
    )
