"""Session-to-session policy analyzer — batch analysis over audit entries.

Detects recurring benign denials, deny→allow transitions, dead rules, and
over-hit rules by comparing audit entries across sessions against the current
policy.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

# Using TYPE_CHECKING for Policy/Rule to avoid circular imports at runtime
from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.policy.models import Policy

IdentityContext = tuple[str, str, str, str, str]


@dataclass(frozen=True)
class RecurringDenial:
    context: IdentityContext
    deny_count: int
    sample_reason: str


@dataclass(frozen=True)
class DenyToAllowTransition:
    context: IdentityContext
    first_deny_at: str
    first_allow_at: str


@dataclass(frozen=True)
class DeadRule:
    rule_index: int
    decision: str
    tool: str
    action: str
    environment: str
    data_class: str
    reason: str


@dataclass(frozen=True)
class OverHitRule:
    reason_code: str
    match_count: int
    percentile: float


@dataclass(frozen=True)
class AnalyticsFindings:
    recurring_denials: list[RecurringDenial] = field(default_factory=list)
    deny_to_allow_transitions: list[DenyToAllowTransition] = field(default_factory=list)
    dead_rules: list[DeadRule] = field(default_factory=list)
    over_hit_rules: list[OverHitRule] = field(default_factory=list)


def _identity_key(entry: AuditEntry) -> IdentityContext:
    return (entry.tool, entry.action, entry.environment, entry.data_class, entry.agent_id)


def _find_recurring_denials(
    groups: dict[IdentityContext, list[AuditEntry]],
    min_denials: int,
) -> list[RecurringDenial]:
    result: list[RecurringDenial] = []
    for context, entries in groups.items():
        deny_count = sum(1 for e in entries if e.decision == "deny")
        has_allow = any(e.decision == "allow" for e in entries)
        if deny_count >= min_denials and not has_allow:
            deny_reasons = [
                e.reason_code for e in entries
                if e.decision == "deny" and e.reason_code
            ]
            sample_reason = (
                Counter(deny_reasons).most_common(1)[0][0]
                if deny_reasons else ""
            )
            result.append(RecurringDenial(
                context=context, deny_count=deny_count,
                sample_reason=sample_reason,
            ))
    return sorted(result, key=lambda r: -r.deny_count)


def _find_transitions(
    groups: dict[IdentityContext, list[AuditEntry]],
) -> list[DenyToAllowTransition]:
    result: list[DenyToAllowTransition] = []
    for context, entries in groups.items():
        sorted_entries = sorted(entries, key=lambda e: e.timestamp)
        deny_found = False
        first_deny_at: str | None = None
        for entry in sorted_entries:
            if entry.decision == "deny" and not deny_found:
                deny_found = True
                first_deny_at = entry.timestamp
            elif entry.decision == "allow" and deny_found:
                result.append(DenyToAllowTransition(
                    context=context,
                    first_deny_at=first_deny_at or "",
                    first_allow_at=entry.timestamp,
                ))
                deny_found = False
                first_deny_at = None
    return sorted(result, key=lambda t: t.first_allow_at)


def _find_dead_rules(
    entries: list[AuditEntry],
    policy: Policy,
) -> list[DeadRule]:
    if not policy or not policy.rules:
        return []
    matching_reasons: set[str] = {
        e.reason_code for e in entries if e.reason_code
    }
    result: list[DeadRule] = []
    for i, rule in enumerate(policy.rules):
        if rule.reason and rule.reason not in matching_reasons:
            result.append(DeadRule(
                rule_index=i,
                decision=rule.decision,
                tool=rule.tool,
                action=rule.action,
                environment=rule.environment,
                data_class=rule.data_class,
                reason=rule.reason,
            ))
    return result


def _find_over_hit_rules(
    entries: list[AuditEntry],
    percentile_threshold: float = 0.9,
) -> list[OverHitRule]:
    if not entries:
        return []
    reason_counts = Counter(e.reason_code for e in entries if e.reason_code)
    if not reason_counts:
        return []
    counts = sorted(reason_counts.values())
    n = len(counts)
    result: list[OverHitRule] = []
    for reason, count in reason_counts.items():
        rank = sum(1 for c in counts if c <= count)
        percentile = rank / n
        if percentile >= percentile_threshold:
            result.append(OverHitRule(
                reason_code=reason,
                match_count=count,
                percentile=round(percentile, 2),
            ))
    return sorted(result, key=lambda r: -r.match_count)


def analyze(
    entries: list[AuditEntry],
    policy: Policy | None = None,
    min_denials: int = 3,
    percentile_threshold: float = 0.9,
) -> AnalyticsFindings:
    groups: dict[IdentityContext, list[AuditEntry]] = defaultdict(list)
    for entry in entries:
        groups[_identity_key(entry)].append(entry)

    return AnalyticsFindings(
        recurring_denials=_find_recurring_denials(groups, min_denials),
        deny_to_allow_transitions=_find_transitions(groups),
        dead_rules=_find_dead_rules(entries, policy) if policy else [],
        over_hit_rules=_find_over_hit_rules(entries, percentile_threshold),
    )
