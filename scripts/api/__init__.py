"""
API Package - LLM Provider Abstraction

Provides unified interface for multiple LLM backends.

Usage:
    from scripts.api import get_provider, Message
    
    # Get a provider
    provider = get_provider("openai")
    
    # Simple prompt
    response = provider.simple_prompt("Explain quantum computing")
    print(response.content)
    
    # Full conversation
    messages = [
        Message(role="system", content="You are a physics tutor"),
        Message(role="user", content="What is wave-particle duality?")
    ]
    response = provider.call(messages)
    print(response.content)
"""

from .llm_provider import (
    LLMProvider,
    LLMResponse,
    Message,
    LLMProviderError,
    RateLimitError,
    AuthenticationError,
    ModelNotFoundError
)

from .openai_provider import OpenAIProvider, call_openai
from .claude_provider import ClaudeProvider, call_claude

from .provider_factory import (
    ProviderFactory,
    get_provider,
    get_provider_with_fallback
)

__all__ = [
    # Core abstractions
    "LLMProvider",
    "LLMResponse",
    "Message",
    
    # Exceptions
    "LLMProviderError",
    "RateLimitError",
    "AuthenticationError",
    "ModelNotFoundError",
    
    # Implementations
    "OpenAIProvider",
    "ClaudeProvider",
    
    # Factory
    "ProviderFactory",
    "get_provider",
    "get_provider_with_fallback",
    
    # Legacy compatibility
    "call_openai",
    "call_claude",
]
