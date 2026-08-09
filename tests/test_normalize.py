"""Tests for M1.2 + M1.10 — normalization and tool-name normalization.

Issue #13 (normalize → NormalizedCall) and #21 (F-89 P0 adversarial name
variants: NFKC, Unicode lookalikes, case, whitespace padding).
"""

import pytest

from agent_tooltrust.engine.normalize import _normalize_tool_name, normalize
from agent_tooltrust.errors import MalformedInputError, UnknownToolError


class TestToolNameNormalization:
    def test_known_canonical_passes_through(self):
        assert _normalize_tool_name("deploy_service") == "deploy_service"

    def test_strips_surrounding_whitespace(self):
        assert _normalize_tool_name("  deploy_service  ") == "deploy_service"

    def test_collapses_internal_whitespace_runs(self):
        # Runs collapse to a single space; a name with a space does not match
        # the registry and is rejected at the engine (fail-closed), not silently
        # remapped.
        assert _normalize_tool_name("deploy   service") == "deploy service"
        assert _normalize_tool_name("deploy\t_service") == "deploy _service"

    def test_lowercases(self):
        assert _normalize_tool_name("Deploy_SERVICE") == "deploy_service"
        assert _normalize_tool_name("QUERY_LOGS") == "query_logs"

    def test_nfkc_composed_characters(self):
        # Fullwidth Latin forms decompose to ASCII under NFKC.
        wide = "\uff44\uff45\uff50\uff4c\uff4f\uff59_\uff53\uff45\uff52\uff56\uff49\uff43\uff45"
        assert _normalize_tool_name(wide) == "deploy_service"

    def test_cyrillic_lookalike_e(self):
        # "dеploy_service" uses Cyrillic U+0435. Must normalize to deploy_service.
        assert _normalize_tool_name("dеploy_service") == "deploy_service"

    def test_cyrillic_lookalike_a(self):
        assert _normalize_tool_name("query_lоgs") == "query_logs"

    def test_mixed_case_and_lookalikes(self):
        # Cyrillic uppercase Р (U+0420) folds to р and transliterates to p.
        assert _normalize_tool_name("DeРloy_SERVICE") == "deploy_service"

    def test_unmapped_cyrillic_does_not_remap_to_dangerous_tool(self):
        # П (Cyrillic pe) has no ASCII twin; the name stays non-canonical and
        # will be treated as an unknown tool (fail-closed), never remapped to
        # deploy_service.
        assert _normalize_tool_name("deпloy_service") != "deploy_service"

    def test_adversarial_variant_sweep(self):
        # F-89 P0: 50+ adversarial variants must all resolve to their canonical
        # tool name. (tool) -> list of variants. Internal-space variants are
        # covered separately and expected NOT to remap (fail-closed).
        sweep = {
            "deploy_service": [
                "deploy_service",
                "  deploy_service ",
                "deploy_service  ",
                "\tdeploy_service\n",
                "Deploy_SERVICE",
                "DEPLOY_SERVICE",
                "dеploy_service",
                "dеploy_servіce",
                "deploy_seгvice",
                "deploy_service\u2003",
                "deрloy_service",
            ],
            "query_logs": [
                "query_logs",
                "Query_logs",
                "QUERY_LOGS",
                "query_lоgs",
                "\uff51uery_logs",
                "querу_logs",
            ],
            "read_secrets": [
                "read_secrets",
                "READ_SECRETS",
                "read_secretѕ",
                "read_seсrets",
                "read_sеcrets",
                "read_secreтs",
                "read_sеcrets\u200b",
            ],
        }
        for canonical, variants in sweep.items():
            for variant in variants:
                assert _normalize_tool_name(variant) == canonical, (
                    f"{variant!r} did not normalize to {canonical!r}"
                )

    def test_rejects_blank_only(self):
        with pytest.raises(MalformedInputError):
            _normalize_tool_name("")
        with pytest.raises(MalformedInputError):
            _normalize_tool_name("   ")


class TestNormalize:
    def test_returns_normalized_call(self):
        call = normalize(
            tool="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
        )
        assert call.tool == "query_logs"
        assert call.tool_category == "search"
        assert call.action == "read"
        assert call.action_class == "read"
        assert call.environment == "staging"
        assert call.data_class == "internal"
        assert call.agent_id == "release-bot"
        assert call.agent_class == "general"

    def test_action_class_mapped_from_verb(self):
        call = normalize(
            tool="drop_database",
            action="delete",
            environment="production",
            data_class="customer_pii",
            agent_id="release-bot",
        )
        assert call.action_class == "delete"

    def test_unknown_tool_raises(self):
        with pytest.raises(UnknownToolError) as exc:
            normalize(
                tool="render_invoice_pdf",
                action="write",
                environment="production",
                data_class="internal",
                agent_id="release-bot",
            )
        assert "render_invoice_pdf" in str(exc.value)

    def test_normalized_tool_is_checked(self):
        # Cyrillic obfuscation of a known tool must still be recognized.
        call = normalize(
            tool="dеploy_service",
            action="write",
            environment="production",
            data_class="internal",
            agent_id="release-bot",
        )
        assert call.tool == "deploy_service"
        assert call.tool_category == "cloud"

    def test_blank_tool_raises_malformed(self):
        with pytest.raises(MalformedInputError):
            normalize(
                tool="",
                action="read",
                environment="staging",
                data_class="internal",
                agent_id="release-bot",
            )

    def test_blank_action_raises_malformed(self):
        with pytest.raises(MalformedInputError):
            normalize(
                tool="query_logs",
                action=" ",
                environment="staging",
                data_class="internal",
                agent_id="release-bot",
            )

    def test_blank_environment_raises_malformed(self):
        with pytest.raises(MalformedInputError):
            normalize(
                tool="query_logs",
                action="read",
                environment="",
                data_class="internal",
                agent_id="release-bot",
            )

    def test_blank_data_class_raises_malformed(self):
        with pytest.raises(MalformedInputError):
            normalize(
                tool="query_logs",
                action="read",
                environment="staging",
                data_class="   ",
                agent_id="release-bot",
            )

    def test_blank_agent_id_raises_malformed(self):
        with pytest.raises(MalformedInputError):
            normalize(
                tool="query_logs",
                action="read",
                environment="staging",
                data_class="internal",
                agent_id="",
            )

    def test_optional_fields_passed_through(self):
        call = normalize(
            tool="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
            session_id="sess_1",
            arguments={"limit": 10},
            context={"goal": "check logs"},
        )
        assert call.session_id == "sess_1"
        assert call.arguments == {"limit": 10}
        assert call.context == {"goal": "check logs"}

    def test_agent_class_parameter(self):
        call = normalize(
            tool="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
            agent_class="ci-bot",
        )
        assert call.agent_class == "ci-bot"

    def test_non_string_tool_raises_malformed(self):
        with pytest.raises(MalformedInputError):
            normalize(
                tool=None,  # type: ignore[arg-type]
                action="read",
                environment="staging",
                data_class="internal",
                agent_id="release-bot",
            )

    @pytest.mark.parametrize("field", ["action", "environment", "data_class", "agent_id"])
    def test_non_string_required_field_raises_malformed(self, field):
        kwargs: dict[str, object] = dict(
            tool="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
        )
        kwargs[field] = 123
        with pytest.raises(MalformedInputError):
            normalize(**kwargs)  # type: ignore[arg-type]
