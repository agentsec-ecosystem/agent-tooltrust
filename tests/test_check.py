"""Tests for M2.4 — ``tooltrust check`` CLI (#4, F-67).

``tooltrust check`` reads a policy file and validates it against the schema.
A clean file exits 0 and prints the version/posture; a broken one exits 1
with the first error and its line/column location.
"""

from pathlib import Path

from agent_tooltrust.cli import main


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "tooltrust.yaml"
    path.write_text(text)
    return path


class TestCheckCli:
    def test_clean_policy_exits_zero(self, tmp_path):
        out = write(tmp_path, 'version: "1.0.0"')
        assert main(["check", str(out)]) == 0

    def test_missing_file_exits_one(self):
        assert main(["check", "/nope/x.yaml"]) == 1

    def test_bad_yaml_exits_one_with_error(self, tmp_path, capsys):
        out = write(tmp_path, "version: [1, 2\n")
        rc = main(["check", str(out)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "invalid policy:" in captured.err

    def test_schema_violation_exits_one(self, tmp_path, capsys):
        out = write(tmp_path, 'version: "1.0.0"\nposture: paranoid\n')
        rc = main(["check", str(out)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "invalid policy:" in captured.err

    def test_default_path_checks_cwd(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        rc = main(["check"])
        captured = capsys.readouterr()
        assert rc == 1
        assert "invalid policy:" in captured.err or "no such" in captured.err
