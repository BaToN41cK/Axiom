"""Errors and exceptions for Axiom."""

from __future__ import annotations

from typing import Any


class AxiomError(Exception):
    """Base error for all Axiom errors."""

    #: Short machine kind used for structured handling.
    kind = "axiom_error"
    #: Human readable cause.
    cause: str = "Unknown cause"
    #: Suggested action for the user.
    action: str = "Check logs for details"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def user_report(self) -> str:
        """Return a short user-friendly report (no tracebacks)."""
        lines = [
            f"ERROR ({self.kind})",
            f"Cause:  {self.cause}",
            f"Action: {self.action}",
        ]
        debug = f"Debug log: ~/.axiom/logs/axiom.log"
        return "\n".join(lines) + f"\n{debug}"


class ConfigurationError(AxiomError):
    kind = "configuration"
    cause = "Invalid or missing configuration"
    action = "Run 'axiom doctor' or edit config"


class WorkspaceBoundaryError(AxiomError):
    """Path escapes the workspace boundary."""

    kind = "workspace_boundary"
    cause = "Path is outside the workspace"
    action = "Use paths inside the current workspace"

    def __init__(self, path: str, workspace: str) -> None:
        super().__init__(f"Path '{path}' is outside workspace '{workspace}'")
        self.path = path
        self.workspace = workspace


class PermissionDeniedError(AxiomError):
    kind = "permission_denied"
    cause = "Permission was denied for this action"
    action = "Adjust permissions with /permissions or approve the prompt"

    def __init__(self, permission: str, action: str = "") -> None:
        super().__init__(f"Permission denied: {permission} {action}".strip())
        self.permission = permission


class ProviderError(AxiomError):
    kind = "provider"
    cause = "Model provider request failed"
    action = "Check provider status with /providers or run 'axiom doctor'"


class ProviderRateLimitError(ProviderError):  # type: ignore[valid-type,misc]
    kind = "rate_limited"
    cause = "Provider rate limit reached"
    action = "Wait briefly or switch model with /models"


class ProviderAuthError(ProviderError):
    kind = "invalid_credentials"
    cause = "API key is missing or invalid"
    action = "Update API key via /settings or environment variable"


class ProviderTimeoutError(ProviderError):
    kind = "timeout"
    cause = "Provider request timed out"
    action = "Retry, or switch to a faster model"


class ProviderUnavailableError(ProviderError):
    kind = "offline"
    cause = "Provider is unreachable"
    action = "Check network / service status; router can use fallback models"


class ModelNotFoundError(ProviderError):
    kind = "model_not_found"
    cause = "Requested model is not available"
    action = "Run 'axiom models' to list available models"


class ToolExecutionError(AxiomError):
    kind = "tool_error"
    cause = "Tool execution failed"
    action = "Inspect the tool result shown in the UI"


class ToolTimeoutError(ToolExecutionError):
    kind = "tool_timeout"
    cause = "Tool timed out"
    action = "Increase timeout in tool settings or retry"


class MalformedResponseError(AxiomError):
    kind = "malformed_response"
    cause = "Model returned a malformed response"
    action = "Retry; if it persists, switch model"


class SessionError(AxiomError):
    kind = "session"
    cause = "Session storage error"
    action = "Check ~/.axiom/sessions directory and SQLite database"


# ProviderError alias so modules can catch the family without circulars.
ProviderError = ProviderError  # noqa: F811  (self alias for readability)
