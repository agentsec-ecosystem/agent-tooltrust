"""Field test report — render a ``FieldTestReport`` as markdown."""

from __future__ import annotations

from typing import Any

from agent_tooltrust.field.models import FieldTestCase


def build_report(report: Any) -> str:
    """Render a FieldTestReport as a markdown document.

    Args:
        report: A :class:`FieldTestReport` (or object with the same surface).

    Returns:
        The report as a markdown string, ready to write to disk.
    """
    lines: list[str] = [
        "# Field Test Report",
        "",
        f"- **Total cases:** {report.total}",
        f"- **Passed:** {report.passed}",
        f"- **Failed:** {report.failed}",
        f"- **Overall pass rate:** {report.pass_rate():.1%}",
        f"- **Decision matrix:** {len(report.decision_cases)} cases, "
        f"{report.pass_rate(report.decision_cases):.1%} pass",
        f"- **Adversarial sub-matrix:** {len(report.adversarial_cases)} cases, "
        f"{report.pass_rate(report.adversarial_cases):.1%} pass",
        "",
    ]

    rates = report.framework_pass_rates()
    if rates:
        lines.append("## Pass Rate by Framework")
        lines.append("")
        lines.append("| Framework | Pass rate |")
        lines.append("|-----------|-----------|")
        for framework in sorted(rates):
            lines.append(f"| {framework} | {rates[framework]:.1%} |")
        lines.append("")

    lines.append("## Scenario Matrix")
    lines.append("")
    lines.append(
        "| Scenario | Type | Agent | Framework | Class | Expected | Actual | Pass | Notes |"
    )
    lines.append("|----------|------|-------|-----------|-------|----------|--------|------|-------|")
    for case in report.cases:
        lines.append(_render_row(case))

    failures = report.failures()
    if failures:
        lines.append("")
        lines.append("## Failures")
        lines.append("")
        for case in failures:
            lines.append(f"- **{case.scenario.id}** / **{case.agent.agent_id}**: {case.notes}")
        lines.append("")

    return "\n".join(lines) + "\n"


def _render_row(case: FieldTestCase) -> str:
    expected = case.expected or {}
    expected_str = " | ".join(
        f"{k}={expected.get(k, '-')}" for k in ("decision", "criticality", "reason_code")
    )
    notes = case.notes.replace("|", "\\|") if case.notes else "-"
    return (
        f"| {case.scenario.id} | {case.scenario.type} | {case.agent.agent_id} "
        f"| {case.agent.framework} | {case.agent_class} | {expected_str} "
        f"| {case.actual}/{case.criticality}/{case.reason_code} "
        f"| {'PASS' if case.passed else 'FAIL'} | {notes} |"
    )
