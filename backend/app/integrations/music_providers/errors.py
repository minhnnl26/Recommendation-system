"""Safe, provider-facing errors without request or credential details."""


class ProviderError(Exception):
    """Base error for an expected provider integration failure."""


class ProviderConfigurationError(ProviderError):
    """Raised when a provider cannot be used with the current configuration."""


class ProviderHTTPError(ProviderError):
    """Raised for a non-success provider response."""

    def __init__(self, provider: str, status_code: int):
        super().__init__(f"{provider} provider request failed (HTTP {status_code})")


class ProviderResponseError(ProviderError):
    """Raised when a provider returns an unusable response."""
