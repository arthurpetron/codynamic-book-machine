"""
OpenAI LLM Provider Implementation

Supports GPT-4, GPT-3.5-turbo, and other OpenAI models.
Uses the modern OpenAI Python client (v1.0+).
"""

import os
import time
from typing import List, Optional, Dict, Any

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("[OpenAIProvider] Warning: openai package not installed. Install with: pip install openai")

from .llm_provider import (
    LLMProvider, 
    LLMResponse, 
    Message,
    LLMProviderError,
    RateLimitError,
    AuthenticationError,
    ModelNotFoundError
)


class OpenAIProvider(LLMProvider):
    """
    OpenAI API provider supporting GPT models.
    
    Environment variables:
        KEY_OPENAI_API: OpenAI API key
    """
    
    SUPPORTED_MODELS = {
        "gpt-4-turbo-preview",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-4-32k",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
    }
    
    DEFAULT_MODEL = "gpt-4-turbo-preview"
    
    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None):
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package required. Install with: pip install openai")
        
        api_key = api_key or os.getenv("KEY_OPENAI_API")
        if not api_key:
            raise AuthenticationError("OpenAI API key not found. Set KEY_OPENAI_API environment variable.")
        
        super().__init__(api_key, default_model or self.DEFAULT_MODEL)
        self.client = OpenAI(api_key=api_key)
    
    def call(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> LLMResponse:
        """
        Make a completion request to OpenAI.
        
        Additional kwargs:
            top_p: Nucleus sampling parameter
            frequency_penalty: Penalty for token frequency
            presence_penalty: Penalty for token presence
            stop: Stop sequences
        """
        model = model or self.default_model
        
        if not self.validate_model(model):
            raise ModelNotFoundError(f"Model {model} not supported by OpenAI provider")
        
        # Convert Message objects to OpenAI format
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        
        start_time = time.time()
        
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else None
            
            self._track_call(tokens_used)
            
            return LLMResponse(
                content=content,
                model=response.model,
                provider=self.get_provider_name(),
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                metadata={
                    "finish_reason": response.choices[0].finish_reason,
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                    "completion_tokens": response.usage.completion_tokens if response.usage else None,
                }
            )
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if "rate_limit" in error_msg or "rate limit" in error_msg:
                raise RateLimitError(f"OpenAI rate limit exceeded: {e}")
            elif "authentication" in error_msg or "api_key" in error_msg:
                raise AuthenticationError(f"OpenAI authentication failed: {e}")
            elif "model" in error_msg and "not found" in error_msg:
                raise ModelNotFoundError(f"OpenAI model not found: {e}")
            else:
                raise LLMProviderError(f"OpenAI API error: {e}")
    
    def get_provider_name(self) -> str:
        return "openai"
    
    def validate_model(self, model: str) -> bool:
        """Check if model is in supported set or follows OpenAI naming pattern"""
        return model in self.SUPPORTED_MODELS or model.startswith("gpt-")


# Convenience function for backward compatibility
def call_openai(
    prompt: str,
    model: str = OpenAIProvider.DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    system_prompt: Optional[str] = None
) -> str:
    """
    Simple function interface for OpenAI calls.
    Compatible with legacy openai_hook.py interface.
    """
    provider = OpenAIProvider()
    response = provider.simple_prompt(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.content
