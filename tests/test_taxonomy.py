"""Tests for M1.1 — the 13-domain taxonomy module.

Issue #12. Domains, verbs, baseline risk weights, known-tool resolution,
and verb → action-class mapping.
"""

from agent_tooltrust.taxonomy import (
    ACTION_CLASSES,
    DOMAIN_BASELINE,
    DOMAIN_VERBS,
    DOMAINS,
    KNOWN_TOOLS,
    action_class_for,
    domain_for,
    is_known_tool,
    taxonomy_summary,
)


class TestTaxonomySurface:
    def test_has_exactly_13_domains(self):
        assert set(DOMAINS) == {
            "fs",
            "shell",
            "http",
            "db",
            "git",
            "email",
            "cloud",
            "secrets",
            "iam",
            "payment",
            "approval",
            "search",
            "notify",
        }

    def test_every_domain_has_verbs(self):
        for domain in DOMAINS:
            assert DOMAIN_VERBS[domain], f"{domain} has no verbs"

    def test_every_domain_has_baseline_in_range(self):
        for domain in DOMAINS:
            baseline = DOMAIN_BASELINE[domain]
            assert 0.0 <= baseline <= 1.0, f"{domain} baseline out of range"

    def test_summary_reports_verb_counts(self):
        summary = taxonomy_summary()
        assert "13" in summary or len(DOMAINS) == 13
        for domain in DOMAINS:
            assert domain in summary

    def test_verb_counts_are_accurate(self):
        for domain, verbs in DOMAIN_VERBS.items():
            assert f"{domain}: {len(verbs)}" in taxonomy_summary()

    def test_known_tools_maps_into_valid_domains(self):
        for tool, domain in KNOWN_TOOLS.items():
            assert domain in DOMAINS, f"{tool} -> unknown domain {domain}"


class TestDomainResolution:
    def test_domain_for_known_tool(self):
        assert domain_for("query_logs") == "search"
        assert domain_for("read_secrets") == "secrets"
        assert domain_for("deploy_service") == "cloud"
        assert domain_for("drop_database") == "db"

    def test_domain_for_unknown_returns_none(self):
        assert domain_for("send_salary_holiday_email_to_all") is None

    def test_is_known_tool(self):
        assert is_known_tool("query_logs") is True
        assert is_known_tool("totally_bogus_tool") is False


class TestActionClasses:
    def test_known_verbs_map_to_classes(self):
        assert action_class_for("read") == "read"
        assert action_class_for("list") == "read"
        assert action_class_for("query") == "read"
        assert action_class_for("write") == "write"
        assert action_class_for("create") == "write"
        assert action_class_for("execute") == "write"
        assert action_class_for("delete") == "delete"
        assert action_class_for("drop") == "delete"
        assert action_class_for("revoke") == "delete"
        assert action_class_for("assign_role") == "grant"
        assert action_class_for("approve") == "grant"
        assert action_class_for("create_key") == "grant"

    def test_every_verb_in_every_domain_resolves(self):
        for domain, verbs in DOMAIN_VERBS.items():
            for verb in verbs:
                assert action_class_for(verb) in ("read", "write", "delete", "grant"), (
                    f"{domain}/{verb} does not resolve to an action class"
                )

    def test_unknown_action_is_conservative_write(self):
        assert action_class_for("unforeseen_verb") == "write"

    def test_actions_classes_are_consistent_with_table(self):
        for klass in ACTION_CLASSES.values():
            assert klass in ("read", "write", "delete", "grant")


class TestScoringSeeds:
    def test_critical_domains_are_highest_risk(self):
        for domain in ("secrets", "iam", "payment", "approval"):
            assert DOMAIN_BASELINE[domain] >= 0.8
        assert DOMAIN_BASELINE["search"] <= 0.2

    def test_baselines_are_strictly_ordered_for_known_cases(self):
        assert DOMAIN_BASELINE["shell"] > DOMAIN_BASELINE["http"]
        assert DOMAIN_BASELINE["secrets"] > DOMAIN_BASELINE["fs"]
