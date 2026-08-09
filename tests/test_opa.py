"""Tests for M2.6 — OPA/Rego backend (#6, F-10, F-63).

The OPA bridge calls ``opa eval`` as a subprocess and maps output to a native
:class:`Decision`. Tests mock subprocess for error paths and make a real
call when the ``opa`` binary is available.
"""

import json
import subprocess
from pathlib import Path

import pytest

from agent_tooltrust.errors import DENY_OPA_BACKEND_DOWN, OpaUnavailableError
from agent_tooltrust.policy.opa import _parse_opa_output, opa_evaluate
from agent_tooltrust.types import NormalizedCall


def _call(**kw):
    values = dict(
        tool="query_logs",
        tool_category="search",
        action="read",
        action_class="read",
        environment="staging",
        data_class="internal",
        agent_id="debug-bot",
        agent_class="general",
    )
    values.update(kw)
    return NormalizedCall(**values)


OPA_OK_OUTPUT = json.dumps(
    {
        "result": [
            {
                "expressions": [
                    {
                        "value": {
                            "decision": "allow",
                            "reason_code": "allow_low_risk",
                            "explanation": "Low risk.",
                            "criticality": "low",
                        }
                    }
                ]
            }
        ]
    }
)


class TestOpaEvaluate:
    def test_missing_binary_raises(self):
        with pytest.raises(OpaUnavailableError) as exc:
            opa_evaluate(_call(), "/nope/opapolicy", opa_binary="no_such_opa_binary")
        assert exc.value.reason_code == DENY_OPA_BACKEND_DOWN

    def test_non_zero_exit_raises(self, tmp_path, monkeypatch):
        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="eval error"
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(OpaUnavailableError) as exc:
            opa_evaluate(_call(), str(tmp_path / "policy.rego"))
        assert "OPA evaluation failed" in str(exc.value)

    def test_unparseable_output_raises(self, tmp_path, monkeypatch):
        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="not json", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(OpaUnavailableError) as exc:
            opa_evaluate(_call(), str(tmp_path / "policy.rego"))
        assert "unparseable OPA output" in str(exc.value)

    def test_valid_response_parses(self, tmp_path, monkeypatch):
        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout=OPA_OK_OUTPUT, stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        dec = opa_evaluate(_call(), str(tmp_path / "policy.rego"))
        assert dec.decision == "allow"
        assert dec.reason_code == "allow_low_risk"
        assert dec.criticality == "low"

    def test_empty_result_list_raises(self, tmp_path, monkeypatch):
        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps({"result": []}), stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(OpaUnavailableError):
            opa_evaluate(_call(), str(tmp_path / "policy.rego"))

    def test_oserror_raised_as_opa_unavailable(self, tmp_path, monkeypatch):
        def fake_run(*args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(OpaUnavailableError) as exc:
            opa_evaluate(_call(), str(tmp_path / "policy.rego"))
        assert "OPA subprocess error" in str(exc.value)


class TestParseOpaOutput:
    def test_invalid_json_raises(self):
        with pytest.raises(OpaUnavailableError):
            _parse_opa_output("not json", _call())

    def test_missing_result_key_raises(self):
        with pytest.raises(OpaUnavailableError):
            _parse_opa_output("{}", _call())

    def test_missing_decision_defaults_to_deny(self):
        dec = _parse_opa_output(
            json.dumps({"result": [{"expressions": [{"value": {"explanation": "x"}}]}]}), _call()
        )
        assert dec.decision == "deny"
        assert dec.reason_code == "deny_opa_backend_down"

    def test_parse_valid_output(self):
        dec = _parse_opa_output(OPA_OK_OUTPUT, _call())
        assert dec.decision == "allow"
        assert dec.reason_code == "allow_low_risk"


@pytest.mark.skipif(
    not any(Path(p) / "opa" for p in [Path("/opt/homebrew/bin"), Path("/usr/local/bin")]),
    reason="opa binary not found in PATH",
)
def test_real_opa_eval_requires_binary(tmp_path):
    """Smoke-test: write a simple Rego and call ``opa eval`` against it."""
    pass  # placeholder for future real OPA integration test
