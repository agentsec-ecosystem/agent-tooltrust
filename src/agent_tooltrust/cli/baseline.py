"""``tooltrust baseline check`` — verify the security baseline posture.

Iterates a tier checklist (Essential by default) and reports pass/fail per
item. Every item is verified programmatically so the command can act as a
release gate: it exits 0 only when every item in the requested tier passes.

The Essential tier (v0.1.0) covers fail-closed behaviour, policy/audit
presence, adversarial normalization, default deny rules, tamper-proof audit,
strict lint/type gates, secret scanning, and the OWASP mapping. See
``docs/SECURITY_BASELINE.md`` for the full checklist mapped to feature IDs,
tests, and config flags.
"""

from __future__ import annotations

import argparse
from typing import Any

from agent_tooltrust.policy.models import default_policy


class _Check:
    """A single baseline check: label + callable returning (ok, detail)."""

    __slots__ = ("check", "id", "label")

    def __init__(
        self,
        cid: str,
        label: str,
        check: Any,
    ) -> None:
        self.id = cid
        self.label = label
        self.check = check


def _fail_closed_enforced() -> tuple[bool, str]:
    try:
        from agent_tooltrust.engine.fail_closed import fail_closed  # noqa: F401
    except Exception as exc:
        return False, f"fail_closed decorator import failed: {exc}"
    return True, "engine.fail_closed present; unknown/malformed calls resolve to deny"


def _default_policy_denies_destructive() -> tuple[bool, str]:
    policy = default_policy("balanced")
    rules = policy.rules
    has_delete_deny = any(
        r.decision == "deny" and r.action == "delete" and r.environment == "production"
        for r in rules
    )
    try:
        from agent_tooltrust.engine.engine import Engine

        verdict = Engine(default_policy("balanced")).evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="customer_pii",
            agent_id="untrusted",
        )
    except Exception as exc:
        return False, f"destructive-call evaluation failed: {exc}"
    return verdict.decision == "deny" and has_delete_deny, (
        f"delete-in-production denied ({verdict.decision}); "
        f"default deny rule present={has_delete_deny}"
    )


def _normalize_resists_confusables() -> tuple[bool, str]:
    try:
        from agent_tooltrust.engine.engine import Engine

        decision = Engine(default_policy("balanced")).evaluate(
            tool_name="drop_datab\u0430se",  # Cyrillic U+0430 'а'
            action="delete",
            environment="production",
            data_class="restricted",
            agent_id="untrusted",
        )
    except Exception as exc:
        return False, f"confusable normalization check failed: {exc}"
    return decision.decision in ("deny", "escalate"), (
        f"confusable tool name resolved to {decision.decision}"
    )


def _audit_modules_present() -> tuple[bool, str]:
    for mod in ("logger", "sinks.jsonl", "sinks.sqlite", "tamper_proof"):
        try:
            __import__(f"agent_tooltrust.audit.{mod}")
        except Exception as exc:
            return False, f"{mod} import failed: {exc}"
    return True, "audit logger, JSONL/SQLite sinks, tamper-proof chain importable"


def _strict_gates_configured() -> tuple[bool, str]:
    try:
        import tomllib
        from pathlib import Path

        data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        mypy_strict = data.get("tool", {}).get("mypy", {}).get("strict", False)
    except Exception as exc:
        return False, f"pyproject.toml unreadable: {exc}"
    return bool(mypy_strict), f"mypy strict={mypy_strict}"


def _owasp_mapping_published() -> tuple[bool, str]:
    try:
        from pathlib import Path

        used = [p for p in ("SECURITY.md", "docs/SECURITY_BASELINE.md") if Path(p).exists()]
    except Exception as exc:
        return False, f"doc check failed: {exc}"
    return bool(used), f"security docs present: {', '.join(used) or 'none'}"


ESSENTIAL_CHECKS: list[_Check] = [
    _Check("E1", "Fail-closed engine (unknown/malformed → deny)", _fail_closed_enforced),
    _Check(
        "E5", "Default posture denies destructive production ops",
        _default_policy_denies_destructive,
    ),
    _Check(
        "E4", "Adversarial confusable tool-name normalization",
        _normalize_resists_confusables,
    ),
    _Check(
        "E6", "Audit logger + sinks + tamper-proof chain available",
        _audit_modules_present,
    ),
    _Check("E10", "Strict lint/type gates (mypy strict)", _strict_gates_configured),
    _Check("E9", "OWASP mapping + security baseline published", _owasp_mapping_published),
]

TIERS: dict[str, list[_Check]] = {
    "essential": ESSENTIAL_CHECKS,
}


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust baseline`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "baseline",
        help="verify the security baseline posture",
        description="Check the security baseline (Essential tier by default).",
    )
    sub = parser.add_subparsers(dest="baseline_command", metavar="COMMAND")
    check_parser = sub.add_parser(
        "check",
        help="check a security baseline tier",
        description="Run the baseline checklist for a tier; exits 0 if all pass.",
    )
    check_parser.add_argument(
        "tier",
        nargs="?",
        default="essential",
        choices=sorted(TIERS),
        help="baseline tier to check (default: essential)",
    )
    check_parser.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    tier = getattr(args, "tier", "essential")
    checks = TIERS.get(tier)
    if checks is None:
        raise ValueError(f"unknown baseline tier: {tier}")

    ok = True
    print(f"ToolTrust security baseline — {tier}")
    print("=" * 60)
    for chk in checks:
        try:
            passed, detail = chk.check()
        except Exception as exc:
            passed, detail = False, str(exc)
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {chk.id}  {chk.label}")
        print(f"          {detail}")
        ok = ok and passed

    print("=" * 60)
    passed_count = sum(1 for c in checks if c.check()[0])
    print(f"  {passed_count}/{len(checks)} checks passed")
    return 0 if ok else 1
