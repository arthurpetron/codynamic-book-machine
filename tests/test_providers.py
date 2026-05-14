"""
Tests for LLM Provider System

Run with: python -m pytest tests/test_providers.py -v
Or: python tests/test_providers.py
"""

import unittest
import os
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.api import (
    Message,
    LLMResponse,
    LLMProvider,
    OpenAIProvider,
    ClaudeProvider,
    ProviderFactory,
    get_provider,
    get_provider_with_fallback,
    LLMProviderError,
    AuthenticationError
)


class TestMessage(unittest.TestCase):
    """Test Message dataclass"""
    
    def test_message_creation(self):
        msg = Message(role="user", content="Hello")
        self.assertEqual(msg.role, "user")
        self.assertEqual(msg.content, "Hello")
    
    def test_message_types(self):
        system_msg = Message(role="system", content="You are helpful")
        user_msg = Message(role="user", content="Question")
        assistant_msg = Message(role="assistant", content="Answer")
        
        self.assertEqual(system_msg.role, "system")
        self.assertEqual(user_msg.role, "user")
        self.assertEqual(assistant_msg.role, "assistant")


class TestLLMResponse(unittest.TestCase):
    """Test LLMResponse dataclass"""
    
    def test_response_creation(self):
        response = LLMResponse(
            content="Test response",
            model="gpt-4",
            provider="openai",
            tokens_used=100,
            latency_ms=500.0
        )
        
        self.assertEqual(response.content, "Test response")
        self.assertEqual(response.model, "gpt-4")
        self.assertEqual(response.provider, "openai")
        self.assertEqual(response.tokens_used, 100)
        self.assertEqual(response.latency_ms, 500.0)
    
    def test_response_optional_fields(self):
        response = LLMResponse(
            content="Test",
            model="test-model",
            provider="test"
        )
        
        self.assertIsNone(response.tokens_used)
        self.assertIsNone(response.latency_ms)
        self.assertIsNone(response.metadata)


class TestProviderFactory(unittest.TestCase):
    """Test ProviderFactory functionality"""
    
    def setUp(self):
        self.factory = ProviderFactory()
    
    def tearDown(self):
        self.factory.clear_cache()
    
    def test_supported_providers(self):
        expected_providers = {"openai", "anthropic", "claude"}
        self.assertEqual(set(self.factory.PROVIDER_CLASSES.keys()), expected_providers)
    
    @patch.dict(os.environ, {"KEY_OPENAI_API": "test-key"})
    @patch('scripts.api.openai_provider.OpenAI')
    def test_create_openai_provider(self, mock_openai_class):
        """Test OpenAI provider creation"""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        provider = self.factory.create_provider("openai", cache=False)
        self.assertIsInstance(provider, OpenAIProvider)
        self.assertEqual(provider.get_provider_name(), "openai")
    
    def test_create_unknown_provider(self):
        """Test that unknown provider raises error"""
        with self.assertRaises(LLMProviderError):
            self.factory.create_provider("unknown-provider")
    
    @patch.dict(os.environ, {"KEY_OPENAI_API": "test-key"})
    @patch('scripts.api.openai_provider.OpenAI')
    def test_provider_caching(self, mock_openai_class):
        """Test that providers are cached correctly"""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        provider1 = self.factory.create_provider("openai", cache=True)
        provider2 = self.factory.create_provider("openai", cache=True)
        
        # Should return same instance
        self.assertIs(provider1, provider2)
    
    @patch.dict(os.environ, {"KEY_OPENAI_API": "test-key"})
    @patch('scripts.api.openai_provider.OpenAI')
    def test_cache_clearing(self, mock_openai_class):
        """Test cache clearing"""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        provider1 = self.factory.create_provider("openai", cache=True)
        self.factory.clear_cache()
        provider2 = self.factory.create_provider("openai", cache=True)
        
        # Should be different instances after cache clear
        self.assertIsNot(provider1, provider2)


class TestOpenAIProvider(unittest.TestCase):
    """Test OpenAI provider implementation"""
    
    @patch.dict(os.environ, {"KEY_OPENAI_API": "test-key"})
    @patch('scripts.api.openai_provider.OpenAI')
    def setUp(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        self.provider = OpenAIProvider(api_key="test-key")
    
    def test_provider_name(self):
        self.assertEqual(self.provider.get_provider_name(), "openai")
    
    def test_validate_supported_models(self):
        self.assertTrue(self.provider.validate_model("gpt-4"))
        self.assertTrue(self.provider.validate_model("gpt-3.5-turbo"))
        self.assertTrue(self.provider.validate_model("gpt-4-turbo-preview"))
    
    def test_validate_gpt_pattern(self):
        """Test that any gpt- prefixed model is considered valid"""
        self.assertTrue(self.provider.validate_model("gpt-future-model"))
    
    def test_invalidate_non_gpt_model(self):
        self.assertFalse(self.provider.validate_model("claude-3"))
    
    @patch('scripts.api.openai_provider.OpenAI')
    def test_missing_api_key(self, mock_openai_class):
        """Test that missing API key raises error"""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AuthenticationError):
                OpenAIProvider()


class TestClaudeProvider(unittest.TestCase):
    """Test Claude provider implementation"""
    
    @patch.dict(os.environ, {"KEY_ANTHROPIC_API": "test-key"})
    @patch('scripts.api.claude_provider.Anthropic')
    def setUp(self, mock_anthropic_class):
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        self.provider = ClaudeProvider(api_key="test-key")
    
    def test_provider_name(self):
        self.assertEqual(self.provider.get_provider_name(), "anthropic")
    
    def test_validate_supported_models(self):
        self.assertTrue(self.provider.validate_model("claude-3-opus-20240229"))
        self.assertTrue(self.provider.validate_model("claude-3-5-sonnet-20241022"))
        self.assertTrue(self.provider.validate_model("claude-3-haiku-20240307"))
    
    def test_validate_claude_pattern(self):
        """Test that any claude- prefixed model is considered valid"""
        self.assertTrue(self.provider.validate_model("claude-future-model"))
    
    def test_invalidate_non_claude_model(self):
        self.assertFalse(self.provider.validate_model("gpt-4"))
    
    @patch('scripts.api.claude_provider.Anthropic')
    def test_missing_api_key(self, mock_anthropic_class):
        """Test that missing API key raises error"""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AuthenticationError):
                ClaudeProvider()


class TestIntegration(unittest.TestCase):
    """Integration tests for provider system"""
    
    @patch.dict(os.environ, {"KEY_OPENAI_API": "test-key"})
    @patch('scripts.api.openai_provider.OpenAI')
    def test_get_provider_convenience_function(self, mock_openai_class):
        """Test get_provider convenience function"""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        provider = get_provider("openai")
        self.assertIsInstance(provider, OpenAIProvider)
    
    @patch.dict(os.environ, {"KEY_OPENAI_API": "test-key"})
    @patch('scripts.api.openai_provider.OpenAI')
    def test_simple_prompt_interface(self, mock_openai_class):
        """Test simple_prompt convenience method"""
        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.model = "gpt-4"
        mock_response.usage.total_tokens = 50
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 40
        mock_response.choices[0].finish_reason = "stop"
        
        mock_client.chat.completions.create.return_value = mock_response
        
        provider = OpenAIProvider(api_key="test-key")
        response = provider.simple_prompt("Test prompt")
        
        self.assertEqual(response.content, "Test response")
        self.assertEqual(response.model, "gpt-4")
        self.assertEqual(response.tokens_used, 50)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
