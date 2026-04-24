"""
LLM Provider Factory

Centralized provider instantiation and management.
Supports configuration-based provider selection and fallback chains.
"""

from typing import Optional, Dict, Any, List
import os

from .llm_provider import LLMProvider, LLMProviderError
from .openai_provider import OpenAIProvider
from .claude_provider import ClaudeProvider


class ProviderFactory:
    """
    Factory for creating and managing LLM providers.
    
    Supports:
    - Provider selection by name
    - Automatic fallback to available providers
    - Provider caching and reuse
    - Configuration-based instantiation
    """
    
    PROVIDER_CLASSES = {
        "openai": OpenAIProvider,
        "anthropic": ClaudeProvider,
        "claude": ClaudeProvider,  # Alias
    }
    
    def __init__(self):
        self._provider_cache: Dict[str, LLMProvider] = {}
    
    def create_provider(
        self,
        provider_name: str,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        cache: bool = True
    ) -> LLMProvider:
        """
        Create or retrieve a cached LLM provider.
        
        Args:
            provider_name: Provider identifier ('openai', 'anthropic', 'claude')
            api_key: Optional API key (uses env vars if not provided)
            default_model: Optional default model override
            cache: Whether to cache and reuse the provider instance
            
        Returns:
            LLMProvider instance
            
        Raises:
            LLMProviderError: If provider creation fails
        """
        provider_name = provider_name.lower()
        
        # Check cache first
        cache_key = f"{provider_name}:{default_model or 'default'}"
        if cache and cache_key in self._provider_cache:
            return self._provider_cache[cache_key]
        
        # Get provider class
        provider_class = self.PROVIDER_CLASSES.get(provider_name)
        if not provider_class:
            available = ", ".join(self.PROVIDER_CLASSES.keys())
            raise LLMProviderError(
                f"Unknown provider '{provider_name}'. Available: {available}"
            )
        
        # Instantiate provider
        try:
            provider = provider_class(
                api_key=api_key,
                default_model=default_model
            )
            
            if cache:
                self._provider_cache[cache_key] = provider
            
            return provider
            
        except Exception as e:
            raise LLMProviderError(f"Failed to create {provider_name} provider: {e}")
    
    def create_with_fallback(
        self,
        preferred_providers: List[str],
        api_keys: Optional[Dict[str, str]] = None,
        default_models: Optional[Dict[str, str]] = None
    ) -> LLMProvider:
        """
        Create provider with automatic fallback.
        
        Tries providers in order until one succeeds.
        Useful for handling missing API keys gracefully.
        
        Args:
            preferred_providers: List of provider names in priority order
            api_keys: Optional dict of provider_name -> api_key
            default_models: Optional dict of provider_name -> model
            
        Returns:
            First successfully created provider
            
        Raises:
            LLMProviderError: If all providers fail
        """
        api_keys = api_keys or {}
        default_models = default_models or {}
        errors = []
        
        for provider_name in preferred_providers:
            try:
                return self.create_provider(
                    provider_name=provider_name,
                    api_key=api_keys.get(provider_name),
                    default_model=default_models.get(provider_name),
                    cache=True
                )
            except Exception as e:
                errors.append(f"{provider_name}: {e}")
                continue
        
        # All providers failed
        error_summary = "; ".join(errors)
        raise LLMProviderError(
            f"All providers failed. Tried: {', '.join(preferred_providers)}. Errors: {error_summary}"
        )
    
    def get_available_providers(self) -> List[str]:
        """
        Return list of provider names that can be instantiated.
        
        Checks for API keys in environment.
        """
        available = []
        
        for provider_name in self.PROVIDER_CLASSES.keys():
            if provider_name == "claude":  # Skip alias
                continue
            
            try:
                # Try to create without caching to test availability
                self.create_provider(provider_name, cache=False)
                available.append(provider_name)
            except Exception:
                continue
        
        return available
    
    def clear_cache(self):
        """Clear all cached provider instances"""
        self._provider_cache.clear()


# Global factory instance
_factory = ProviderFactory()


def get_provider(
    provider_name: str = "openai",
    **kwargs
) -> LLMProvider:
    """
    Convenience function to get a provider from the global factory.
    
    Example:
        provider = get_provider("openai", default_model="gpt-4")
        response = provider.simple_prompt("Hello!")
    """
    return _factory.create_provider(provider_name, **kwargs)


def get_provider_with_fallback(
    preferred_providers: Optional[List[str]] = None,
    **kwargs
) -> LLMProvider:
    """
    Get provider with automatic fallback.
    
    Default fallback order: openai -> anthropic
    
    Example:
        provider = get_provider_with_fallback(["anthropic", "openai"])
    """
    if preferred_providers is None:
        preferred_providers = ["openai", "anthropic"]
    
    return _factory.create_with_fallback(preferred_providers, **kwargs)
