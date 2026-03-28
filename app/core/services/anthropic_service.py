"""
Backward-compatibility shim — re-exports everything from openai_service.

All existing callers (businesses.py, chat.py, email_service.py, etc.) import
from this module using the old names (claude_cli, ClaudeCliError, etc.).
Those imports continue to work unchanged.
"""

from app.core.services.openai_service import (
    OpenAIService as AnthropicService,
    OpenAIServiceError as AnthropicServiceError,
    OpenAIServiceNotReady as AnthropicServiceNotReady,
    build_profile_context,
    openai_service as anthropic_service,
)

# Legacy aliases used across the codebase
ClaudeCliError = AnthropicServiceError
ClaudeCliNotReady = AnthropicServiceNotReady
ClaudeCliTokenExpired = AnthropicServiceError
claude_cli = anthropic_service

__all__ = [
    "AnthropicService",
    "AnthropicServiceError",
    "AnthropicServiceNotReady",
    "ClaudeCliError",
    "ClaudeCliNotReady",
    "ClaudeCliTokenExpired",
    "anthropic_service",
    "claude_cli",
    "build_profile_context",
]
