"""Tests for M1 Task 1 (#93) — rule composition with and/or/not + grouping.

Extends the flat :class:`Rule` constraint model with an optional boolean
condition tree over sub-conditions, so policies can express "allow read IF
owner AND not prod" compactly without rule explosion. The flat fields
(tool/action/environment/data_class) keep working unchanged.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from agent_tooltrust.policy.models import Rule
from agent_tooltrust.types import NormalizedCall


def _call(**overrides) -> NormalizedCall:
    values = {
        "tool": "deploy_service",
        "tool_category": "cloud",
        "action": "write",
        "action_class": "write",
        "environment": "production",
        "data_class": "internal",
        "agent_id": "release-bot",
        "agent_class": "ci-bot",
    }
    values.update(overrides)
    return NormalizedCall(
        **{  # type: ignore[arg-type]
            "tool": values["tool"],
            "tool_category": values["tool_category"],
            "action": values["action"],
            "action_class": values["action_class"],
            "environment": values["environment"],
            "data_class": values["data_class"],
            "agent_id": values["agent_id"],
            "agent_class": values["agent_class"],
        }
    )


def _cond(**overrides) -> dict:
    cond = {"field": "environment", "op": "eq", "value": "production"}
    cond.update(overrides)
    return cond


class TestConditionPrimitives:
    def test_eq_field_matches(self):
        rule = Rule(decision="deny", conditions=[_cond()])
        assert rule.matches(_call(environment="production"))
        assert not rule.matches(_call(environment="staging"))

    def test_neq_field(self):
        rule = Rule(decision="deny", conditions=[_cond(op="neq", value="production")])
        assert rule.matches(_call(environment="staging"))
        assert not rule.matches(_call(environment="production"))

    def test_action_condition_matches_verb_or_class(self):
        # action conditions match against both the verb and the action class
        rule = Rule(decision="deny", conditions=[_cond(field="action", value="delete")])
        assert rule.matches(_call(action="delete", action_class="delete"))
        assert rule.matches(_call(action="drop", action_class="delete"))
        assert not rule.matches(_call(action="read", action_class="read"))

    def test_tool_condition(self):
        rule = Rule(decision="deny", conditions=[_cond(field="tool", value="deploy_service")])
        assert rule.matches(_call())
        assert not rule.matches(_call(tool="query_logs", tool_category="search"))

    def test_data_class_condition(self):
        rule = Rule(
            decision="deny", conditions=[_cond(field="data_class", value="customer_pii")]
        )
        assert rule.matches(_call(data_class="customer_pii"))
        assert not rule.matches(_call(data_class="internal"))


class TestBooleanGroups:
    def test_and_group_all_true(self):
        rule = Rule(
            decision="deny",
            conditions=[
                {"op": "and", "conditions": [_cond(), _cond(field="action", value="write")]}
            ],
        )
        assert rule.matches(_call())  # env=production AND action=write
        assert not rule.matches(_call(environment="staging"))

    def test_or_group_any_true(self):
        rule = Rule(
            decision="deny",
            conditions=[
                {"op": "or", "conditions": [_cond(), _cond(field="action", value="delete")]}
            ],
        )
        assert rule.matches(_call(environment="production", action="read", action_class="read"))
        assert rule.matches(_call(environment="staging", action="delete", action_class="delete"))
        assert not rule.matches(
            _call(environment="staging", action="read", action_class="read")
        )

    def test_not_wraps_condition(self):
        rule = Rule(decision="deny", conditions=[{"op": "not", "condition": _cond()}])
        assert rule.matches(_call(environment="staging"))
        assert not rule.matches(_call(environment="production"))

    def test_nested_groups(self):
        rule = Rule(
            decision="deny",
            conditions=[
                {
                    "op": "and",
                    "conditions": [
                        {"op": "or", "conditions": [_cond(), _cond(field="action", value="grant")]},
                        {"op": "not", "condition": _cond(field="data_class", value="public")},
                    ],
                }
            ],
        )
        # env=production (true) AND data_class!=public (true)
        assert rule.matches(_call(environment="production", data_class="internal"))
        # action=grant (true) AND data_class!=public (true)
        assert rule.matches(_call(environment="staging", action="grant", action_class="grant"))
        # env!=production AND action!=grant → or false → whole and false
        assert not rule.matches(_call(environment="staging", action="read", action_class="read"))
        # data_class=public makes the not-branch false
        assert not rule.matches(_call(environment="production", data_class="public"))


class TestConditionsInteractWithFlatFields:
    def test_flat_fields_and_conditions_are_anded(self):
        rule = Rule(
            decision="deny",
            tool="deploy_service",
            conditions=[_cond(field="data_class", value="customer_pii")],
        )
        assert rule.matches(_call(tool="deploy_service", data_class="customer_pii"))
        assert not rule.matches(_call(tool="deploy_service", data_class="internal"))
        assert not rule.matches(_call(tool="query_logs", tool_category="search"))


class TestMalformedConditions:
    def test_empty_conditions_list_matches_like_flat_rule(self):
        # An empty conditions list adds no constraint — identical to the
        # default wildcard Rule (consistent with flat-field semantics).
        rule = Rule(decision="deny", conditions=[])
        assert rule.matches(_call())
        assert rule.matches(_call(tool="anything", action="whatever"))

    def test_unknown_operator_rejected_at_construction(self):
        with pytest.raises(ValueError):
            Rule(decision="deny", conditions=[{"op": "xor"}])

    def test_unknown_field_rejected_at_construction(self):
        with pytest.raises(ValueError):
            Rule(decision="deny", conditions=[_cond(field="nonexistent")])

    def test_condition_clause_is_frozen(self):
        rule = Rule(decision="deny", conditions=[_cond()])
        cond = rule.conditions[0]
        with pytest.raises(FrozenInstanceError):
            cond.value = "staging"  # type: ignore[misc]


class TestRulesStayFrozen:
    def test_rule_still_frozen(self):
        rule = Rule(decision="deny", conditions=[_cond()])
        with pytest.raises(FrozenInstanceError):
            rule.conditions = []  # type: ignore[misc]
