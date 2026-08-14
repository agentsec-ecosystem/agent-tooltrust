"""Tests for M2.1 — the tooltrust.yaml Pydantic schema (#1, F-06/F-60).

The schema must accept the architecture §5.4 policy document verbatim, reject
malformed documents (bad posture, out-of-range risks, unknown keys, invalid
rule decisions), and expose the validated fields for the loader.
"""

import pytest
from pydantic import ValidationError

from agent_tooltrust.policy.schema import (
    AuditConfig,
    EscalationConfig,
    RuleSpec,
    ToolSpec,
    parse_tooltrust_yaml,
)

ARCHITECTURE_EXAMPLE = """\
version: "1.0.0"
posture: balanced

environments:
  staging: {criticality: 0.1}
  production: {criticality: 0.8}
  pre_prod: {criticality: 0.6}

data_classes:
  public: {sensitivity: 0.0}
  internal: {sensitivity: 0.3}
  restricted: {sensitivity: 0.7}
  customer_pii: {sensitivity: 1.0}

risk_weights:
  tool_category: 1.0
  action_class: 1.0
  environment: 1.0
  data_sensitivity: 1.0
  agent_class: 1.0

rules:
  - tool: "*"
    action: delete
    environment: production
    decision: deny
    reason: "Deletes in production are blocked"

  - tool: "query_logs"
    action: read
    environment: staging
    decision: allow

escalation:
  threshold: 0.5
  ttl_seconds: 300

audit:
  sink: jsonl
  path: ~/.tooltrust/audit.jsonl
  postgres_url: null
"""


class TestParsesValid:
    def test_architecture_example_parses(self):
        doc = parse_tooltrust_yaml(ARCHITECTURE_EXAMPLE)
        assert doc.version == "1.0.0"
        assert doc.posture == "balanced"
        assert doc.environments["production"].criticality == 0.8
        assert doc.data_classes["customer_pii"].sensitivity == 1.0
        assert doc.risk_weights["tool_category"] == 1.0
        assert len(doc.rules) == 2
        assert doc.rules[0].decision == "deny"
        assert doc.escalation.threshold == 0.5
        assert doc.escalation.ttl_seconds == 300
        assert doc.audit.sink == "jsonl"

    def test_default_fields_fill_in(self):
        doc = parse_tooltrust_yaml('version: "0.2.0"')
        assert doc.posture == "balanced"
        assert doc.rules == []
        assert doc.escalation == EscalationConfig()
        assert doc.audit == AuditConfig()
        # risk_weights default empty so the loader inherits the posture preset
        # instead of clobbering every dimension with 1.0.
        assert doc.risk_weights == {}

    def test_rules_use_default_constraints(self):
        doc = parse_tooltrust_yaml('version: "0.1.0"\nrules:\n  - decision: allow\n')
        rule = doc.rules[0]
        assert rule.tool == "*"
        assert rule.action == "*"
        assert rule.environment == "*"
        assert rule.data_class == "*"
        assert rule.reason == ""
        assert rule.conditions == []


class TestConditionsSchema:
    """M1 #93 — boolean condition tree in policy rules (schema form)."""

    CONDITIONS_YAML = """\
version: "2.0.0"
rules:
  - decision: deny
    conditions:
      - {field: environment, op: eq, value: production}
      - {op: not, condition: {field: data_class, value: public}}
"""

    def test_conditions_parses(self):
        doc = parse_tooltrust_yaml(self.CONDITIONS_YAML)
        assert len(doc.rules) == 1
        assert len(doc.rules[0].conditions) == 2

    def test_unknown_condition_key_rejected(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml(
                'version: "2.0.0"\nrules:\n'
                "  - decision: deny\n    conditions:\n"
                "      - {field: environment, op: eq, value: prod, bogus: 1}\n"
            )


class TestRejectsMalformed:
    def test_missing_version(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml("posture: balanced")

    def test_blank_version(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml('version: ""')

    def test_unknown_posture(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml('version: "1.0.0"\nposture: paranoid')

    def test_environment_criticality_out_of_range(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml(
                'version: "1.0.0"\nenvironments:\n  production: {criticality: 2.5}\n'
            )

    def test_negative_sensitivity(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml(
                'version: "1.0.0"\ndata_classes:\n  internal: {sensitivity: -0.5}\n'
            )

    def test_rule_with_invalid_decision(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml('version: "1.0.0"\nrules:\n  - decision: run\n')

    def test_unknown_top_level_key(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml('version: "1.0.0"\nenvironemnts: {}\n')

    def test_unknown_rule_key(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml(
                'version: "1.0.0"\nrules:\n  - decision: deny\n    environmet: production\n'
            )

    def test_risk_weight_out_of_range(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml('version: "1.0.0"\nrisk_weights:\n  tool_category: 1.4\n')

    def test_risk_weight_unknown_dimension(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml('version: "1.0.0"\nrisk_weights:\n  tool_categry: 1.0\n')

    def test_escalation_ttl_must_be_positive(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml('version: "1.0.0"\nescalation:\n  ttl_seconds: -5\n')

    def test_escalation_threshold_out_of_range(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml('version: "1.0.0"\nescalation:\n  threshold: 1.7\n')

    def test_non_mapping_document_rejected(self):
        with pytest.raises(ValueError):
            parse_tooltrust_yaml("- a\n- list\n")

    def test_unknown_audit_sink(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml('version: "1.0.0"\naudit:\n  sink: mongodb\n')


class TestRuleSpec:
    def test_accepts_all_four_decisions(self):
        for decision in ("allow", "audit", "escalate", "deny"):
            rule = RuleSpec(decision=decision)
            assert rule.decision == decision


class TestToolSpec:
    def test_hidden_for_round_trips(self):
        tool = ToolSpec(name="delete_instance", hidden_for=["readonly"])
        assert tool.name == "delete_instance"
        assert tool.hidden_for == ["readonly"]

    def test_empty_hidden_for_defaults(self):
        assert ToolSpec(name="delete_instance").hidden_for == []

    def test_unknown_keys_rejected(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml(
                'version: "1.0.0"\ntools:\n  - name: delete_instance\n    bogus: 1\n'
            )

    def test_args_policy_parses(self):
        doc = parse_tooltrust_yaml(
            'version: "1.0.0"\ntools:\n'
            "  - name: db.delete\n    args_policy:\n"
            "      filter: {required: true, forbid: [\"*\", \"1=1\"]}\n"
            "      row_limit: {max: 1000}\n"
        )
        spec = doc.tools[0].args_policy
        assert spec["filter"].required is True
        assert spec["filter"].forbid == ["*", "1=1"]
        assert spec["row_limit"].max == 1000

    def test_args_policy_unknown_key_rejected(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml(
                'version: "1.0.0"\ntools:\n'
                "  - name: db.delete\n    args_policy:\n"
                "      filter: {bogus: 1}\n"
            )

    def test_rule_obligations_parse(self):
        doc = parse_tooltrust_yaml(
            'version: "1.0.0"\nrules:\n'
            "  - decision: allow\n    action: delete\n"
            "    obligations: [first_use_signoff, auto_notify]\n"
        )
        assert doc.rules[0].obligations == ["first_use_signoff", "auto_notify"]

    def test_rule_unknown_obligation_key_rejected(self):
        with pytest.raises(ValidationError):
            parse_tooltrust_yaml(
                'version: "1.0.0"\nrules:\n'
                "  - decision: allow\n    obligaton: [first_use_signoff]\n"
            )
