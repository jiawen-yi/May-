"""Caller-facing failures. A failed gate is a result object, not an exception."""


class MayError(Exception):
    """Base error for invalid calls and policy breaches."""


class PolicyBreach(MayError):
    """An action would break a hard desk rule (stop ratchet, naked entry, …)."""


class LiveTradingDisabled(MayError):
    """Live routing was requested without both required switches."""


class FirewallError(MayError):
    """Long-book research tried to enter the sleeve path, or the reverse."""


class ConfigError(MayError):
    """Config tried to loosen a fixed principle, or a file is invalid."""


class FixtureError(MayError):
    """A sample/mock input could not be read."""
