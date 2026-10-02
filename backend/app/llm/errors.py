from __future__ import annotations


class LLMError(ValueError):
    """Base class for safe, user-facing LLM errors."""


class LLMConfigurationError(LLMError):
    pass


class LLMConnectionError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMModelNotFoundError(LLMError):
    pass


class LLMEndpointError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass
