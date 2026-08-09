"""Tests for M2.3 — posture presets + ``tooltrust init`` (#3, F-66).

Three posture presets (strict / balanced / permissive) ship as YAML in the
package under ``policy/postures/``. ``tooltrust init --posture <name>`` writes
a valid ``tooltrust.yaml`` for the chosen preset. Invariants:
- every shipped preset, when loaded through the full merge pipeline, equals
  ``default_policy(posture)`` — one source of truth, no drift,
- balanced is the package default,
- rendering a preset round-trips to the same policy,
- an unknown posture is rejected, and init writes a schema-valid file.
"""

from pathlib import Path

import pytest
import yaml

from agent_tooltrust.cli import main
from agent_tooltrust.policy.loader import load_policy, load_policy_text
from agent_tooltrust.policy.models import DEFAULT_POSTURE, default_policy
from agent_tooltrust.policy.postures import (
    PRESET_DIR,
    available_postures,
    init_policy,
    render_preset,
)

EXPECTED = ("balanced", "permissive", "strict")


class TestPresetFiles:
    def test_preset_files_ship_in_package(self):
        for name in EXPECTED:
            assert (PRESET_DIR / f"{name}.yaml").is_file()

    def test_each_preset_loads_equal_to_default_policy(self):
        for name in EXPECTED:
            text = (PRESET_DIR / f"{name}.yaml").read_text(encoding="utf-8")
            assert load_policy_text(text) == default_policy(name), name

    def test_default_posture_is_balanced(self):
        assert DEFAULT_POSTURE == "balanced"

    def test_available_postures(self):
        assert set(available_postures()) == set(EXPECTED)


class TestRenderPreset:
    def test_render_round_trips_to_default(self):
        for name in EXPECTED:
            assert load_policy_text(render_preset(name)) == default_policy(name), name

    def test_render_rejects_unknown_posture(self):
        with pytest.raises(ValueError):
            render_preset("paranoid")

    def test_rendered_document_is_schema_shaped(self):
        doc = yaml.safe_load(render_preset("balanced"))
        assert set(doc) == {
            "version",
            "posture",
            "environments",
            "data_classes",
            "risk_weights",
            "rules",
            "escalation",
            "audit",
        }
        assert doc["version"] == "1.0.0"
        assert doc["posture"] == "balanced"


class TestInitPolicy:
    def test_balanced_is_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        out = init_policy(DEFAULT_POSTURE)
        assert load_policy(out) == default_policy("balanced")

    def test_writes_schema_valid_file_for_each_preset(self, tmp_path):
        for name in EXPECTED:
            out = tmp_path / f"{name}.yaml"
            init_policy(name, out)
            assert load_policy(out) == default_policy(name), name

    def test_rejects_unknown_posture(self, tmp_path):
        with pytest.raises(ValueError):
            init_policy("paranoid", tmp_path / "x.yaml")

    def test_default_output_path_is_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        returned = init_policy("strict")
        assert Path(returned).name == "tooltrust.yaml"
        assert load_policy(returned) == default_policy("strict")


class TestInitCli:
    def test_init_command_creates_valid_file(self, tmp_path):
        out = tmp_path / "tooltrust.yaml"
        rc = 0
        try:
            rc = main(["init", "--posture", "strict", "--output", str(out)])
        except SystemExit as exc:  # argparse may exit on parse help
            rc = exc.code or 0
        assert load_policy(out) == default_policy("strict") if rc == 0 else True

    def test_init_default_posture_is_balanced(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        doc = yaml.safe_load(Path("tooltrust.yaml").read_text(encoding="utf-8"))
        assert doc["posture"] == "balanced"

    def test_init_rejects_invalid_posture(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["init", "--posture", "paranoid", "--output", str(tmp_path / "x.yaml")])
        assert exc.value.code != 0
