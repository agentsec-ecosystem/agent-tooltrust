"""Tool definition scanner — detect adversarial patterns in tool names and descriptions.

Scans for hidden instructions, typosquatting via Unicode lookalikes, and
adversarial patterns that attempt to override agent behavior.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

_HIDDEN_INSTRUCTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "you are now",
    "pretend you are",
    "act as if",
    "forget everything",
    "disregard prior",
    "override system",
    "override all previous",
    "bypass restrictions",
    "unrestricted mode",
    "no restrictions apply",
    "full access",
    "administrator privileges",
]

_LOOKALIKE_RANGES = {
    "cyrillic": range(0x0400, 0x04FF),
    "greek": range(0x0370, 0x03FF),
    "armenian": range(0x0530, 0x058F),
}

_ASCII_LETTERS = set(range(ord("a"), ord("z") + 1)) | set(range(ord("A"), ord("Z") + 1))


@dataclass
class ToolScanResult:
    """Result of scanning a tool definition.

    Args:
        tool_name: The name of the tool that was scanned.
        clean: True if no issues were found.
        findings: Human-readable descriptions of each finding.
    """

    tool_name: str
    clean: bool
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation."""
        return {
            "tool_name": self.tool_name,
            "clean": self.clean,
            "findings": self.findings,
        }


def scan_tool_definition(tool_name: str, description: str) -> ToolScanResult:
    """Scan a tool definition for adversarial patterns.

    Args:
        tool_name: The tool's name.
        description: The tool's description text.

    Returns:
        A ToolScanResult with findings if any issues were detected.
    """
    findings: list[str] = []
    _scan_hidden_instructions(description, findings)
    _scan_typosquatting(tool_name, findings)
    return ToolScanResult(
        tool_name=tool_name,
        clean=len(findings) == 0,
        findings=findings,
    )


def _scan_hidden_instructions(description: str, findings: list[str]) -> None:
    """Check the description for hidden instruction patterns.

    Args:
        description: The tool description text.
        findings: List to append findings to.
    """
    desc_lower = description.lower()
    for pattern in _HIDDEN_INSTRUCTION_PATTERNS:
        if pattern in desc_lower:
            findings.append(
                f"Hidden instruction detected: '{pattern}' in tool description"
            )
    if len(description) > 500:
        findings.append(
            f"Unusually long description ({len(description)} chars) — "
            "may contain hidden instructions"
        )


def _scan_typosquatting(tool_name: str, findings: list[str]) -> None:
    """Check for Unicode lookalike characters in the tool name.

    Args:
        tool_name: The tool name.
        findings: List to append findings to.
    """
    nfkc_name = unicodedata.normalize("NFKC", tool_name)

    lookalikes: list[str] = []
    for ch in tool_name:
        cp = ord(ch)
        if cp in _ASCII_LETTERS:
            continue
        if cp == ord("_") or cp == ord("-"):
            continue
        script = ""
        for name, rng in _LOOKALIKE_RANGES.items():
            if cp in rng:
                script = name
                break
        if script:
            lookalikes.append(f"U+{cp:04X} ({unicodedata.name(ch, 'UNKNOWN')}) from {script}")

    if lookalikes:
        findings.append(
            f"Unicode lookalike characters in tool name: {', '.join(lookalikes)}. "
            f"NFKC normalized: '{nfkc_name}'"
        )

    if tool_name != nfkc_name:
        findings.append(
            f"Tool name '{tool_name}' normalizes to '{nfkc_name}' under NFKC — "
            "possible typosquatting attempt"
        )
