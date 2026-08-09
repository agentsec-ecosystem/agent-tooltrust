# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 0.1.x | ✅ |

## Reporting a Vulnerability

Do NOT open a public issue. Report vulnerabilities privately via GitHub's [private vulnerability reporting](https://github.com/deghosal-2026/agent-tooltrust/security/advisories/new). Include:

- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact

We will acknowledge within 48 hours and provide a timeline for remediation.

## Security Design

Agent ToolTrust is a policy engine that gates tool invocations. Key security properties:

- **Policy-as-code** makes trust rules explicit, auditable, and reviewable
- **Explanation artifacts** expose decision rationale — no black-box denials
- **Audit trail** records every allow/deny/escalate decision with full context
- **Secrets scanning** (trufflehog) runs in CI on every push