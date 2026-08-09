"""Tests for M1.7 — Decision, NormalizedCall, Factor, RiskScore dataclasses.

Issue #18 — types.py. Frozen, JSON-serializable, field validation on construction.
"""

import json
from dataclasses import FrozenInstanceError, asdict, is_dataclass

import pytest

from agent_tooltrust.types import Decision, Factor, NormalizedCall, RiskScore


def _factor(**overrides):
    values = {"dimension": "environment", "value": "production", "contribution": 0.8}
    values.update(overrides)
    return Factor(**values)


def _normalized(**overrides):
    values = {
        "tool": "query_logs",
        "tool_category": "search",
        "action": "read",
        "action_class": "read",
        "environment": "staging",
        "data_class": "internal",
        "agent_id": "release-bot",
        "agent_class": "ci-bot",
    }
    values.update(overrides)
    return NormalizedCall(**values)


def _risk(**overrides):
    values = {
        "dimensions": {"environment": 0.7, "action_class": 0.0},
        "aggregate": 0.44,
        "band": "medium",
    }
    values.update(overrides)
    return RiskScore(**values)


def _decision(**overrides):
    values = {
        "decision": "escalate",
        "criticality": "high",
        "reason_code": "escalate_high_risk",
        "explanation": "Write action in production on internal data requires approval.",
        "factors": [_factor()],
        "escalation_id": None,
        "policy_version": "1.0.0",
    }
    values.update(overrides)
    return Decision(**values)


class TestFactor:
    def test_is_dataclass(self):
        assert is_dataclass(Factor)

    def test_frozen(self):
        f = _factor()
        with pytest.raises(FrozenInstanceError):
            f.contribution = 0.1  # type: ignore[misc]

    def test_rejects_contribution_out_of_range(self):
        with pytest.raises(ValueError):
            _factor(contribution=1.5)
        with pytest.raises(ValueError):
            _factor(contribution=-0.1)

    def test_rejects_blank_dimension(self):
        with pytest.raises(ValueError):
            _factor(dimension="", value="production", contribution=0.5)

    def test_json_serializable(self):
        assert json.loads(json.dumps(asdict(_factor()))) == asdict(_factor())


class TestNormalizedCall:
    def test_is_dataclass(self):
        assert is_dataclass(NormalizedCall)

    def test_frozen(self):
        n = _normalized()
        with pytest.raises(FrozenInstanceError):
            n.tool = "other"  # type: ignore[misc]

    def test_optional_fields_default_none(self):
        n = _normalized()
        assert n.session_id is None
        assert n.arguments is None
        assert n.context is None

    def test_optional_fields_accept_values(self):
        n = _normalized(session_id="sess_1", arguments={"force": False}, context={"goal": "deploy"})
        assert n.session_id == "sess_1"
        assert n.arguments == {"force": False}
        assert n.context == {"goal": "deploy"}

    def test_rejects_blank_tool(self):
        with pytest.raises(ValueError):
            _normalized(tool="   ")

    def test_rejects_unknown_action_class(self):
        with pytest.raises(ValueError):
            _normalized(action_class="deploy")

    def test_rejects_blank_environment(self):
        with pytest.raises(ValueError):
            _normalized(environment="")

    def test_json_serializable(self):
        n = _normalized(arguments={"force": True})
        assert json.loads(json.dumps(asdict(n)))["tool"] == "query_logs"


class TestRiskScore:
    def test_is_dataclass(self):
        assert is_dataclass(RiskScore)

    def test_frozen(self):
        r = _risk()
        with pytest.raises(FrozenInstanceError):
            r.aggregate = 0.9  # type: ignore[misc]

    def test_rejects_aggregate_out_of_range(self):
        with pytest.raises(ValueError):
            _risk(aggregate=1.1)
        with pytest.raises(ValueError):
            _risk(aggregate=-0.5)

    def test_rejects_unknown_band(self):
        with pytest.raises(ValueError):
            _risk(band="severe")

    def test_accepts_all_four_bands(self):
        for band in ("low", "medium", "high", "critical"):
            assert _risk(band=band).band == band

    def test_dimension_value_clamped_or_rejected(self):
        with pytest.raises(ValueError):
            _risk(dimensions={"environment": 2.0})

    def test_json_serializable(self):
        assert json.loads(json.dumps(asdict(_risk())))["aggregate"] == 0.44


class TestDecision:
    def test_is_dataclass(self):
        assert is_dataclass(Decision)

    def test_frozen(self):
        d = _decision()
        with pytest.raises(FrozenInstanceError):
            d.explanation = "changed"  # type: ignore[misc]

    def test_dry_run_defaults_false(self):
        assert _decision().dry_run is False

    def test_dry_run_can_be_true(self):
        assert _decision(dry_run=True).dry_run is True

    def test_rejects_unknown_decision_value(self):
        with pytest.raises(ValueError):
            _decision(decision="maybe")

    def test_rejects_unknown_criticality(self):
        with pytest.raises(ValueError):
            _decision(criticality="extreme")

    def test_rejects_blank_reason_code(self):
        with pytest.raises(ValueError):
            _decision(reason_code="")

    def test_json_serializable_roundtrip(self):
        d = _decision()
        raw = json.dumps(asdict(d))
        assert json.loads(raw)["decision"] == "escalate"
        assert isinstance(json.loads(raw)["factors"], list)

    def test_as_dict_shape(self):
        d = _decision()
        dct = asdict(d)
        assert set(dct) == {
            "decision",
            "criticality",
            "reason_code",
            "explanation",
            "factors",
            "escalation_id",
            "policy_version",
            "dry_run",
        }

    def test_decision_to_dict_matches_asdict(self):
        d = _decision()
        assert d.to_dict() == asdict(d)

    def test_normalized_call_to_dict_matches_asdict(self):
        c = _normalized()
        assert c.to_dict() == asdict(c)

    def test_risk_score_to_dict_matches_asdict(self):
        rs = RiskScore(
            dimensions={"environment": 0.8, "action": 0.0},
            aggregate=0.4,
            band="medium",
        )
        assert rs.to_dict() == asdict(rs)

    def test_factor_to_dict_matches_asdict(self):
        f = _factor()
        assert f.to_dict() == asdict(f)
