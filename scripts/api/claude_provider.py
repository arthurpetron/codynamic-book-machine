"""
Anthropic Claude LLM Provider Implementation

Supports Claude 3 models (Opus, Sonnet, Haiku) and Claude 3.5.
Uses the Anthropic Python SDK.
"""

import os
import time
from typing import List, Optional, Dict, Any

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("[ClaudeProvider] Warning: anthropic package not installed. Install with: pip install anthropic")

from .llm_provider import (
    LLMProvider,
    LLMResponse,
    Message,
    LLMProviderError,
    RateLimitError,
    AuthenticationError,
    ModelNotFoundError
)


class ClaudeProvider(LLMProvider):
    """
    Anthropic Claude API provider.
    
    Environment variables:
        KEY_ANTHROPIC_API: Anthropic API key
        ANTHROPIC_API_KEY: Alternative API key variable name (SDK default)
    """
    
    SUPPORTED_MODELS = {
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
        "claude-3-5-sonnet-20240620",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
    }
    
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
    
    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None):
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package required. Install with: pip install anthropic")
        
        # Try multiple API key sources
        api_key = api_key or os.getenv("KEY_ANTHROPIC_API") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise AuthenticationError(
                "Anthropic API key not found. Set KEY_ANTHROPIC_API or ANTHROPIC_API_KEY environment variable."
            )
        
        super().__init__(api_key, default_model or self.DEFAULT_MODEL)
        self.client = Anthropic(api_key=api_key)
    
    def call(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> LLMResponse:
        """
        Make a completion request to Claude.
        
        Additional kwargs:
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
            stop_sequences: Stop sequences
            system: System prompt (alternative to system message)
        """
        model = model or self.default_model
        
        if not self.validate_model(model):
            raise ModelNotFoundError(f"Model {model} not supported by Claude provider")
        
        # Claude API requires system messages to be separated
        system_content = None
        conversation_messages = []
        
        for msg in messages:
            if msg.role == "system":
                # Concatenate multiple system messages
                if system_content:
                    system_content += "\n\n" + msg.content
                else:
                    system_content = msg.content
            else:
                conversation_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Allow system prompt override via kwargs
        if "system" in kwargs:
            system_content = kwargs.pop("system")
        
        start_time = time.time()
        
        try:
            # Build API call parameters
            api_params = {
                "model": model,
                "messages": conversation_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }
            
            # Only include system if it exists
            if system_content:
                api_params["system"] = system_content
            
            response = self.client.messages.create(**api_params)
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract text content from response
            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text
            
            # Calculate approximate token usage
            # Claude API returns usage info
            tokens_used = None
            if hasattr(response, 'usage'):
                tokens_used = response.usage.input_tokens + response.usage.output_tokens
            
            self._track_call(tokens_used)
            
            return LLMResponse(
                content=content,
                model=response.model,
                provider=self.get_provider_name(),
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                metadata={
                    "stop_reason": response.stop_reason,
                    "input_tokens": response.usage.input_tokens if hasattr(response, 'usage') else None,
                    "output_tokens": response.usage.output_tokens if hasattr(response, 'usage') else None,
                }
            )
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if "rate" in error_msg and "limit" in error_msg:
                raise RateLimitError(f"Claude rate limit exceeded: {e}")
            elif "authentication" in error_msg or "api_key" in error_msg or "unauthorized" in error_msg:
                raise AuthenticationError(f"Claude authentication failed: {e}")
            elif "model" in error_msg and ("not found" in error_msg or "invalid" in error_msg):
                raise ModelNotFoundError(f"Claude model not found: {e}")
            else:
                raise LLMProviderError(f"Claude API error: {e}")
    
    def get_provider_name(self) -> str:
        return "anthropic"
    
    def validate_model(self, model: str) -> bool:
        """Check if model is in supported set or follows Claude naming pattern"""
        return model in self.SUPPORTED_MODELS or model.startswith("claude-")


# Convenience function matching OpenAI interface
def call_claude(
    prompt: str,
    model: str = ClaudeProvider.DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    system_prompt: Optional[str] = None
) -> str:
    """
    Simple function interface for Claude calls.
    Matches call_openai interface for easy swapping.
    """
    provider = ClaudeProvider()
    response = provider.simple_prompt(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.content
