"""M4 Task 2 (#146) — URL fetch category guard (dev.to iwasinnam2).

An agent that fetches URLs is implicitly authorized to *read* - but not to
touch the host's internals. This guard makes the fetch decision at three
layers, each fail-closed:

**Layer 1 — robots.txt.** Before fetching a path, consult the site's
``robots.txt`` and deny the fetch when the path is disallowed for the agent's
user-agent. The parser is the stdlib :mod:`urllib.robotparser` fed pure text
(no I/O), so it is deterministic and offline-testable.

**Layer 2 — PII redaction.** Whatever the fetch returns, anything that looks
like an email, phone number, or credential is stripped before the content
enters the model context. Defense in depth: the fetch itself still happened,
but the sensitive payload does not reach the agent.

**Layer 3 — SSRF redirect re-resolution.** Every target URL (the original and
*every* redirect hop) is resolved to its IPs and compared against an
internal-address blocklist: loopback, RFC 1918 private ranges, link-local
(including the cloud metadata address ``169.254.169.254``), and reserved
addresses. A resolution to any internal address is a hard deny, so a fetch to
a public URL that redirects back into the network cannot exfiltrate metadata
or probe internal hosts. Resolution is delegated to an injectable ``resolver``
(defaults to :func:`socket.getaddrinfo`) so tests never touch the network.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from agent_tooltrust.errors import (
    DENY_URL_BLOCKED_BY_ROBOTS,
    DENY_URL_INTERNAL_ADDRESS,
    DENY_URL_INVALID,
    DENY_URL_SCHEME,
)

#: Reason codes used while a fetch is *allowed* (decision side of the gate).
ALLOW_URL_FETCH = "allow_url_fetch"

_DEFAULT_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_USER_AGENT = "ToolTrustFetchGuard/1.0"

#: RFC 1918 + loopback + link-local + reserved addresses are never fetchable.
#: The cloud metadata endpoint (169.254.169.254, link-local) is covered by
#: :meth:`is_internal_address` via ``is_link_local``.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<![\w])[+]?1?[ (.-]*\d{3}[).-]*\d{3}[ .-]*\d{4}\b")
#: Common high-cardinality secrets: 32+ hex, 40+ hex, OpenAI-style ``sk-``
#: keys, AWS access keys. Conservative on purpose - over-redaction beats
#: under-redaction. The base64 rule requires a *mix* of upper/lower case and
#: digits (or explicit padding/+/) so ordinary long words like
#: "internationalization" are not shredded.
_HEX32_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")
#: base64-like blobs: 16+ chars with a mix of upper/lower case and digits
#: (optionally padding), bounded by non-word characters so ordinary long words
#: like "internationalization" never match.
_B64_RE = re.compile(
    r"(?<![\w])(?=.*[0-9])(?=.*[A-Z])(?=.*[a-z])[A-Za-z0-9+/]{16,}={0,2}(?![\w])"
)
_SK_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")
_AWS_AK_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")

Resolver = Callable[[str], tuple[str, ...]]


def _default_resolver(host: str) -> tuple[str, ...]:
    """Resolve a host to its IP addresses via the system resolver.

    Args:
        host: The hostname to resolve.

    Returns:
        A tuple of IP strings (may be empty when resolution fails).
    """
    try:
        results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return ()
    return tuple(dict.fromkeys(str(info[4][0]) for info in results))


def is_internal_address(address: str) -> bool:
    """Whether an IP address is internal and therefore never fetchable.

    Loopback (127.0.0.0/8, ::1), RFC 1918 private ranges (10/8, 172.16/12,
    192.168/16), link-local (169.254/16, fe80::/10 — covers the cloud metadata
    endpoint), and reserved addresses all count as internal. Anything that is
    not a well-formed global unicast address also returns ``True`` (fail-closed).

    Args:
        address: A numeric IP string (IPv4 or IPv6).

    Returns:
        ``True`` when the address is internal, malformed, or non-global.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved


def redact_pii(text: str) -> str:
    """Strip PII and credential-like fragments from fetched content.

    Emails, phone numbers, long hex/base64 tokens, ``sk-`` API keys, and AWS
    access-keys are replaced with a fixed placeholder so the content can still
    be read by the agent without leaking secrets into context.

    Args:
        text: The fetched content to sanitize.

    Returns:
        The content with sensitive fragments redacted.
    """
    text = _EMAIL_RE.sub("[redacted:email]", text)
    text = _SK_KEY_RE.sub("[redacted:key]", text)
    text = _AWS_AK_RE.sub("[redacted:key]", text)
    text = _HEX32_RE.sub("[redacted:token]", text)
    text = _B64_RE.sub("[redacted:token]", text)
    text = _PHONE_RE.sub("[redacted:phone]", text)
    return text


def robots_allows(
    robots_txt: str,
    url: str,
    user_agent: str = _DEFAULT_USER_AGENT,
) -> bool:
    """Consult a robots.txt body and report whether *url* may be fetched.

    Deterministic and offline: the rules are parsed from the passed string,
    never fetched. A malformed or empty rules body defaults to allow (the
    robot-parse convention); an explicitly disallowed path returns ``False``.

    Args:
        robots_txt: The full ``robots.txt`` document text.
        url: The absolute URL being fetched.
        user_agent: The agent's user-agent token for ``User-agent:`` matching.

    Returns:
        ``True`` when the path is allowed for *user_agent*.
    """
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(user_agent, url)


@dataclass(frozen=True)
class FetchGuardConfig:
    """Configuration for the :class:`FetchGuard`.

    Attributes:
        allowed_schemes: URL schemes permitted at the gate (default http/https).
        default_user_agent: Used when a call does not supply one.
        redact: Whether fetched content is PII/secret-stripped on passage.
        block_internal: Whether internal-address resolutions are denied.
    """

    allowed_schemes: frozenset[str] = _DEFAULT_ALLOWED_SCHEMES
    default_user_agent: str = _DEFAULT_USER_AGENT
    redact: bool = True
    block_internal: bool = True


@dataclass(frozen=True)
class FetchDecision:
    """The outcome of one URL-fetch gate evaluation.

    Attributes:
        allowed: ``True`` when the fetch may proceed.
        reason_code: Machine-readable reason (allow or deny).
        url: The URL evaluated.
        resolved_ips: IPs the (final) target resolved to, for auditing.
        redacted: The content after PII stripping, when the fetch is allowed
            and :attr:`FetchGuardConfig.redact` is on. ``None`` otherwise.
    """

    allowed: bool
    reason_code: str
    url: str
    resolved_ips: tuple[str, ...]
    redacted: str | None = None

    def to_dict(self) -> dict[str, object]:
        """JSON-friendly representation for the audit trail and dashboards."""
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "url": self.url,
            "resolved_ips": list(self.resolved_ips),
        }


class FetchGuard:
    """Deterministic URL fetch gate: scheme -> robots -> SSRF, plus redaction.

    Args:
        config: Gate behavior; defaults are shipped-safe.
        resolver: Callable mapping a host to resolved IPs. Defaults to the
            system resolver via :func:`socket.getaddrinfo`.
    """

    def __init__(
        self, config: FetchGuardConfig | None = None, resolver: Resolver | None = None
    ) -> None:
        self._config = config or FetchGuardConfig()
        self._resolver = resolver or _default_resolver

    @property
    def config(self) -> FetchGuardConfig:
        """The gate behavior in force."""
        return self._config

    def guard(
        self,
        url: str,
        *,
        robots_txt: str | None = None,
        user_agent: str | None = None,
        content: str | None = None,
    ) -> FetchDecision:
        """Evaluate one URL fetch against the full gate.

        Order is fixed: scheme → robots.txt → SSRF re-resolution. The first
        failed layer returns a deny ``FetchDecision``. When everything passes,
        the (optional) fetched *content* is redacted for context ingestion.

        Args:
            url: The absolute URL being fetched.
            robots_txt: The site's ``robots.txt`` body, when the caller has
                already fetched it (set ``None`` to skip the robots layer).
            user_agent: The agent's user-agent token for the robots layer.
            content: The fetched body, redacted before it reaches the model.

        Returns:
            A :class:`FetchDecision` describing allow-or-deny.
        """
        parsed = urlparse(url)
        if parsed.scheme not in self._config.allowed_schemes or not parsed.hostname:
            return self._deny(DENY_URL_SCHEME, url)
        if robots_txt is not None and not robots_allows(
            robots_txt,
            url,
            user_agent or self._config.default_user_agent,
        ):
            return self._deny(DENY_URL_BLOCKED_BY_ROBOTS, url)

        ips = self._resolver(parsed.hostname)
        if not ips:
            return self._deny(DENY_URL_INVALID, url)
        if self._config.block_internal and any(is_internal_address(ip) for ip in ips):
            return FetchDecision(
                allowed=False,
                reason_code=DENY_URL_INTERNAL_ADDRESS,
                url=url,
                resolved_ips=ips,
            )

        redacted = redact_pii(content) if (self._config.redact and content is not None) else content
        return FetchDecision(
            allowed=True,
            reason_code=ALLOW_URL_FETCH,
            url=url,
            resolved_ips=ips,
            redacted=redacted,
        )

    def redirect_target(self, current_url: str, location: str) -> FetchDecision:
        """Re-evaluate a redirect ``Location`` hop for the SSRF guard.

        A public fetch that redirects into an internal address is the classic
        SSRF pivot, so redirects are re-resolved against the same blocklist.
        The *current_url* is only used to build an absolute redirect target
        when *location* is relative.

        Args:
            current_url: The URL the fetch is currently on.
            location: The ``Location`` header value of the redirect.

        Returns:
            A :class:`FetchDecision` for the redirect hop; ``allowed`` is
            ``False`` when it resolves internally or is otherwise invalid.
        """
        target = _absolute_redirect(current_url, location)
        return self.guard(target)

    def _deny(self, reason_code: str, url: str) -> FetchDecision:
        return FetchDecision(
            allowed=False,
            reason_code=reason_code,
            url=url,
            resolved_ips=(),
        )


def _absolute_redirect(current_url: str, location: str) -> str:
    """Resolve a ``Location`` header against the current URL for re-checking.

    Uses :func:`urljoin`, so every header form is turned into an absolute URL
    the gate can re-evaluate:

    - a protocol-relative ``//host/path`` switches authority to *host* (the
      SSRF layer then re-resolves it — a ``//169.254.169.254/...`` redirect
      is denied, not absorbed into the current host);
    - an absolute-URI ``file:///etc/passwd`` keeps its scheme so the scheme
      allowlist rejects it;
    - a root/relative ``/path`` or ``page/b`` resolves against the current
      host with ``..`` segments normalized.

    Args:
        current_url: The running fetch URL.
        location: The redirect target.

    Returns:
        An absolute URL for the gate to re-check, or *location* unchanged
        when the current URL carries no scheme/host to resolve against.
    """
    parsed = urlparse(current_url)
    if not parsed.scheme or not parsed.hostname:
        return location
    return urljoin(current_url, location)


__all__ = [
    "ALLOW_URL_FETCH",
    "FetchDecision",
    "FetchGuard",
    "FetchGuardConfig",
    "is_internal_address",
    "redact_pii",
    "robots_allows",
]
