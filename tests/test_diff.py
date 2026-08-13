"""Tests for M2.5 — ``tooltrust diff`` CLI (#5, F-65).

``tooltrust diff`` compares a loaded policy against its posture default and
prints any differences (kept defaults are omitted). Exits 0 when the policy
matches the default, 1 when there are overrides or gaps.
"""

from pathlib import Path

from agent_tooltrust.cli import main


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "tooltrust.yaml"
    path.write_text(text)
    return path


class TestDiffCli:
    def test_identical_policy_exits_zero(self, tmp_path):
        out = write(tmp_path, 'version: "1.0.0"\nposture: balanced\n')
        rc = main(["diff", str(out)])
        assert rc == 0

    def test_overridden_environment_exits_one(self, tmp_path, capsys):
        out = write(
            tmp_path,
            'version: "2.0.0"\nposture: balanced\n'
            "environments:\n  production: {criticality: 0.95}\n",
        )
        rc = main(["diff", str(out)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "0.7 -> 0.95" in captured.out

    def test_missing_file_exits_one(self, capsys):
        rc = main(["diff", "/nope/x.yaml"])
        captured = capsys.readouterr()
        assert rc == 1
        assert "cannot load policy:" in captured.err

    def test_posture_flag_overrides_default(self, tmp_path):
        out = write(tmp_path, 'version: "1.0.0"\nposture: strict\n')
        rc = main(["diff", str(out), "--posture", "strict"])
        assert rc == 0

    def test_overridden_data_class_exits_one(self, tmp_path, capsys):
        out = write(
            tmp_path,
            'version: "2.0.0"\nposture: balanced\ndata_classes:\n  public: {sensitivity: 0.1}\n',
        )
        rc = main(["diff", str(out)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "0.0 -> 0.1" in captured.out

    def test_uses_policy_posture_when_no_flag(self, tmp_path):
        out = write(tmp_path, 'version: "1.0.0"\nposture: permissive\n')
        rc = main(["diff", str(out)])
        assert rc == 0
