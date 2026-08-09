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
        assert doc.risk_weights != {}

    def test_rules_use_default_constraints(self):
        doc = parse_tooltrust_yaml('version: "0.1.0"\nrules:\n  - decision: allow\n')
        rule = doc.rules[0]
        assert rule.tool == "*"
        assert rule.action == "*"
        assert rule.environment == "*"
        assert rule.data_class == "*"
        assert rule.reason == ""


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
