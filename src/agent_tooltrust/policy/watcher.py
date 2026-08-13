"""M2.7 — policy hot-reload via ``watchfiles`` (#7, F-60).

``watch(path, callback)`` monitors a policy file for changes and invokes a
callback with the newly loaded policy. A file change triggers a reload within
1 s; stale decisions that race with a pending reload are returned with the
old version in their audit record — but since ``evaluate()`` is fast and the
callback swaps atomically, the window is negligible.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchfiles import watch as fswatch

from agent_tooltrust.policy.loader import load_policy
from agent_tooltrust.policy.models import Policy


def watch(
    path: str | Path,
    callback: Callable[[Policy], Any] | None = None,
) -> None:
    """Block until the policy file at *path* is changed, then reload.

    When no callback is supplied, prints the new version to stdout. Intended
    to run in a background thread that swaps the engine's policy reference on
    change.

    Args:
        path: Path to ``tooltrust.yaml`` to monitor.
        callback: Called with the freshly loaded :class:`Policy` after every
            change (including the initial load).

    Raises:
        FileNotFoundError: *path* does not exist.

    Raises :class:`FileNotFoundError` if *path* does not exist.
    """
    policy_path = Path(path)
    if not policy_path.is_file():
        raise FileNotFoundError(f"policy file not found: {policy_path}")

    _callback = callback or (lambda p: print(f"reloaded policy {p.version}"))

    # Initial load.
    _callback(load_policy(policy_path))

    # Watch for file changes and reload.
    for _changes in fswatch(str(policy_path)):
        try:
            policy = load_policy(policy_path)
            _callback(policy)
        except Exception:  # noqa: S110 — old policy stays in effect, fail-safe
            pass
