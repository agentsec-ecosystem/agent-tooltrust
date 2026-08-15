"""Tests for M1 #142 — argument-level policy (Stage 1b, DD-15).

A per-tool ``args_policy`` constrains a call's arguments before scoring:
required fields, forbidden patterns, numeric bounds, and allowed values. A
violation is a deterministic deny with reason code ``deny_argument_policy`` and
the
offending field named in the explanation. Non-required missing args and
unknown args pass through — the schema is a constraint, not an allowlist.
"""

from __future__ import annotations

from typing import Any

from agent_tooltrust.engine.argument_policy import ArgumentSpec, check_arguments
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import Policy, default_policy
from agent_tooltrust.types import Decision


def _policy(args_policy: dict[str, Any]) -> Policy:
    base = default_policy("balanced")
    return Policy(
        version=base.version,
        posture=base.posture,
        environments=base.environments,
        data_classes=base.data_classes,
        risk_weights=base.risk_weights,
        rules=base.rules,
        agents=base.agents,
        args_policy=args_policy,
    )


DELETE_ARGS = {
    "delete_instance": {
        "filter": ArgumentSpec(required=True, forbid=("*", "1=1", "")),
        "row_limit": ArgumentSpec(max=1000.0),
        "target_env": ArgumentSpec(allowed=("staging", "prod")),
    }
}


class TestCheckArguments:
    def test_required_arg_missing_denied(self) -> None:
        field = check_arguments("delete_instance", {}, DELETE_ARGS)
        assert field == "filter"

    def test_forbidden_value_denied(self) -> None:
        assert check_arguments("delete_instance", {"filter": "*"}, DELETE_ARGS) == "filter"
        assert check_arguments("delete_instance", {"filter": "1=1"}, DELETE_ARGS) == "filter"
        assert check_arguments("delete_instance", {"filter": ""}, DELETE_ARGS) == "filter"

    def test_forbid_is_substring_match(self) -> None:
        assert check_arguments(
            "delete_instance", {"filter": "SELECT * FROM x"}, DELETE_ARGS
        ) == "filter"

    def test_beyond_max_denied(self) -> None:
        assert check_arguments(
            "delete_instance", {"filter": "id=1", "row_limit": 5000}, DELETE_ARGS
        ) == "row_limit"

    def test_at_max_allowed(self) -> None:
        assert (
            check_arguments(
                "delete_instance", {"filter": "id=1", "row_limit": 1000}, DELETE_ARGS
            )
            is None
        )

    def test_value_not_in_allowed_denied(self) -> None:
        assert check_arguments(
            "delete_instance", {"filter": "id=1", "target_env": "production"}, DELETE_ARGS
        ) == "target_env"

    def test_value_in_allowed_passes(self) -> None:
        assert (
            check_arguments(
                "delete_instance", {"filter": "id=1", "target_env": "prod"}, DELETE_ARGS
            )
            is None
        )

    def test_no_schema_for_tool_passes(self) -> None:
        assert check_arguments("other_tool", {"anything": 1}, DELETE_ARGS) is None

    def test_unknown_arg_passes_through(self) -> None:
        assert (
            check_arguments(
                "delete_instance", {"filter": "id=1", "unlisted": "x"}, DELETE_ARGS
            )
            is None
        )

    def test_non_required_missing_arg_passes(self) -> None:
        assert (
            check_arguments("delete_instance", {"filter": "id=1"}, DELETE_ARGS) is None
        )

    def test_empty_arguments_and_no_policy_passes(self) -> None:
        assert check_arguments("delete_instance", None, {}) is None
        assert check_arguments("delete_instance", {}, {}) is None


class TestEngineStage1b:
    def _engine(self) -> Engine:
        return Engine(_policy(DELETE_ARGS))

    def test_empty_filter_delete_denied_with_reason(self) -> None:
        decision = self._engine().evaluate(
            tool_name="delete_instance",
            action="delete",
            environment="production",
            data_class="internal",
            agent_id="release-bot",
            arguments={"filter": ""},
        )
        assert decision.decision == "deny"
        assert decision.reason_code == "deny_argument_policy"
        assert "filter" in decision.explanation

    def test_unbounded_row_limit_denied(self) -> None:
        decision = self._engine().evaluate(
            tool_name="delete_instance",
            action="delete",
            environment="production",
            data_class="internal",
            agent_id="release-bot",
            arguments={"filter": "id=1", "row_limit": 5000},
        )
        assert decision.decision == "deny"
        assert decision.reason_code == "deny_argument_policy"

    def test_safe_delete_still_policy_evaluated(self) -> None:
        decision = self._engine().evaluate(
            tool_name="delete_instance",
            action="delete",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
            arguments={"filter": "id=1", "row_limit": 10},
        )
        # Not an argument violation; the normal band applies.
        assert decision.reason_code != "deny_argument_policy"

    def test_call_without_arguments_passes_stage_1b(self) -> None:
        decision = self._engine().evaluate(
            tool_name="query_logs",
            action="read",
            environment="development",
            data_class="public",
            agent_id="release-bot",
        )
        assert decision.reason_code != "argument_policy"

    def test_deny_is_a_decision_not_exception(self) -> None:
        decision = self._engine().evaluate(
            tool_name="delete_instance",
            action="delete",
            environment="production",
            data_class="internal",
            agent_id="release-bot",
            arguments={"filter": "1=1"},
        )
        assert isinstance(decision, Decision)
