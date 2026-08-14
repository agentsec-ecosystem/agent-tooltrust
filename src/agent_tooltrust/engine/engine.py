"""M1.8 — the engine facade.

Issue #19. ``Engine`` runs the whole decision pipeline: normalize -> score ->
decide -> explain. Any error fails closed to a deny decision, and an optional
LLM explainer may enrich the explanation text.
"""

from dataclasses import replace
from typing import Any

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.argument_policy import check_arguments
from agent_tooltrust.engine.decide import decide
from agent_tooltrust.engine.delegation import DelegationManager, DelegationResult
from agent_tooltrust.engine.escalation import EscalationManager
from agent_tooltrust.engine.explain import explain
from agent_tooltrust.engine.fail_closed import deny, fail_closed
from agent_tooltrust.engine.llm_explain import Explainer, template_explainer
from agent_tooltrust.engine.normalize import normalize
from agent_tooltrust.engine.obligations import ObligationError, ObligationStore, run_obligations
from agent_tooltrust.engine.scoping import SessionScope, scoping_violation
from agent_tooltrust.engine.score import score
from agent_tooltrust.errors import (
    DENY_ARGUMENT_POLICY,
    DENY_OBLIGATION_FAILED,
    DENY_OUT_OF_SCOPE,
)
from agent_tooltrust.policy.models import Policy
from agent_tooltrust.taxonomy import KNOWN_TOOLS
from agent_tooltrust.types import Decision, NormalizedCall


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
        obligation_store: ObligationStore | None = None,
        escalation_manager: EscalationManager | None = None,
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
        #: Obligation state (sign-off cache, event journal). One store may be
        #: shared across engine instances to keep sign-offs durable per fleet.
        self._obligation_store = obligation_store or ObligationStore()
        #: Child-agent delegation registry (M2 #108, F-88). Enforces the
        #: child-scope-⊆-parent-scope invariant and keeps the parent→child
        #: chain for the audit trail.
        self._delegations = DelegationManager()
        #: Escalation approval registry (M3 #84, F-09). Tracks pending
        #: escalations and their approvals/denials, bound to the action
        #: identity, so a human approval can be enforced by the engine.
        self._escalation_manager = escalation_manager or EscalationManager()

    @property
    def obligation_store(self) -> ObligationStore:
        """The obligation store backing this engine's permit-with-obligation."""
        return self._obligation_store

    @property
    def delegation_manager(self) -> DelegationManager:
        """The delegation registry enforcing the child-scope subset invariant."""
        return self._delegations

    @property
    def escalation_manager(self) -> EscalationManager:
        """The escalation registry tracking approvals bound to action identity."""
        return self._escalation_manager

    def delegate(
        self,
        child_id: str,
        parent_id: str,
        environments: tuple[str, ...] = (),
    ) -> DelegationResult:
        """Delegate a child agent under a parent, enforcing scope-subset.

        The child's requested ``environments`` must be a subset of the
        parent's own allowed environments (confused-deputy protection, F-88).
        A successful delegation registers the child in the registry so the
        parent→child lineage is visible in the audit trail; a delegation that
        would exceed the parent's scope is denied.

        Args:
            child_id: The identity being created by this delegation.
            parent_id: The existing identity authorizing the delegation.
            environments: The child's requested allowed environments.

        Returns:
            The :class:`DelegationResult` describing allow or deny.
        """
        return self._delegations.delegate(
            child_id=child_id,
            parent_id=parent_id,
            policy=self._policy,
            environments=environments,
        )

    @property
    def policy(self) -> Policy:
        """The policy in force for this engine."""
        return self._policy

    def capabilities(self, agent_id: str) -> tuple[str, ...]:
        """Return the discovery-time capability list for an agent class.

        Implements discovery-time tool hiding (M1 #88, F-83). A tool marked
        ``hidden_for`` a class is omitted from the list that class sees, so a
        read-only agent is never even told about tools it cannot use. Hiding
        is *discovery-time only*: calling a hidden tool still goes through
        :meth:`evaluate` and is denied by policy if not permitted — hiding
        never weakens enforcement.

        The returned order is deterministic (sorted) so the capability surface
        is stable across calls.

        Args:
            agent_id: The agent identity; its class resolves visibility.

        Returns:
            The tool names visible to the agent's class, sorted.
        """
        agent_class = self._policy.agent_profile(agent_id).agent_class
        hidden: set[str] = {
            tool
            for tool, rules in self._policy.tool_visibility.items()
            if agent_class in rules.get("hidden_for", ())
        }
        return tuple(sorted(tool for tool in KNOWN_TOOLS if tool not in hidden))

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
        session_scope: SessionScope | None = None,
        resource_tag: str | None = None,
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
            resource_tag=resource_tag,
        )
        # 1a. Resource/environment scoping (M2 #145, DD-18). Default-deny: an
        #     identity or session scope restricts which environments/resources
        #     a call may touch. Identity scope comes from the policy profile;
        #     the session scope is supplied by the caller. A violation is an
        #     immediate, audited deny before scoring.
        scope_violation = scoping_violation(call, session_scope)
        if scope_violation is None and profile.environments:
            if call.environment not in profile.environments:
                scope_violation = (
                    f"identity {agent_id!r} is not scoped to environment "
                    f"{call.environment!r} (allowed: {profile.environments!r})"
                )
        if scope_violation is not None:
            decision = deny(
                DENY_OUT_OF_SCOPE,
                scope_violation,
                policy_version=self._policy.version,
            )
            return self._finalize(decision, call)
        # 1b. Argument-level policy (M1 #142, DD-15). Pure, deterministic check
        #     of the call's arguments against the tool's args_policy. A
        #     violation is an immediate, audited deny before any scoring.
        violating = check_arguments(call.tool, call.arguments, self._policy.args_policy)
        if violating is not None:
            decision = deny(
                DENY_ARGUMENT_POLICY,
                f"argument {violating!r} violates policy for tool {call.tool!r}",
                policy_version=self._policy.version,
            )
            return self._finalize(decision, call)
        # 2-4. Score → decide → explain. Order is fixed: the verdict needs the
        #      score's band, and the Decision needs both.
        risk_score = score(call, self._policy)
        verdict = decide(call, self._policy)
        decision = explain(verdict, risk_score, call, self._policy)
        # 3b. Escalation registry (M3 #84, F-09). When the verdict escalates,
        #     create a pending approval record bound to the call's action
        #     identity, and pin the decision's escalation_id to the registered
        #     record so the approval workflow keys on a known, tracked id.
        if decision.decision == "escalate" or verdict.decision == "escalate":
            escalation = self._escalation_manager.create(call, reason=decision.explanation)
            decision = replace(decision, escalation_id=escalation.escalation_id)
        # 4b. Permit-with-obligation (M1 #147, DD-20). When the verdict carries
        #     obligations, the gatekeeper executes them — not the agent — and
        #     a runner failure is fail-closed (deny, never allow-without-
        #     obligation). The summary is folded into the explanation so the
        #     audit trail records the obligations and their completion.
        if verdict.obligations:
            try:
                summary = run_obligations(
                    verdict.obligations,
                    store=self._obligation_store,
                    agent_id=call.agent_id,
                    tool=call.tool,
                )
            except ObligationError as exc:
                decision = deny(
                    DENY_OBLIGATION_FAILED,
                    f"obligation failed: {exc}",
                    policy_version=self._policy.version,
                )
                return self._finalize(decision, call)
            decision = replace(
                decision,
                obligations=verdict.obligations,
                explanation=f"OBLIGATIONS [{summary}]: {decision.explanation}",
            )
        # 5. Enrich explanation (optional plugin). Always re-set the text so
        #    the explainer's output is what callers and the audit trail see.
        decision = replace(decision, explanation=self._explainer(decision, call))
        return self._finalize(decision, call)

    def _finalize(self, decision: Decision, call: NormalizedCall) -> Decision:
        """Apply the audit log and shadow-mode override to a finished Decision.

        Every decision — allow, deny, and the early-return denies from
        argument-policy (1b) and obligation-failure (4b) paths — flows through
        here so the audit trail records a *real*, un-overridden decision and
        dry-run mode always returns an ``allow`` without blocking anything.

        Args:
            decision: The finished decision (pre audit/dry-run).
            call: The normalized call, for the audit record.

        Returns:
            The audited decision, with the dry-run override applied when
            shadow mode is active.
        """
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
