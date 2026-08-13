"""``tooltrust report`` — generate governance compliance reports."""

from __future__ import annotations

import argparse
import csv
import io
from collections import Counter
from typing import Any

from agent_tooltrust.audit.logger import AuditLogger


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust report`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "report",
        help="generate governance compliance reports",
        description="Aggregate audit data into compliance reports.",
    )
    parser.add_argument(
        "--type", choices=["compliance", "summary"], default="compliance",
        help="Report type (default: compliance)",
    )
    parser.add_argument("--period", default="all", help="Period filter (e.g., 2026-Q3, all)")
    parser.add_argument(
        "--format", choices=["html", "csv"], default="html",
        help="Output format (default: html)",
    )
    parser.set_defaults(func=_report)


def _report(args: argparse.Namespace) -> int:
    """Generate and print a governance report.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0.
    """
    logger = AuditLogger()
    entries = logger.query()

    if args.format == "csv":
        _csv_report(entries)
    else:
        _html_report(entries, args.type, args.period)

    return 0


def _csv_report(entries: list[Any]) -> None:
    """Output a CSV report from audit entries.

    Args:
        entries: List of AuditEntry objects.
    """
    if not entries:
        print("No audit entries found.")
        return

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=entries[0].to_dict().keys())
    writer.writeheader()
    for entry in entries:
        writer.writerow(entry.to_dict())
    print(output.getvalue())


def _html_report(entries: list[Any], report_type: str, period: str) -> None:
    """Output an HTML governance report.

    Args:
        entries: List of AuditEntry objects.
        report_type: Type of report.
        period: Period string for display.
    """
    if not entries:
        print("<html><body><h1>No audit entries found.</h1></body></html>")
        return

    decision_counts = Counter(e.decision for e in entries)
    tool_counts = Counter(e.tool for e in entries)
    agent_counts = Counter(e.agent_id for e in entries)
    total = len(entries)

    html = f"""<html>
<head><title>ToolTrust Governance Report</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2em auto; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  .bar {{ display: inline-block; height: 16px; background: #4a90d9; border-radius: 2px; }}
  .deny {{ background: #d94a4a; }}
  .escalate {{ background: #d9a64a; }}
  .audit {{ background: #d9c84a; }}
  .allow {{ background: #4ad96a; }}
  .summary {{ background: #f5f5f5; padding: 1em; border-radius: 8px; margin-bottom: 1em; }}
</style></head>
<body>
<h1>ToolTrust Governance Report</h1>
<div class="summary">
  <strong>Type:</strong> {report_type} |
  <strong>Period:</strong> {period} |
  <strong>Total decisions:</strong> {total}
</div>

<h2>Decision Distribution</h2>
<table><tr><th>Decision</th><th>Count</th><th>%</th><th>Distribution</th></tr>"""
    for dec in ["allow", "audit", "escalate", "deny"]:
        count = decision_counts.get(dec, 0)
        pct = count / total * 100 if total > 0 else 0
        bar = f'<span class="bar {dec}" style="width:{int(pct)}%"></span> {pct:.1f}%'
        html += f"<tr><td>{dec}</td><td>{count}</td><td>{pct:.1f}%</td><td>{bar}</td></tr>"
    html += "</table>"

    html += "<h2>Top Tools</h2><table><tr><th>Tool</th><th>Calls</th></tr>"
    for tool, count in tool_counts.most_common(10):
        html += f"<tr><td>{tool}</td><td>{count}</td></tr>"
    html += "</table>"

    html += "<h2>Top Agents</h2><table><tr><th>Agent</th><th>Calls</th></tr>"
    for agent, count in agent_counts.most_common(10):
        html += f"<tr><td>{agent}</td><td>{count}</td></tr>"
    html += "</table>"

    html += "</body></html>"
    print(html)
