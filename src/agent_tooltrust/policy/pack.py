"""M1 #91 — policy pack format (tools.yaml + tests.yaml).

A pack is a self-contained, shareable unit of policy: a ``tools.yaml`` policy
document (schema-validated like any tooltrust.yaml) plus an optional
``tests.yaml`` of golden decision fixtures. The pack is validated
deterministically — no LLM, no randomness — so the same pack+fixtures produce
the same result on every run (F-61, F-71).

Layout (any directory, or a direct path to ``tools.yaml``)::

    my-pack/
      tools.yaml    # policy document (rules, tool hiding, arg policy)
      tests.yaml    # optional golden fixtures; validated against tools.yaml

``validate_pack`` parses both files, rejects malformed schemas, unknown keys,
duplicate tool names, and fixtures that reference tools the pack does not
declare. ``run_pack_tests`` replays the fixtures through the :class:`Engine`
and returns per-fixture results; a fixture referencing an unevaluable tool
raises :class:`PackError` — never a silent skip.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agent_tooltrust.errors import ToolTrustError
from agent_tooltrust.policy.loader import load_policy
from agent_tooltrust.policy.models import Policy
from agent_tooltrust.policy.schema import PolicyDocument, parse_tooltrust_yaml

#: Canonical pack filenames. Only these two files are part of the pack format.
PACK_TOOLS = "tools.yaml"
PACK_TESTS = "tests.yaml"


class PackError(ToolTrustError):
    """A pack is malformed or internally inconsistent.

    Raised for missing files, duplicate tool names, and fixtures referencing
    tools the pack does not declare. Carries the generic policy-parse reason
    code so downstream fail-closed paths treat it like any config error.
    """

    reason_code = "deny_policy_parse_error"


class TestFixture(BaseModel):
    """One golden decision fixture in ``tests.yaml``.

    Each fixture fully specifies a call and the decision it must produce. All
    fields are explicit (no wildcards) so results are deterministic and a
    fixture can never silently match by accident.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Human-readable fixture name")
    tool: str = Field(min_length=1, description="Tool name (must exist in the pack)")
    action: str = Field(min_length=1, description="Action verb (e.g. read/write)")
    environment: str = Field(min_length=1, description="Environment name")
    data_class: str = Field(min_length=1, description="Data classification")
    agent_id: str = Field(min_length=1, description="Agent identity")
    expect: str = Field(min_length=1, description="Expected decision (allow/audit/escalate/deny)")


class TestDocument(BaseModel):
    """The ``tests.yaml`` document: a list of golden fixtures."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, description="Pack tests version (semver-style)")
    fixtures: list[TestFixture] = Field(default_factory=list)


class PackResult:
    """Outcome of one fixture replay in :func:`run_pack_tests`."""

    __slots__ = ("decision", "expected", "name")

    def __init__(self, name: str, expected: str, decision: str) -> None:
        self.name = name
        self.expected = expected
        self.decision = decision

    @property
    def passed(self) -> bool:
        """Whether the replay matched the expected decision."""
        return self.expected == self.decision

    def __repr__(self) -> str:
        return f"PackResult({self.name!r}, expected={self.expected!r}, got={self.decision!r})"


def _resolve_pack_dir(target: str | Path) -> Path:
    """Return the pack directory for a target path.

    If *target* points at a ``tools.yaml`` file directly, use its parent as
    the pack directory; otherwise treat the path as the pack directory itself.

    Args:
        target: Path to a pack directory or its ``tools.yaml``.

    Returns:
        The pack directory as a :class:`Path`.
    """
    path = Path(target)
    if path.is_file() and path.name == PACK_TOOLS:
        return path.parent
    return path


def _load_policy_document(text: str) -> PolicyDocument:
    """Parse a policy document, wrapping schema errors as :class:`PackError`.

    Args:
        text: The raw YAML of ``tools.yaml``.

    Returns:
        The parsed :class:`PolicyDocument`.

    Raises:
        PackError: If the document is not valid YAML or violates the schema.
    """
    try:
        return parse_tooltrust_yaml(text)
    except (ValueError, ToolTrustError, yaml.YAMLError) as exc:
        raise PackError(str(exc)) from exc


def _duplicate_tool_errors(doc: PolicyDocument) -> list[str]:
    """Collect duplicate-tool-name errors from the ``tools`` section.

    Args:
        doc: The parsed policy document.

    Returns:
        One human-readable error per duplicated tool name.
    """
    seen: dict[str, int] = {}
    for spec in doc.tools:
        seen[spec.name] = seen.get(spec.name, 0) + 1
    return [
        f"duplicate tool name: {name} ({count} entries in tools.yaml)"
        for name, count in sorted(seen.items())
        if count > 1
    ]


def _pack_declares(doc: PolicyDocument) -> set[str]:
    """The set of tool names a pack declares in its ``tools`` section."""
    return {spec.name for spec in doc.tools}


def _resolvable_tools(declared: set[str]) -> set[str]:
    """Every tool a fixture may reference: the taxonomy-known tools.

    A fixture must never reference a tool the engine could not evaluate, or
    its expected decision could pass by accident (e.g. an unknown tool always
    denies). The Engine only evaluates taxonomy-registered tools, so a pack
    may declare custom ``tools.yaml`` tools for hiding/argument policy, but a
    fixture referencing one would always resolve to an unknown-tool deny. Keep
    the resolvable set to taxonomy-known names so such a fixture is rejected
    loudly at validate time, never silently passing as a deny.

    Args:
        declared: Tool names declared by the pack's ``tools`` section (kept
            for signature compatibility; the engine cannot evaluate a tool the
            taxonomy does not know even when declared).

    Returns:
        The taxonomy-known tool names the engine can evaluate.
    """
    from agent_tooltrust.taxonomy import KNOWN_TOOLS

    return set(KNOWN_TOOLS)


def validate_pack(target: str | Path) -> tuple[list[str], Policy]:
    """Validate a policy pack.

    Parses ``tools.yaml`` against the schema and ``tests.yaml`` (if present)
    against the fixture schema, then checks internal consistency: duplicate
    tool names are rejected, and every fixture must reference a tool the
    engine can evaluate (a taxonomy-known tool). Missing ``tests.yaml`` is
    valid (a pack may carry no tests yet).

    Args:
        target: Pack directory or a direct path to its ``tools.yaml``.

    Returns:
        A ``(errors, policy)`` pair. ``errors`` is empty for a valid pack;
        ``policy`` is the loaded :class:`Policy` (best-effort even on error).
    """
    pack_dir = _resolve_pack_dir(target)
    tools_path = pack_dir / PACK_TOOLS
    tests_path = pack_dir / PACK_TESTS
    errors: list[str] = []

    if not tools_path.is_file():
        return [f"missing {PACK_TOOLS} in {pack_dir}"], _empty_policy()

    try:
        text = tools_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read {tools_path}: {exc}"], _empty_policy()

    try:
        doc = _load_policy_document(text)
    except PackError as exc:
        return [str(exc)], _empty_policy()
    errors.extend(_duplicate_tool_errors(doc))

    declared = _pack_declares(doc)

    if tests_path.is_file():
        try:
            test_text = tests_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"cannot read {tests_path}: {exc}")
        else:
            errors.extend(_validate_tests(test_text, _resolvable_tools(declared)))

    policy = _load_policy(doc, tools_path)
    return errors, policy


def _validate_tests(text: str, declared: set[str]) -> list[str]:
    """Validate ``tests.yaml`` against the fixture schema and resolvable tools.

    Args:
        text: Raw YAML of ``tests.yaml``.
        declared: Tool names declared by the pack's ``tools`` section.

    Returns:
        List of human-readable validation errors (empty if valid).
    """
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return [f"invalid {PACK_TESTS}: must contain a single YAML mapping"]
    try:
        doc = TestDocument.model_validate(data)
    except Exception as exc:
        return [f"invalid {PACK_TESTS}: {exc}"]
    return [
        f"fixture {fixture.name!r} references tool {fixture.tool!r}, which the "
        "engine cannot evaluate (not a taxonomy-known tool)"
        for fixture in doc.fixtures
        if fixture.tool not in declared
    ]


def _load_policy(doc: PolicyDocument, tools_path: Path) -> Policy:
    """Load the pack policy through the standard loader.

    Args:
        doc: The validated policy document (kept for its declared tools).
        tools_path: Path to ``tools.yaml`` for the loader.

    Returns:
        The merged :class:`Policy`.
    """
    try:
        return load_policy(tools_path)
    except ToolTrustError as exc:
        raise PackError(str(exc)) from exc


def _empty_policy() -> Policy:
    """A minimal valid policy used when the pack is unreadable."""
    from agent_tooltrust.policy.models import default_policy

    return default_policy("balanced")


def run_pack_tests(target: str | Path) -> list[PackResult]:
    """Replay the pack's golden fixtures through the Engine.

    Deterministic by construction: the Engine never invokes an LLM, and
    fixtures are fully specified. A fixture referencing a tool the pack does
    not declare raises :class:`PackError` (never a silent skip).

    Args:
        target: Pack directory or a direct path to its ``tools.yaml``.

    Returns:
        One :class:`PackResult` per fixture; empty when the pack has no
        ``tests.yaml``.

    Raises:
        PackError: If the pack is invalid or a fixture is unevaluable.
    """
    pack_dir = _resolve_pack_dir(target)
    errors, policy = validate_pack(pack_dir)
    if errors:
        raise PackError("; ".join(errors))

    tests_path = pack_dir / PACK_TESTS
    if not tests_path.is_file():
        return []

    from agent_tooltrust.engine.engine import Engine

    engine = Engine(policy)
    data = yaml.safe_load(tests_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PackError(f"invalid {PACK_TESTS}: must contain a single YAML mapping")
    doc = TestDocument.model_validate(data)
    results: list[PackResult] = []
    for fixture in doc.fixtures:
        decision = engine.evaluate(
            tool_name=fixture.tool,
            action=fixture.action,
            environment=fixture.environment,
            data_class=fixture.data_class,
            agent_id=fixture.agent_id,
        )
        results.append(PackResult(fixture.name, fixture.expect, decision.decision))
    return results
