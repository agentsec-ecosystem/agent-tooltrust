"""Field test harness — drive ToolTrust against 100 real agents.

M7 (F-75, F-89). ``FieldTestRunner`` loads a scenario matrix and an agent
roster, runs every (agent, scenario) pair through the engine, and asserts the
decision, criticality, and reason code match the golden expectations. The
runner is framework-agnostic: the per-agent differentiation is the agent's
identity, which resolves to an ``agent_class`` profile in policy.

Adversarial scenarios assert the fail-closed invariant: an attack (prompt
injection, Unicode obfuscation, malformed input, unknown tool) is either
denied outright or canonicalized to the exact decision the real tool would
receive — never a free pass.
"""

from __future__ import annotations

from agent_tooltrust.field.models import FieldAgent, FieldScenario, FieldTestCase
from agent_tooltrust.field.replan import LiveReplan, ReplanResult, ScriptedReplan
from agent_tooltrust.field.report import build_report
from agent_tooltrust.field.runner import FieldTestReport, FieldTestRunner

__all__ = [
    "FieldAgent",
    "FieldScenario",
    "FieldTestCase",
    "FieldTestReport",
    "FieldTestRunner",
    "LiveReplan",
    "ReplanResult",
    "ScriptedReplan",
    "build_report",
]
