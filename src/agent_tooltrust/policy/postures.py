"""M2.3 — posture presets + ``tooltrust init`` (#3, F-66).

Three posture presets ship as YAML in this package: ``strict.yaml``,
``balanced.yaml``, ``permissive.yaml``. They are generated from
:func:`~agent_tooltrust.policy.models.default_policy` so there is exactly one
source of truth for preset rules/risk maps; the ``tooltrust init`` command
copies the chosen preset into a usable ``tooltrust.yaml``.

The merger in :mod:`agent_tooltrust.policy.loader` treats a loaded org file as
an overlay on top of ``default_policy(posture)``, so a preset written by init
round-trips to the identical :class:`Policy` (its sections equal the base and
simply overwrite with the same values).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from agent_tooltrust.policy.models import Rule, default_policy

#: Directory the shipped preset files live in (package data).
PRESET_DIR = Path(__file__).parent / "postures"


def _yaml_dump(data: Mapping[str, object]) -> str:
    """Serialize *data* keeping string scalars unambiguous.

    A naked ``1.0.0`` would be resolved by PyYAML as the float ``1.0`` and the
    schema's ``version: str`` field would then reject it. We force any scalar
    that PyYAML would implicitly resolve to a non-string type to be quoted, so
    the emitted preset round-trips through ``safe_load`` as the same strings.
    """
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    lines: list[str] = []
    for line in text.splitlines():
        if ": " in line:
            key, plain = line.split(": ", 1)
            if not isinstance(yaml.safe_load(plain), str):
                quote = "'" if '"' not in plain else '"'
                line = f"{key}: {quote}{plain}{quote}"
        lines.append(line)
    return "\n".join(lines) + "\n"


VALID_POSTURES = frozenset({"strict", "balanced", "permissive"})


def available_postures() -> list[str]:
    """Names of the shipped posture presets, sorted."""
    return sorted(VALID_POSTURES)


def render_preset(posture: str) -> str:
    """Render the shipped posture preset as a tooltrust.yaml document.

    Raises :class:`ValueError` for unknown postures so callers can't silently
    generate a misconfigured file.
    """
    if posture not in VALID_POSTURES:
        raise ValueError(f"unknown posture preset: {posture!r}")
    policy = default_policy(posture)
    document = {
        "version": "1.0.0",
        "posture": posture,
        "environments": {name: {"criticality": risk} for name, risk in policy.environments.items()},
        "data_classes": {name: {"sensitivity": risk} for name, risk in policy.data_classes.items()},
        "risk_weights": dict(policy.risk_weights),
        "rules": [_rule_spec(rule) for rule in policy.rules],
        "escalation": {"threshold": 0.5, "ttl_seconds": 300},
        "audit": {"sink": "jsonl", "path": "~/.tooltrust/audit.jsonl", "postgres_url": None},
    }
    return _yaml_dump(document)


def _rule_spec(rule: Rule) -> dict[str, str]:
    """Serialize a :class:`Rule` to the dict shape the ``tooltrust.yaml`` schema expects."""
    return {
        "decision": rule.decision,
        "tool": rule.tool,
        "action": rule.action,
        "environment": rule.environment,
        "data_class": rule.data_class,
        "reason": rule.reason,
    }


def init_policy(posture: str, path: str | Path | None = None) -> Path:
    """Write a ``tooltrust.yaml`` for *posture* to *path* (default ./tooltrust.yaml).

    Returns the path written so callers (and tests) can locate it. The written
    file is validated by the loader in tests, so init can never emit a broken
    policy by construction.
    """
    out = Path(path) if path is not None else Path("tooltrust.yaml")
    out.write_text(render_preset(posture), encoding="utf-8")
    return out
