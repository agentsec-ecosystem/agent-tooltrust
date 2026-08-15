"""Tests for M4 Task 2 (#146) — URL fetch category guard.

Three fail-closed layers: robots.txt is enforced, PII/credentials are stripped
before context, and every fetch + redirect hop is re-resolved against an
internal-address blocklist (RFC 1918, loopback, link-local incl. cloud
metadata, reserved ranges). Resolution is injected so tests never touch DNS.
"""

from __future__ import annotations

from agent_tooltrust.engine.fetch_guard import (
    ALLOW_URL_FETCH,
    FetchGuard,
    FetchGuardConfig,
    _default_resolver,
    is_internal_address,
    redact_pii,
    robots_allows,
)
from agent_tooltrust.errors import (
    DENY_URL_BLOCKED_BY_ROBOTS,
    DENY_URL_INTERNAL_ADDRESS,
    DENY_URL_INVALID,
    DENY_URL_SCHEME,
)

ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /"

ROBOTS_BLOCK = """\
User-agent: *
Disallow: /private/
Allow: /public
"""


def _resolver(*ips: str):
    def resolve(host: str) -> tuple[str, ...]:
        _ = host
        return ips

    return resolve


class TestInternalAddress:
    def test_loopback_is_internal(self):
        assert is_internal_address("127.0.0.1")
        assert is_internal_address("::1")

    def test_private_ranges_are_internal(self):
        for ip in ("10.0.0.5", "172.16.0.1", "172.31.255.255", "192.168.1.1"):
            assert is_internal_address(ip)

    def test_cloud_metadata_is_internal(self):
        assert is_internal_address("169.254.169.254")

    def test_link_local_is_internal(self):
        assert is_internal_address("169.254.1.2")
        assert is_internal_address("fe80::1")

    def test_public_is_not_internal(self):
        for ip in ("8.8.8.8", "93.184.216.34", "2606:4700::6810:85e5"):
            assert not is_internal_address(ip)

    def test_malformed_fails_closed(self):
        assert is_internal_address("not-an-ip")
        assert is_internal_address("999.999.999.999")

    def test_default_resolver_returns_ip_strings(self):
        assert _default_resolver("localhost") != ()

    def test_default_resolver_graceful_on_failure(self):
        assert _default_resolver("no-such.invalid-host.nxdom") == ()


class TestRobots:
    def test_allow_when_robots_blank(self):
        assert robots_allows("", "https://example.com/page") is True

    def test_allow_public_path(self):
        assert robots_allows(ROBOTS_BLOCK, "https://example.com/public/page") is True

    def test_block_private_path(self):
        assert (
            robots_allows(ROBOTS_BLOCK, "https://example.com/private/page") is False
        )

    def test_user_agent_specific_rule(self):
        rules = "User-agent: bad-bot\nDisallow: /\nUser-agent: *\nAllow: /\n"
        assert robots_allows(rules, "https://example.com/", "bad-bot") is False
        assert robots_allows(rules, "https://example.com/", "good-bot") is True


class TestRedactPii:
    def test_email_redacted(self):
        assert redact_pii("write me at alice@example.com now") == (
            "write me at [redacted:email] now"
        )

    def test_phone_redacted(self):
        assert redact_pii("call 555-123-4567 today") == "call [redacted:phone] today"

    def test_api_key_redacted(self):
        assert redact_pii("key sk-abc123456789012345678901234 today") == (
            "key [redacted:key] today"
        )

    def test_aws_key_redacted(self):
        assert redact_pii("AKIAIOSFODNN7EXAMPLE here") == "[redacted:key] here"

    def test_hex_token_redacted(self):
        assert redact_pii("token abcdef0123456789abcdef0123456789 end") == (
            "token [redacted:token] end"
        )

    def test_base64_blob_redacted(self):
        blob = "aGVsbG8gd29ybGQgdGhpcyBpcyBhIHNlY3JldA=="
        assert redact_pii(f"data {blob} end") == "data [redacted:token] end"

    def test_long_ordinary_word_survives(self):
        # No upper/lower+digit mix, so a plain long word must not be shredded.
        assert redact_pii("the internationalization committee") == (
            "the internationalization committee"
        )

    def test_long_mixed_case_identifier_survives(self):
        assert redact_pii("someCounterIntelligenceValue here") == (
            "someCounterIntelligenceValue here"
        )

    def test_plain_text_survives(self):
        text = "the quick brown fox jumps over the lazy dog"
        assert redact_pii(text) == text


class TestFetchGuardGate:
    def test_public_https_allowed(self):
        guard = FetchGuard(resolver=_resolver("93.184.216.34"))
        decision = guard.guard("https://example.com/page")
        assert decision.allowed is True
        assert decision.reason_code == ALLOW_URL_FETCH
        assert decision.resolved_ips == ("93.184.216.34",)

    def test_internal_ip_denied(self):
        guard = FetchGuard(resolver=_resolver("10.0.0.5"))
        decision = guard.guard("https://example.com/page")
        assert decision.allowed is False
        assert decision.reason_code == DENY_URL_INTERNAL_ADDRESS

    def test_mixed_resolution_fails_closed(self):
        # One internal address among public ones must still deny.
        guard = FetchGuard(resolver=_resolver("8.8.8.8", "192.168.1.1"))
        decision = guard.guard("https://example.com/page")
        assert decision.allowed is False
        assert decision.reason_code == DENY_URL_INTERNAL_ADDRESS

    def test_bad_scheme_denied(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        decision = guard.guard("file:///etc/passwd")
        assert decision.allowed is False
        assert decision.reason_code == DENY_URL_SCHEME

    def test_no_host_denied(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        assert guard.guard("https:///path-only").allowed is False

    def test_unresolvable_denied(self):
        guard = FetchGuard(resolver=_resolver())
        decision = guard.guard("https://nost.nxdomain.local")
        assert decision.allowed is False
        assert decision.reason_code == DENY_URL_INVALID

    def test_robots_block_denied_before_resolution(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        decision = guard.guard(
            "https://example.com/private/x", robots_txt=ROBOTS_BLOCK
        )
        assert decision.allowed is False
        assert decision.reason_code == DENY_URL_BLOCKED_BY_ROBOTS

    def test_block_internal_disabled_opt_out(self):
        guard = FetchGuard(
            FetchGuardConfig(block_internal=False), resolver=_resolver("10.0.0.5")
        )
        assert guard.guard("https://example.com/page").allowed is True

    def test_content_redacted_on_pass(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        decision = guard.guard(
            "https://example.com/page", content="contact alice@example.com"
        )
        assert decision.allowed is True
        assert decision.redacted == "contact [redacted:email]"

    def test_content_not_redacted_when_redact_off(self):
        guard = FetchGuard(
            FetchGuardConfig(redact=False), resolver=_resolver("8.8.8.8")
        )
        decision = guard.guard("https://example.com/page", content="alice@example.com")
        assert decision.redacted == "alice@example.com"

    def test_decision_to_dict(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        payload = guard.guard("https://example.com/page").to_dict()
        assert payload["reason_code"] == ALLOW_URL_FETCH
        assert payload["resolved_ips"] == ["8.8.8.8"]


class TestRedirectGuard:
    def test_public_redirect_allowed(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        decision = guard.redirect_target("https://example.com/a", "https://other.com/b")
        assert decision.allowed is True

    def test_redirect_into_internal_denied(self):
        guard = FetchGuard(resolver=_resolver("127.0.0.1"))
        decision = guard.redirect_target("https://example.com/a", "http://localhost/admin")
        assert decision.allowed is False
        assert decision.reason_code == DENY_URL_INTERNAL_ADDRESS

    def test_relative_redirect_keeps_host(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        decision = guard.redirect_target("https://example.com/a", "/private/admin")
        assert decision.allowed is True
        assert decision.url == "https://example.com/private/admin"

    def test_redirect_scheme_change_to_internal_denied(self):
        guard = FetchGuard(resolver=_resolver("10.1.2.3"))
        decision = guard.redirect_target("https://example.com/a", "https://intranet.local/")
        assert decision.allowed is False

    def test_protocol_relative_redirect_to_metadata_denied(self):
        # '//169.254.169.254/...' must switch authority and be re-resolved,
        # not be absorbed as a path under the current public host.
        guard = FetchGuard(resolver=_resolver("169.254.169.254"))
        decision = guard.redirect_target(
            "https://example.com/a", "//169.254.169.254/latest/meta-data/"
        )
        assert decision.allowed is False
        assert decision.reason_code == DENY_URL_INTERNAL_ADDRESS

    def test_protocol_relative_redirect_to_public_allowed(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        decision = guard.redirect_target("https://example.com/a", "//other.com/page")
        assert decision.allowed is True
        assert decision.url == "https://other.com/page"

    def test_absolute_file_uri_redirect_denied_by_scheme(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        decision = guard.redirect_target("https://example.com/a", "file:///etc/passwd")
        assert decision.allowed is False
        assert decision.reason_code == DENY_URL_SCHEME

    def test_relative_redirect_normalizes_dot_segments(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        decision = guard.redirect_target("https://example.com/a/b", "../page")
        assert decision.allowed is True
        assert decision.url == "https://example.com/page"

    def test_relative_redirect_without_leading_slash(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        decision = guard.redirect_target("https://example.com/a", "page/b")
        assert decision.allowed is True
        assert decision.url == "https://example.com/page/b"

    def test_current_url_without_scheme_passes_location_through(self):
        guard = FetchGuard(resolver=_resolver("8.8.8.8"))
        decision = guard.redirect_target("no-scheme", "https://example.com/page")
        assert decision.url == "https://example.com/page"


class TestConfig:
    def test_default_config_is_shipped_safe(self):
        config = FetchGuardConfig()
        assert "https" in config.allowed_schemes
        assert config.redact is True
        assert config.block_internal is True

    def test_custom_scheme_allowlist(self):
        guard = FetchGuard(
            FetchGuardConfig(allowed_schemes=frozenset({"http"})),
            resolver=_resolver("8.8.8.8"),
        )
        assert guard.guard("https://example.com/page").allowed is False
        assert guard.guard("http://example.com/page").allowed is True

    def test_config_property_exposed(self):
        config = FetchGuardConfig()
        guard = FetchGuard(config, resolver=_resolver("8.8.8.8"))
        assert guard.config is config
