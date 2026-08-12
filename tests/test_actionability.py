"""CUJ 3 — Explanation actionability tests.

For every denied or escalated decision, the explanation must identify the
blocking factor so a human (or LLM judge) can identify the ONE change that
would get the call allowed.
"""

from __future__ import annotations

import pytest

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy


class TestExplanationActionability:
    @pytest.fixture
    def engine(self) -> Engine:
        return Engine(default_policy("balanced"))

    def test_deny_identifies_action_as_blocking(self, engine: Engine) -> None:
        """A delete on customer-PII in production should point to action and data."""
        decision = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="customer_pii",
            agent_id="release-bot",
        )

        assert decision.decision == "deny"
        explanation_lower = decision.explanation.lower()
        assert any(word in explanation_lower for word in ("delete", "destructive"))
        assert any(word in explanation_lower for word in ("pii", "sensitive"))

        action_factor = next(
            (f for f in decision.factors if f.dimension == "action_class"), None
        )
        assert action_factor is not None
        assert action_factor.value == "delete"

    def test_escalate_identifies_environment_as_blocking(self, engine: Engine) -> None:
        """Write in production on restricted data should escalate pointing to prod."""
        decision = engine.evaluate(
            tool_name="deploy_service",
            action="write",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )

        assert decision.decision == "escalate"
        explanation_lower = decision.explanation.lower()
        assert "production" in explanation_lower
        assert "approval" in explanation_lower

        env_factor = next(
            (f for f in decision.factors if f.dimension == "environment"), None
        )
        assert env_factor is not None
        assert "production" in env_factor.value

    def test_allow_no_blockers(self, engine: Engine) -> None:
        """Read in staging on internal data should produce no blocking factors."""
        decision = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="debug-bot",
        )

        assert decision.decision == "allow"

    def test_reason_code_is_machine_readable(self, engine: Engine) -> None:
        """Every denied decision must carry a machine-readable reason_code."""
        decision = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="customer_pii",
            agent_id="release-bot",
        )

        assert decision.decision == "deny"
        assert decision.reason_code
        assert "_" in decision.reason_code or decision.reason_code.islower()

    def test_deny_explains_what_to_change(self, engine: Engine) -> None:
        """A denied call explanation should suggest an alternative action."""
        decision = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="customer_pii",
            agent_id="release-bot",
        )

        assert decision.decision == "deny"
        explanation_lower = decision.explanation.lower()
        assert any(word in explanation_lower for word in (
            "read-only", "alternative", "lower-risk", "staging", "instead"
        ))
