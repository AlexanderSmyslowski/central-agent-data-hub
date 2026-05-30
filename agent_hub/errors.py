"""Expected Agent Data Hub error types."""

from __future__ import annotations


class AgentHubError(RuntimeError):
    """Base class for user-facing Hub failures."""


class ConfigurationError(AgentHubError):
    """Required runtime configuration is missing or invalid."""


class ValidationError(AgentHubError):
    """Input or domain validation failed."""


class NotFoundError(ValidationError):
    """A required Hub object was not found."""


class SafetyError(ValidationError):
    """Input was rejected by a safety rule."""
