"""Stage 3 of the pipeline: decide the outcome for a normalized call.

Resolution order (highest priority first):

1. explicit deny rule
2. explicit allow rule
3. explicit escalate rule
4. risk-band mapping
5. default deny (fail-closed safety net)

The outcome is a lightweight :class:`Verdict` carrying the decision, where it
came from (a rule or the band), and the rule's human reason when applicable.
Explanation and audit stages embellish this into a full ``Decision``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from agent_tooltrust.engine.score import score
from agent_tooltrust.policy.models import Policy
from agent_tooltrust.types import DecisionValue, NormalizedCall, RiskScore

#: Risk band → decision (see architecture §3.3). Bands come out of the
#: scorer; ``low``/``medium``/``high``/``critical`` thresholds are frozen at
#: 0.25 / 0.50 / 0.75 so the mapping stays deterministic across installs.
_BAND_DECISIONS: dict[str, DecisionValue] = {
    "low": "allow",
    "medium": "audit",
    "high": "escalate",
    "critical": "deny",
}


@dataclass(frozen=True)
class Verdict:
    """A preliminary outcome before explanation/audit is applied.

    ``source`` is ``"rule"`` when an explicit policy rule produced the outcome
    or ``"band"`` when it came from the risk-band mapping. ``reason`` carries
    the matched rule's human text (only populated for ``"rule"`` verdicts) so
    the explanation stage can quote it.
    """

    decision: DecisionValue
    source: str
    reason: str = ""
    obligations: tuple[str, ...] = ()


def decide_from_score(risk_score: RiskScore, call: NormalizedCall, policy: Policy) -> Verdict:
    """Resolve a final decision from a risk score + policy rules.

    Resolution order (highest priority wins, per the architecture):
    explicit deny > explicit allow > explicit escalate > band mapping >
    default-deny fallback. Any policy rule that does not appear in this
    cascade is ignored: in particular an explicit ``audit`` rule is not a
    decision by itself — ``audit`` is only produced by the band mapping on a
    ``medium`` score. If M2 needs explicit audit rules, the ``wanted`` tuple
    below is the single place to extend.
    """
    for wanted in ("deny", "allow", "escalate"):
        for rule in policy.rules:
            if rule.decision == wanted and rule.matches(call):
                obligations = rule.obligations
                if wanted == "allow" and obligations:
                    return Verdict(
                        "allow_with_obligation",
                        "rule",
                        rule.reason,
                        obligations,
                    )
                return Verdict(cast(DecisionValue, rule.decision), "rule", rule.reason)

    # Band mapping covers every valid band; the ``"deny"`` default here is a
    # defensive net in case a future caller synthesizes an unknown band.
    band_decision = _BAND_DECISIONS.get(risk_score.band, "deny")
    return Verdict(band_decision, "band")


def decide(call: NormalizedCall, policy: Policy) -> Verdict:
    """Score the call, then resolve the final verdict (M1 convenience)."""
    return decide_from_score(score(call, policy), call, policy)
