"""Output inspector — scan tool results for secrets, PII, and injection.

Scans tool output before it reaches the model to prevent data leakage
and adversarial payload injection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_SECRET_PATTERNS: list[tuple[str, str]] = [
    (r"sk-(?:proj|ant|svcacct)-[A-Za-z0-9_-]{20,}", "OpenAI API key"),
    (r"sk-[A-Za-z0-9]{32,}", "Generic API key (sk- prefix)"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    (r"gh[pousr]_[A-Za-z0-9]{36}", "GitHub personal access token"),
    (r"github_pat_[A-Za-z0-9_]{22,}", "GitHub fine-grained token"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT token"),
    (r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", "Private key"),
    (r"AIza[0-9A-Za-z_-]{35}", "Google API key"),
]

_PII_PATTERNS: list[tuple[str, str]] = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN (XXX-XX-XXXX)"),
    (r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b", "Credit card number"),
    (r"\b\d{3}-\d{5}-\d{4}\b", "SSN alternate (XXX-XXXXX-XXXX)"),
]

_INJECTION_PATTERNS: list[str] = [
    r"ignore (?:all )?previous (?:instructions|constraints)",
    r"you are now (?:operating in|an?)",
    r"pretend (?:you are|to be)",
    r"disable (?:all )?safety (?:checks|mechanisms|filters)",
    r"bypass (?:all )?(?:restrictions|limits|safeguards)",
    r"system[:\s]+override",
    r"act as (?:if|though) you (?:are|have)",
    r"forget (?:everything|your training|your constraints)",
]


@dataclass
class InspectResult:
    """Result of output inspection.

    Args:
        clean: True if no issues were found.
        findings: Human-readable descriptions of each finding.
        severity: Overall severity — "warn" or "block".
        redacted: Redacted version of the output if redact=True was passed.
    """

    clean: bool
    findings: list[str] = field(default_factory=list)
    severity: str = "warn"
    redacted: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation."""
        return {
            "clean": self.clean,
            "severity": self.severity,
            "findings": self.findings,
            "redacted": self.redacted,
        }


def inspect_output(text: str, *, redact: bool = False) -> InspectResult:
    """Inspect tool output for secrets, PII, and injection payloads.

    Args:
        text: The raw tool output to inspect.
        redact: If True, return a redacted version with secrets replaced.

    Returns:
        An InspectResult with findings, severity, and optional redacted text.
    """
    if not text:
        return InspectResult(clean=True)

    findings: list[str] = []
    severity = "warn"

    _scan_patterns(text, _SECRET_PATTERNS, "Secret", findings)
    _scan_patterns(text, _PII_PATTERNS, "PII", findings)
    _scan_injection(text, findings)

    for finding in findings:
        if finding.startswith("Secret") or finding.startswith("Injection"):
            severity = "block"

    redacted_text: str | None = None
    if redact:
        redacted_text = text
        for pattern, _ in _SECRET_PATTERNS:
            redacted_text = re.sub(
                pattern, lambda m: f"[REDACTED-{m.lastgroup or 'secret'}]", redacted_text
            )

    return InspectResult(
        clean=len(findings) == 0,
        findings=findings,
        severity=severity,
        redacted=redacted_text,
    )


def _scan_patterns(
    text: str,
    patterns: list[tuple[str, str]],
    category: str,
    findings: list[str],
) -> None:
    for pattern, label in patterns:
        if re.search(pattern, text):
            findings.append(f"{category}: {label} detected in output")


def _scan_injection(text: str, findings: list[str]) -> None:
    text_lower = text.lower()
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            findings.append(f"Injection: adversarial pattern '{pattern}' detected")
