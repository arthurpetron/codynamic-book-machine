"""
Abstract LLM Provider Interface

Provides a unified interface for multiple LLM backends (OpenAI, Anthropic Claude, etc.)
enabling polymorphic agent behavior across different language models.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import time


@dataclass
class Message:
    """Structured message for LLM conversations"""
    role: str  # 'system', 'user', 'assistant'
    content: str


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider"""
    content: str
    model: str
    provider: str
    tokens_used: Optional[int] = None
    latency_ms: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    Implementations must handle provider-specific authentication,
    rate limiting, error handling, and response formatting.
    """
    
    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None):
        self.api_key = api_key
        self.default_model = default_model
        self._call_count = 0
        self._total_tokens = 0
    
    @abstractmethod
    def call(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> LLMResponse:
        """
        Make a completion request to the LLM.
        
        Args:
            messages: List of Message objects forming the conversation
            model: Model identifier (provider-specific)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens in response
            **kwargs: Provider-specific parameters
            
        Returns:
            LLMResponse with standardized fields
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider identifier (e.g., 'openai', 'anthropic')"""
        pass
    
    @abstractmethod
    def validate_model(self, model: str) -> bool:
        """Check if a model identifier is valid for this provider"""
        pass
    
    def simple_prompt(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Convenience method for single-turn prompts.
        
        Args:
            prompt: User prompt text
            system_prompt: Optional system instruction
            **kwargs: Passed to call()
            
        Returns:
            LLMResponse
        """
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=prompt))
        
        return self.call(messages, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """Return usage statistics"""
        return {
            "provider": self.get_provider_name(),
            "call_count": self._call_count,
            "total_tokens": self._total_tokens
        }
    
    def _track_call(self, tokens: Optional[int] = None):
        """Internal: track usage metrics"""
        self._call_count += 1
        if tokens:
            self._total_tokens += tokens


class LLMProviderError(Exception):
    """Base exception for LLM provider errors"""
    pass


class RateLimitError(LLMProviderError):
    """Raised when rate limit is exceeded"""
    pass


class AuthenticationError(LLMProviderError):
    """Raised when API authentication fails"""
    pass


class ModelNotFoundError(LLMProviderError):
    """Raised when requested model doesn't exist"""
    pass
