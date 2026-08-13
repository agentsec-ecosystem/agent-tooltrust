"""Tests for M2.7 — policy hot-reload (#7, F-60).

``watch()`` monitors a policy file for changes and calls a callback with the
freshly loaded :class:`Policy`. Tests verify the initial load fires the
callback, missing file raises, and file changes trigger a reload.
"""

import threading
from pathlib import Path

import pytest

from agent_tooltrust.policy.watcher import watch


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "tooltrust.yaml"
    path.write_text(text)
    return path


class TestWatcher:
    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            watch("/nope/tooltrust.yaml", callback=lambda p: None)

    def test_initial_load_calls_callback(self, tmp_path):
        out = write(tmp_path, 'version: "1.0.0"\n')
        received = []

        def cb(policy):
            received.append(policy)

        thread = threading.Thread(target=watch, args=(out, cb), daemon=True)
        thread.start()
        thread.join(timeout=2)
        assert len(received) >= 1
        assert received[0].version == "1.0.0"

    def test_reload_after_file_change(self, tmp_path):
        out = write(tmp_path, 'version: "1.0.0"\n')
        received = []

        def cb(policy):
            received.append(policy)
            if len(received) >= 2:
                raise StopIteration  # signal done

        thread = threading.Thread(target=watch, args=(out, cb), daemon=True)
        thread.start()

        import time

        time.sleep(0.5)
        out.write_text('version: "2.0.0"\n')
        time.sleep(1)

        assert len(received) >= 2
        assert received[0].version == "1.0.0"
        assert received[-1].version == "2.0.0"
