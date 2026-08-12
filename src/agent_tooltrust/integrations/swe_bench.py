"""M23 — SWE-bench integration (F-92, issue #135).

ToolTrust as a policy wrapper for SWE-bench coding-agent runs. A
:class:`SWEBenchToolMapper` classifies each raw SWE-bench tool call (``bash``,
``str_replace_editor``, ``write``) into a semantic action
(``read``/``write``/``delete``/``grant``) and detects destructive commands;
:class:`SWEBenchGuard` enforces the engine's policy per call and accumulates a
decision trace per benchmark task; :class:`SWEBenchRunner` replays whole
task lists (from YAML fixtures or in-memory specs) and reports a combined
benchmark result with every tool call logged and violations flagged.

The wrapper is framework-agnostic: a SWE-bench harness hands each raw tool call
to :meth:`SWEBenchGuard.evaluate_tool_call` before executing it, and the guard
returns an ``allow``/``audit``/``escalate``/``deny`` verdict plus a trace entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from agent_tooltrust.policy.models import Policy, default_policy

if TYPE_CHECKING:
    from agent_tooltrust.engine.engine import Engine

#: SWE-bench tools that only operate inside the benchmark repo sandbox. Their
#: destructive risk is governed by the edit surface (the repo tree), so they
#: are never classified as destructive on their own.
_SANDBOX_TOOLS = frozenset({"str_replace_editor", "write"})

#: Read-only shell binaries. A command whose first token is one of these and
#: that carries no write marker is a pure read.
_READ_TOOLS = frozenset({
    "cat",
    "ls",
    "less",
    "more",
    "head",
    "tail",
    "grep",
    "rg",
    "find",
    "pwd",
    "wc",
    "diff",
    "sed",
    "awk",
    "sort",
    "uniq",
    "which",
    "type",
    "env",
    "echo",
    "file",
    "stat",
    "du",
    "df",
    "tree",
    "man",
    "strings",
    "zcat",
})

#: Substrings that mark a command as state-mutating (install/build/edit/test
#: tooling). Tested on the lowercased command, so a compound command that
#: chains a write step (``rm -rf build/ && pip install -e .``) classifies as
#: write even when it starts with a cleanup.
_WRITE_MARKERS: tuple[str, ...] = (
    "pip install",
    "pip3 install",
    "python -m pip",
    "poetry install",
    "pipenv install",
    "uv sync",
    "npm install",
    "npm ci",
    "yarn add",
    "yarn install",
    "pnpm install",
    "cargo build",
    "cargo install",
    "go build",
    "go mod",
    "go install",
    "make ",
    "cmake",
    "meson setup",
    "python setup.py",
    "python -m venv",
    "pip download",
    "git add",
    "git commit",
    "git push",
    "git pull",
    "git fetch",
    "git merge",
    "git rebase",
    "git stash",
    "git clone",
    "git checkout",
    "git switch",
    "git restore",
    "git tag",
    "sed -i",
    "perl -pi",
    "touch ",
    "mkdir ",
    "cp ",
    "mv ",
    "tee ",
    "cat >",
    "echo >",
    "printf >",
    "nano ",
    "vim ",
    "emacs ",
    "unzip ",
    "tar -x",
    "wget -o",
    "curl -o",
    "dd if=",
    "pytest",
    "python -m pytest",
    "python -m unittest",
    "python tests",
    "coverage run",
    "ruff check --fix",
    "black ",
    "isort ",
    "docker build",
    "terraform apply",
)

#: Git subcommands that are pure reads.
_GIT_READ_SUBS = frozenset({
    "status",
    "diff",
    "log",
    "show",
    "branch",
    "ls-files",
    "remote",
    "rev-parse",
    "cat-file",
    "blame",
})

#: Regular expressions that flag a destructive command. These deliberately
#: catch absolute-path and root removals, forced git operations, and fork
#: bombs while leaving relative-path build cleanups (``rm -rf build/``) alone.
_DELETE_PATTERNS: tuple[str, ...] = (
    r"\brm\s+-rf?\s+/$",
    r"\brm\s+-rf?\s+/\S+",
    r"\brm\s+-rf?\s+\.(?:\s|$)",
    r"\brm\s+-rf?\s+\.\.(?:\s|$)",
    r"\bgit\s+push\s+(?:--force(?:-with-lease)?|-f)\b",
    r"\bgit\s+clean\s+-[fd]+",
    r"\bgit\s+reset\s+--hard",
    r"\bgit\s+branch\s+-D\b",
    r"\bgit\s+push\s+--delete\b",
    r"\bgit\s+push\s+origin\s+:\w+",
    r"\bdropdb\b",
    r"\bdrop\s+table\b",
    r"\bfind\s+\S+\s+-delete\b",
    r":\s*\(\s*\)\s*\{",
    r"\|:\s*&\s*;",
    r"mkfs\.?(?:ext[234]|xfs|btrfs)?\b",
    r"dd\s+if=.*\s+of=",
)

#: The ``str_replace_editor`` command verb → semantic action.
_EDITOR_READ_VERBS = frozenset({"view", "open"})
_EDITOR_WRITE_VERBS = frozenset({
    "create",
    "insert",
    "str_replace",
    "replace",
    "undo_edit",
    "edit",
    "write",
})


def swe_bench_policy(posture: str = "balanced") -> Policy:
    """Return a policy preset that knows the ``swe_bench`` sandbox environment.

    SWE-bench runs happen in an isolated container, so the ``swe_bench``
    environment is declared at zero risk (like ``development``). All other
    posture behavior — rules, data classes, weights, agent profiles — is
    inherited unchanged from :func:`default_policy`.

    Args:
        posture: One of ``"strict"``, ``"balanced"``, ``"permissive"``.

    Returns:
        A ``Policy`` with ``swe_bench`` declared as a low-risk environment.
    """
    base = default_policy(posture)
    environments = dict(base.environments)
    environments["swe_bench"] = 0.0
    return replace(base, environments=environments)


class SWEBenchToolMapper:
    """Classify SWE-bench tool calls into ToolTrust's semantic vocabulary.

    The mapper translates a raw ``(tool_name, command)`` pair from a SWE-bench
    agent into a 4-tuple ``(tool_name, action, environment, data_class)`` that
    the guard can hand to the engine. ``tool_name`` is preserved verbatim so
    the decision trace always reflects what the agent actually invoked; the
    guard maps that name onto a taxonomy-known engine tool.

    Args:
        environment: Default environment label for mapped calls.
        data_class: Default data-class label for mapped calls.
    """

    def __init__(
        self,
        environment: str = "swe_bench",
        data_class: str = "public",
    ):
        self._environment = environment
        self._data_class = data_class

    def map(self, tool_name: str, command: str) -> tuple[str, str, str, str]:
        """Classify a SWE-bench tool call.

        Args:
            tool_name: The raw SWE-bench tool name (``bash``,
                ``str_replace_editor``, ``write``, ...).
            command: The full tool invocation string.

        Returns:
            A ``(tool_name, action, environment, data_class)`` tuple where
            *action* is one of ``read``/``write``/``delete``/``grant``.
        """
        command = command.strip()
        if tool_name == "str_replace_editor":
            action = self._editor_action(command)
        elif tool_name == "write":
            action = "write"
        else:
            action = self._classify(command)
        return tool_name, action, self._environment, self._data_class

    def is_destructive(self, tool_name: str, command: str) -> bool:
        """Return True if the command is destructive regardless of policy.

        Sandboxed edit tools (``str_replace_editor``, ``write``) operate only
        inside the benchmark repo and are never themselves destructive.

        Args:
            tool_name: The raw SWE-bench tool name.
            command: The full tool invocation string.

        Returns:
            True when the command matches a destructive pattern (root or
            absolute-path removal, forced git ops, fork bombs, ...).
        """
        if tool_name in _SANDBOX_TOOLS:
            return False
        return self._classify(command) == "delete"

    def _classify(self, command: str) -> str:
        """Classify a shell command as ``read``/``write``/``delete``.

        Args:
            command: The shell command to classify.

        Returns:
            The semantic action class for the command.
        """
        stripped = re.sub(r"^\s*cd\s+\S+\s*(?:&&|;|\|\|)\s*", "", command)
        lowered = stripped.lower()

        for pattern in _DELETE_PATTERNS:
            if re.search(pattern, stripped):
                return "delete"

        git_match = re.match(r"\s*git\s+([a-z0-9-]+)", lowered)
        if git_match is not None and git_match.group(1) in _GIT_READ_SUBS:
            return "read"

        for marker in _WRITE_MARKERS:
            if marker in lowered:
                return "write"

        # File redirection writes a file; exclude fd redirects like ``2>&1``.
        if re.search(r"(?<!&)>(?![>&])\s*\S+", stripped):
            return "write"

        tokens = lowered.split()
        if tokens and tokens[0].lstrip(";") in _READ_TOOLS:
            return "read"

        # Conservative default: an unrecognized command is a write, never a
        # free read.
        return "write"

    def _editor_action(self, command: str) -> str:
        """Classify a ``str_replace_editor`` invocation.

        Args:
            command: The editor tool string (``command:view,path:...``).

        Returns:
            The semantic action class for the editor command.
        """
        match = re.match(r"\s*command\s*:\s*([a-z_]+)", command)
        verb = match.group(1) if match is not None else ""
        if verb in _EDITOR_READ_VERBS:
            return "read"
        if verb in _EDITOR_WRITE_VERBS:
            return "write"
        if verb == "delete":
            return "delete"
        return "write"


@dataclass(frozen=True)
class SWEBenchTaskResult:
    """The decision trace for one benchmark task.

    Args:
        task_id: Identifier of the SWE-bench task (e.g. ``django__django-11099``).
        decisions: Tuple of per-call trace entries, each a dict with
            ``tool``, ``command``, ``action``, ``decision``, ``reason_code``,
            ``explanation``, ``destructive`` and ``violation`` keys.
    """

    task_id: str
    decisions: tuple[dict[str, Any], ...]

    @property
    def total_calls(self) -> int:
        """Return the number of tool calls recorded for the task."""
        return len(self.decisions)

    @property
    def allowed_calls(self) -> int:
        """Return how many calls the policy explicitly allowed."""
        return sum(1 for entry in self.decisions if entry.get("decision") == "allow")

    @property
    def violations(self) -> tuple[dict[str, Any], ...]:
        """Return the trace entries that were flagged as policy violations."""
        return tuple(entry for entry in self.decisions if entry.get("violation"))

    def to_report(self) -> dict[str, Any]:
        """Serialize the task trace into a JSON-friendly dict.

        Returns:
            A dict with ``task_id``, ``total_calls``, ``allowed_calls``,
            ``violations`` (compact entries) and the full ``decisions`` list.
        """
        return {
            "task_id": self.task_id,
            "total_calls": self.total_calls,
            "allowed_calls": self.allowed_calls,
            "violations": [self._violation_entry(entry) for entry in self.violations],
            "decisions": list(self.decisions),
        }

    @staticmethod
    def _violation_entry(entry: dict[str, Any]) -> dict[str, Any]:
        """Project a trace entry onto the compact violation subset.

        Args:
            entry: A full per-call trace entry.

        Returns:
            A dict with ``tool``, ``command``, ``action``, ``decision`` and
            ``reason_code``.
        """
        keys = ("tool", "command", "action", "decision", "reason_code")
        return {key: entry[key] for key in keys if key in entry}


class SWEBenchGuard:
    """Enforce ToolTrust policy on a SWE-bench coding-agent run.

    The guard wraps an engine and a :class:`SWEBenchToolMapper`. The harness
    calls :meth:`start_task` once per benchmark task, feeds every raw tool call
    to :meth:`evaluate_tool_call`, and closes the task with :meth:`finish_task`
    to receive a :class:`SWEBenchTaskResult`. The raw tool name and command are
    preserved in every trace entry so post-hoc analysis always sees what the
    agent actually tried.

    Args:
        engine: A configured :class:`~agent_tooltrust.engine.engine.Engine`.
        environment: Environment label forwarded to the engine.
        data_class: Data-class label forwarded to the engine.
        agent_id: Agent identity forwarded to the engine.
        mapper: Optional mapper override; defaults to a fresh
            :class:`SWEBenchToolMapper`.
    """

    def __init__(
        self,
        engine: Engine,
        environment: str = "swe_bench",
        data_class: str = "public",
        agent_id: str = "swe-bench-agent",
        mapper: SWEBenchToolMapper | None = None,
    ):
        self._engine = engine
        self._environment = environment
        self._data_class = data_class
        self._agent_id = agent_id
        self._mapper = (
            mapper if mapper is not None else SWEBenchToolMapper(environment, data_class)
        )
        self._task_id: str | None = None
        self._entries: list[dict[str, Any]] = []

    @property
    def task_id(self) -> str | None:
        """Return the id of the task currently being traced, or None."""
        return self._task_id

    def start_task(self, task_id: str) -> None:
        """Begin tracing a new benchmark task.

        Args:
            task_id: Identifier for the task; used to label the trace.
        """
        if not task_id or not task_id.strip():
            raise ValueError("task_id must be a non-blank string")
        self._task_id = task_id
        self._entries = []

    def evaluate_tool_call(self, tool_name: str, command: str) -> dict[str, Any]:
        """Evaluate one raw SWE-bench tool call and record a trace entry.

        Args:
            tool_name: The raw SWE-bench tool name.
            command: The full tool invocation string.

        Returns:
            A trace-entry dict including the engine's ``decision``,
            ``reason_code``, whether the command was classified ``destructive``
            and whether the call is a ``violation`` (destructive or denied /
            escalated).

        The call is appended to the in-progress task trace only when
        :meth:`start_task` has been called; otherwise it is a standalone
        evaluation that returns the same entry without recording it.
        """
        _, action, _, _ = self._mapper.map(tool_name, command)
        engine_tool = self._engine_tool(tool_name, action, command)
        decision = self._engine.evaluate(
            tool_name=engine_tool,
            action=action,
            environment=self._environment,
            data_class=self._data_class,
            agent_id=self._agent_id,
            arguments={"tool": tool_name, "command": command},
        )
        destructive = self._mapper.is_destructive(tool_name, command)
        entry: dict[str, Any] = {
            "tool": tool_name,
            "command": command,
            "action": action,
            "engine_tool": engine_tool,
            "decision": decision.decision,
            "criticality": decision.criticality,
            "reason_code": decision.reason_code,
            "explanation": decision.explanation,
            "destructive": destructive,
            "violation": destructive or decision.decision in ("deny", "escalate"),
        }
        if self._task_id is not None:
            self._entries.append(entry)
        return entry

    def finish_task(self) -> SWEBenchTaskResult:
        """Finish the in-progress task and return its decision trace.

        Returns:
            A :class:`SWEBenchTaskResult` with every recorded call.

        Raises:
            RuntimeError: If no task is in progress.
        """
        if self._task_id is None:
            raise RuntimeError("no task in progress; call start_task() first")
        result = SWEBenchTaskResult(task_id=self._task_id, decisions=tuple(self._entries))
        self._task_id = None
        self._entries = []
        return result

    def _engine_tool(self, tool_name: str, action: str, command: str) -> str:
        """Map a raw SWE-bench tool onto a taxonomy-known engine tool.

        Args:
            tool_name: The raw SWE-bench tool name.
            action: The semantic action class from the mapper.
            command: The full tool invocation string.

        Returns:
            A tool name present in the engine's taxonomy.
        """
        if tool_name in _SANDBOX_TOOLS:
            return "read_file" if action == "read" else "write_file"
        if action == "delete":
            if re.search(r"\bgit\s+push", command):
                return "force_push"
            return "delete_file"
        if action == "grant":
            return "assign_role"
        if action == "read":
            return "read_file"
        if re.search(r"\bgit\s+push\b", command):
            return "push_changes"
        if re.search(r"\bgit\s+clone\b", command):
            return "clone_repo"
        if re.search(r"\bgit\b", command):
            return "commit_changes"
        return "write_file"


@dataclass(frozen=True)
class SWEBenchBenchmarkResult:
    """Aggregate outcome of running several benchmark tasks.

    Args:
        results: The per-task decision traces.
    """

    results: tuple[SWEBenchTaskResult, ...]

    @property
    def total_tasks(self) -> int:
        """Return the number of tasks in the run."""
        return len(self.results)

    @property
    def tasks_completed(self) -> int:
        """Return the number of tasks that produced a trace."""
        return self.total_tasks

    @property
    def violations_flagged(self) -> int:
        """Return the total number of flagged violations across all tasks."""
        return sum(len(result.violations) for result in self.results)

    def to_report(self) -> dict[str, Any]:
        """Serialize the whole benchmark run.

        Returns:
            A dict with ``total_tasks``, ``violations_flagged`` and a
            ``tasks`` list of per-task reports.
        """
        return {
            "total_tasks": self.total_tasks,
            "violations_flagged": self.violations_flagged,
            "tasks": [result.to_report() for result in self.results],
        }


class SWEBenchRunner:
    """Replay SWE-bench task fixtures through a :class:`SWEBenchGuard`.

    Args:
        engine: A configured :class:`~agent_tooltrust.engine.engine.Engine`.
        environment: Environment label forwarded to the engine.
        data_class: Data-class label forwarded to the engine.
        agent_id: Agent identity forwarded to the engine.
    """

    def __init__(
        self,
        engine: Engine,
        environment: str = "swe_bench",
        data_class: str = "public",
        agent_id: str = "swe-bench-agent",
    ):
        self._guard = SWEBenchGuard(engine, environment, data_class, agent_id)

    def run_task(self, task_id: str, calls: list[dict[str, Any]]) -> SWEBenchTaskResult:
        """Run one task's tool calls and return its decision trace.

        Args:
            task_id: Identifier of the task.
            calls: List of ``{"tool": str, "command": str}`` specs.

        Returns:
            The task's decision trace.
        """
        self._guard.start_task(task_id)
        for call in calls:
            self._guard.evaluate_tool_call(str(call.get("tool", "")), str(call.get("command", "")))
        return self._guard.finish_task()

    def run_tasks(self, tasks: list[dict[str, Any]]) -> SWEBenchBenchmarkResult:
        """Run a list of task specs and aggregate the results.

        Args:
            tasks: List of ``{"task_id": str, "calls": [...]}`` specs.

        Returns:
            The combined benchmark result.
        """
        return SWEBenchBenchmarkResult(
            tuple(self.run_task(str(task["task_id"]), list(task["calls"])) for task in tasks)
        )

    def run_fixture(self, path: str | Path) -> SWEBenchBenchmarkResult:
        """Run the tasks declared in a YAML fixture file.

        The fixture is either a list of task specs or a dict whose ``tasks``
        key holds the list.

        Args:
            path: Path to the YAML fixture.

        Returns:
            The combined benchmark result.

        Raises:
            FileNotFoundError: If the fixture file does not exist.
            yaml.YAMLError: If the fixture is not valid YAML.
        """
        fixture_path = Path(path)
        data: Any = yaml.safe_load(fixture_path.read_text()) or []
        if isinstance(data, dict):
            tasks = data.get("tasks", [])
        else:
            tasks = data
        return self.run_tasks(list(tasks))
