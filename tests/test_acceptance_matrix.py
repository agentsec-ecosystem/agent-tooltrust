"""M1.11/M1.12 — the 40-cell acceptance matrix (F-01..F-05, F-12).

Every cell in the golden fixture must produce exactly the documented decision
and reason_code. This is the deterministic correctness gate that CI runs on
every push. Also includes the CUJ 9 fail-closed sub-sweep (6 failure
scenarios -> deny with distinct reason codes).
"""

from pathlib import Path

import pytest
import yaml

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy

FIXTURE = Path(__file__).parent / "fixtures" / "acceptance_matrix.yaml"

MATRIX = yaml.safe_load(FIXTURE.read_text())
ENGINE = Engine(default_policy(MATRIX["policy"]))


def _pytest_id(cell):
    return (
        f"{cell['tool']}|{cell['action']}|{cell['environment']}|"
        f"{cell['data_class']}->{cell['decision']}"
    )


@pytest.mark.parametrize(
    "cell",
    MATRIX["cells"],
    ids=_pytest_id,
)
def test_acceptance_matrix_cell(cell):
    decision = ENGINE.evaluate(
        tool_name=cell["tool"],
        action=cell["action"],
        environment=cell["environment"],
        data_class=cell["data_class"],
        agent_id=MATRIX["agent_id"],
    )
    assert decision.decision == cell["decision"]
    assert decision.reason_code == cell["reason_code"]


class TestMatrixCoverage:
    def test_matrix_has_40_cells(self):
        assert len(MATRIX["cells"]) == 40

    def test_all_four_decision_types_present(self):
        seen = {c["decision"] for c in MATRIX["cells"]}
        assert seen == {"allow", "audit", "escalate", "deny"}

    def test_safety_no_unsafe_cell_is_allowed(self):
        allowed = [c for c in MATRIX["cells"] if c["decision"] == "allow"]
        for cell in allowed:
            assert cell["action"] in ("read", "write")
            assert not (cell["action"] == "write" and cell["environment"] == "production")
            assert cell["action"] != "grant"


class TestFailClosedSweep:
    def test_unknown_tool_fails_closed(self):
        decision = ENGINE.evaluate("rm -rf /", "delete", "production", "restricted", "release-bot")
        assert decision.decision == "deny"
        assert decision.reason_code == "deny_unknown_tool"

    def test_blank_tool_fails_closed(self):
        decision = ENGINE.evaluate("  ", "read", "production", "restricted", "release-bot")
        assert decision.decision == "deny"
        assert decision.reason_code == "deny_malformed_input"

    def test_blank_action_fails_closed(self):
        decision = ENGINE.evaluate("query_logs", "", "production", "restricted", "release-bot")
        assert decision.decision == "deny"
        assert decision.reason_code == "deny_malformed_input"

    def test_unicode_confusable_never_allows(self):
        decision = ENGINE.evaluate(
            "drop_dаtabase", "delete", "production", "customer_pii", "release-bot"
        )
        assert decision.reason_code in ("deny_critical_op", "deny_unknown_tool")

    def test_injection_attempt_denied(self):
        decision = ENGINE.evaluate(
            "force_push", "delete", "production", "customer_pii", "release-bot"
        )
        assert decision.decision == "deny"
