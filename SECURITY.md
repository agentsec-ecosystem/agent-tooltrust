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
- **Fail-closed** — engine crashes, unknown tools, and malformed input all resolve to deny

## OWASP Agentic AI Top 10 Coverage

| # | Risk | Covered | ToolTrust Mitigation |
|---|------|---------|---------------------|
| A01 | **Excessive Agency** — agent performs actions beyond intended scope | ✅ v0.1.0 | Policy rules gating every tool call by tool, action, environment, data class, and agent identity. Decision pipeline: allow → audit → escalate → deny |
| A02 | **Supply Chain Vulnerabilities** — malicious tools, plugins, or MCP servers | ✅ v0.1.0 | `tooltrust scan` detects hidden instructions, typosquatting, and adversarial patterns in tool definitions (F-81) |
| A03 | **Data Leakage / Exposure** — PII, secrets, or sensitive data in outputs | ⚠️ Partial | Output inspector (F-82) catches secrets (API keys), PII (SSN, credit card), and injection payloads in tool results. Full output inspection via dispatcher parser in v0.2.0 |
| A04 | **Unbounded Consumption** — resource exhaustion, infinite loops | ✅ v0.1.0 | Per-session call budgets (M5) + rate/burst limits (F-86). Budget exceeded → deny("budget_exceeded") |
| A05 | **Goal Hijacking / Prompt Injection** — "ignore previous instructions" | ✅ v0.1.0 | Tool scanner detects hidden prompts in tool descriptions. Output inspector detects injection payloads in tool results |
| A06 | **Tool Misuse** — agent misuses authorized tools (delete production, query PII) | ✅ v0.1.0 | 5-dimension risk scoring (tool category, action class, environment, data sensitivity, agent class). Destructive ops + sensitive data = deny |
| A07 | **Insecure Output Handling** — agent processes untrusted tool results | ⚠️ Partial | Output inspector catches secrets and PII before agent consumes results. Dispatcher parser for shell/HTTP tools in v0.2.0 |
| A08 | **Multi-Agent Coordination Failures** — sub-agents exceed delegated scope | ❌ v0.2.0 | Child-agent delegation with scope subset invariant (F-88). Parent scope [A,B,C] → child scope [A,B] allowed; [A,B,D] denied |
| A09 | **Overreliance** — humans trust agent decisions without verification | ✅ v0.1.0 | Every decision carries machine-readable reason_code + human-readable explanation + risk factor breakdown. Escalate decisions require explicit human approval |
| A10 | **Lack of Audit / Accountability** — no record of agent actions | ✅ v0.1.0 | Full audit pipeline: JSONL (zero-dep default), SQLite (local query), Postgres (operational). `tooltrust audit` CLI for query/export. Tamper-evident hash chain (v0.1.0 F-34) |

**Coverage summary:** 7/10 fully covered in v0.1.0, 2 partially covered (A03, A07), 1 deferred to v0.2.0 (A08).

## CI Security Scanning

[trufflehog](https://github.com/trufflesecurity/trufflehog) runs on every push to detect secrets accidentally committed to the repository.