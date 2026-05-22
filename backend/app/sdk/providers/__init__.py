from .base import BaseLLMProvider, LLMResponse, StreamChunk
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider

PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
}

DEFAULT_MODELS = {
    "openai": "gpt-4.1",
    "anthropic": "claude-sonnet-4-5",
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
}


def get_provider(name: str) -> BaseLLMProvider:
    cls = PROVIDER_MAP.get(name)
    if not cls:
        raise ValueError(f"Unknown provider '{name}'. Available: {list(PROVIDER_MAP.keys())}")
    return cls()


__all__ = ["BaseLLMProvider", "LLMResponse", "StreamChunk", "get_provider", "DEFAULT_MODELS", "PROVIDER_MAP"]
