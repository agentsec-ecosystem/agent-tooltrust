"""Tests for score calibration: counterfactual thresholds, false rates, and reporting."""

from __future__ import annotations

from agent_tooltrust.engine.score import counterfactual_threshold


class TestCounterfactualThreshold:
    def test_low_band_boundary(self) -> None:
        assert counterfactual_threshold(0.2, "low") == 0.25

    def test_medium_band_boundary(self) -> None:
        assert counterfactual_threshold(0.3, "medium") == 0.5

    def test_high_band_downward(self) -> None:
        assert counterfactual_threshold(0.6, "high") == 0.5

    def test_critical_band_downward(self) -> None:
        assert counterfactual_threshold(0.9, "critical") == 0.75


class TestDecisionCounterfactual:
    def test_decision_has_counterfactual_field(self) -> None:
        from agent_tooltrust.engine.engine import Engine
        from agent_tooltrust.policy.models import default_policy

        engine = Engine(default_policy("balanced"))
        decision = engine.evaluate(
            "query_logs", "read", "staging", "internal", "debug-bot",
        )
        assert hasattr(decision, "counterfactual")
        d = decision.to_dict()
        assert "counterfactual" in d

    def test_counterfactual_stored_in_audit_entry(self) -> None:
        from agent_tooltrust.audit.logger import AuditLogger
        from agent_tooltrust.audit.sink import AuditSink
        from agent_tooltrust.engine.engine import Engine
        from agent_tooltrust.policy.models import default_policy

        class MemorySink(AuditSink):
            def __init__(self) -> None:
                self.entries: list = []
            def write(self, entry: object) -> None:
                self.entries.append(entry)
            def query(self, session_id: str | None = None) -> list:
                return list(self.entries)

        sink = MemorySink()
        logger = AuditLogger(sink=sink)
        engine = Engine(default_policy("balanced"), audit_logger=logger)

        from agent_tooltrust.engine.normalize import normalize

        call = normalize(
            tool="query_logs", action="read", environment="staging",
            data_class="internal", agent_id="debug-bot",
        )
        decision = engine.evaluate("query_logs", "read", "staging", "internal", "debug-bot")
        logger.log(decision, call)
        entry = sink.entries[0]
        assert entry.counterfactual is not None
        assert isinstance(entry.counterfactual, float)


class TestCalibrateCLI:
    def test_calibrate_report_runs(self) -> None:
        from agent_tooltrust.cli import main

        rc = main(["calibrate", "report"])
        assert rc == 0
