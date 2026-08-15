"""Tests for M2 Task 3 (#106, F-87) — dispatcher parser.

Raw ``bash``/``git``/``http``/``aws`` command strings are parsed into a
canonical ``(tool, action, args)`` triple and evaluated against the *same*
policy, so a smuged ``git push --force`` is denied when the policy denies a
forced push. Unparseable input fails closed to a deny.
"""

from __future__ import annotations

import pytest

from agent_tooltrust.engine.dispatcher import (
    DispatcherError,
    ParsedCall,
    dispatch,
    parse_aws,
    parse_bash,
    parse_git,
    parse_http,
)
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.errors import DENY_UNPARSEABLE_INPUT
from agent_tooltrust.policy.models import Policy, Rule, default_policy


def _git_denying_policy() -> Policy:
    base = default_policy("balanced")
    return Policy(
        version=base.version,
        posture=base.posture,
        environments=base.environments,
        data_classes=base.data_classes,
        risk_weights=base.risk_weights,
        rules=(
            Rule(
                decision="deny",
                tool="git_push",
                action="force_push",
                reason="force push blocked",
            ),
        ),
        agents=base.agents,
    )


class TestParseBash:
    def test_git_push_maps_to_push(self):
        parsed = parse_bash("git push origin main")
        assert parsed.tool == "git_push"
        assert parsed.action == "push"

    def test_git_push_force_maps_to_force_push(self):
        parsed = parse_bash("git push --force origin main")
        assert parsed.tool == "git_push"
        assert parsed.action == "force_push"

    def test_git_push_short_f_maps_to_force_push(self):
        parsed = parse_bash("git push -f origin main")
        assert parsed.action == "force_push"

    def test_git_pull_maps_to_pull(self):
        parsed = parse_bash("git pull origin main")
        assert parsed.tool == "git_pull"
        assert parsed.action == "pull"

    def test_git_status_maps_to_status(self):
        parsed = parse_bash("git status")
        assert parsed.tool == "git_status"
        assert parsed.action == "status"

    def test_generic_command_maps_to_execute_shell(self):
        parsed = parse_bash("ls -la")
        assert parsed.tool == "execute_shell"
        assert parsed.action == "exec"

    def test_empty_command_raises(self):
        with pytest.raises(DispatcherError):
            parse_bash("   ")

    def test_bad_quoting_raises(self):
        with pytest.raises(DispatcherError):
            parse_bash("echo 'unclosed")

    def test_parsed_call_carries_args_and_raw(self):
        parsed = parse_bash("git push -f origin main")
        assert parsed.raw == "git push -f origin main"
        assert "args" in parsed.args


class TestParseGit:
    def test_plain_git_command_without_binary(self):
        parsed = parse_git("push origin main")
        assert parsed.tool == "git_push"
        assert parsed.action == "push"

    def test_git_force_push(self):
        parsed = parse_git("git push --force-with-lease origin main")
        assert parsed.action == "force_push"

    def test_unsupported_verb_raises(self):
        with pytest.raises(DispatcherError):
            parse_git("rebase --interactive")


class TestParseHttp:
    def test_capital_method(self):
        parsed = parse_http("GET /api/users")
        assert parsed.tool == "http_get"
        assert parsed.action == "get"

    def test_lowercase_method(self):
        parsed = parse_http("delete /api/account")
        assert parsed.tool == "http_delete"
        assert parsed.action == "delete"

    def test_curl_method_flag(self):
        parsed = parse_http("curl -X POST https://example.com/api")
        assert parsed.tool == "http_post"
        assert parsed.action == "post"

    def test_bare_url_is_get(self):
        parsed = parse_http("https://example.com")
        assert parsed.tool == "http_get"
        assert parsed.action == "get"

    def test_unknown_verb_raises(self):
        with pytest.raises(DispatcherError):
            parse_http("RANDOM /path")


class TestParseAws:
    def test_s3_copy_is_write(self):
        parsed = parse_aws("aws s3 cp file.txt s3://bucket/file.txt")
        assert parsed.action == "write"
        assert parsed.args["service"] == "s3"

    def test_s3_put_object_is_write(self):
        parsed = parse_aws("aws s3 create-bucket --bucket new-bucket")
        assert parsed.action == "write"

    def test_s3_delete_is_delete(self):
        parsed = parse_aws("aws s3api delete-bucket --bucket old-bucket")
        assert parsed.action == "delete"

    def test_ec2_terminate_is_delete(self):
        parsed = parse_aws("aws ec2 terminate-instances --instance-ids i-1234")
        assert parsed.action == "delete"

    def test_ec2_describe_is_read(self):
        parsed = parse_aws("aws ec2 describe-instances")
        assert parsed.action == "read"

    def test_missing_service_raises(self):
        with pytest.raises(DispatcherError):
            parse_aws("aws onlyonearg")


class TestDispatch:
    def test_force_push_denied_when_git_push_denied(self):
        engine = Engine(_git_denying_policy())
        decision = dispatch(
            "git push --force origin main",
            kind="bash",
            environment="staging",
            data_class="internal",
            agent_id="dev-eng",
            engine=engine,
        )
        assert decision.decision == "deny"
        assert decision.reason_code == "deny_critical_op"

    def test_plain_push_not_denied(self):
        engine = Engine(_git_denying_policy())
        decision = dispatch(
            "git push origin main",
            kind="bash",
            environment="staging",
            data_class="internal",
            agent_id="dev-eng",
            engine=engine,
        )
        assert decision.decision == "allow"

    def test_unparseable_input_fails_closed(self):
        engine = Engine(default_policy("balanced"))
        decision = dispatch(
            "echo 'unclosed quote",
            kind="bash",
            environment="staging",
            data_class="internal",
            agent_id="dev-eng",
            engine=engine,
        )
        assert decision.decision == "deny"
        assert decision.reason_code == DENY_UNPARSEABLE_INPUT

    def test_unsupported_kind_fails_closed(self):
        engine = Engine(default_policy("balanced"))
        decision = dispatch(
            "foo",
            kind="weird",
            environment="staging",
            data_class="internal",
            agent_id="dev-eng",
            engine=engine,
        )
        assert decision.decision == "deny"
        assert decision.reason_code == DENY_UNPARSEABLE_INPUT

    def test_dispatch_requires_engine(self):
        with pytest.raises(TypeError):
            dispatch(
                "git status",
                kind="bash",
                environment="staging",
                data_class="internal",
                agent_id="dev-eng",
                engine="not-an-engine",
            )


def test_parsed_call_is_dataclass():
    parsed = ParsedCall(tool="git_push", action="push", raw="git push x")
    assert parsed.tool == "git_push"
    assert parsed.action == "push"
