"""M1.8 — the engine facade.

Issue #19. ``Engine`` runs the whole decision pipeline: normalize -> score ->
decide -> explain. Any error fails closed to a deny decision, and an optional
LLM explainer may enrich the explanation text.
"""

from dataclasses import replace
from typing import Any

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.decide import decide
from agent_tooltrust.engine.explain import explain
from agent_tooltrust.engine.fail_closed import fail_closed
from agent_tooltrust.engine.llm_explain import Explainer, template_explainer
from agent_tooltrust.engine.normalize import normalize
from agent_tooltrust.engine.score import score
from agent_tooltrust.policy.models import Policy
from agent_tooltrust.types import Decision


class Engine:
    """The only entry point callers need. Safe by default: every failure is a
    deny Decision, never an exception and never an allow.

    ``evaluate`` wires the stages together: it resolves the caller's agent
    class from the policy, normalizes the raw call, scores it, decides, and
    explains the result. The optional ``explainer`` (default: no-op template
    explainer) may enrich the explanation; it is called with the assembled
    Decision so it can reference the final reason_code/factors.
    """

    def __init__(
        self,
        policy: Policy,
        explainer: Explainer = template_explainer,
        dry_run: bool = False,
        audit_logger: AuditLogger | None = None,
    ):
        #: The declarative policy in force for every evaluation. Immutable for
        #: the Engine's lifetime; swap engines to change policy.
        self._policy = policy
        self._explainer = explainer
        #: When *dry_run* is ``True``, every :meth:`evaluate` returns an
        #: ``allow`` Decision but logs the *real* (un-overridden) decision in
        #: the audit record so operators can see what would have happened
        #: without risk of accidentally blocking a call.
        self._dry_run = dry_run
        #: Optional audit destination. When set, every decision (allow and
        #: deny alike) is recorded after stage 5. A sink failure is reported to
        #: stderr by the logger and never changes or blocks the decision.
        self._audit_logger = audit_logger

    @fail_closed
    def evaluate(
        self,
        tool_name: str,
        action: str,
        environment: str,
        data_class: str,
        agent_id: str,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Decision:
        """Evaluate a tool call and return a complete, always-safe Decision.

        Any stage that raises a ToolTrustError (unknown tool, malformed
        input, policy failure, backend/policy outage, timeout) is converted by
        the ``fail_closed`` decorator into a deny Decision with the matching
        reason_code. Non-ToolTrust bugs still surface as exceptions — we
        never want to mask real defects with a bogus allow.
        """
        # 1. Resolve the agent's class from policy (falls back to "general").
        #    This must happen before normalize so the call carries the right
        #    agent_class into the scorer.
        profile = self._policy.agent_profile(agent_id)
        call = normalize(
            tool=tool_name,
            action=action,
            environment=environment,
            data_class=data_class,
            agent_id=agent_id,
            agent_class=profile.agent_class,
            arguments=arguments,
            context=context,
        )
        # 2-4. Score → decide → explain. Order is fixed: the verdict needs the
        #      score's band, and the Decision needs both.
        risk_score = score(call, self._policy)
        verdict = decide(call, self._policy)
        decision = explain(verdict, risk_score, call, self._policy)
        # 5. Enrich explanation (optional plugin). Always re-set the text so
        #    the explainer's output is what callers and the audit trail see.
        decision = replace(decision, explanation=self._explainer(decision, call))
        # 5b. Audit. Record the *real* (pre-dry-run) decision so the audit
        #     trail shows what would have been enforced in shadow mode. The
        #     logger swallows its own failures, so this never raises.
        if self._audit_logger is not None:
            self._audit_logger.log(decision, call, dry_run=bool(self._dry_run))
        # 6. Shadow / dry-run mode: return ``allow`` but keep the real verdict
        #    in the audit trail (callers can inspect ``decision.dry_run`` and
        #    the original decision details).
        if self._dry_run:
            decision = replace(
                decision,
                decision="allow",
                explanation=(
                    f"[DRY RUN] would have been {decision.decision}: {decision.explanation}"
                ),
                dry_run=True,
            )
        return decision
