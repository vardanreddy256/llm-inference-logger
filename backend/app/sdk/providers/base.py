from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    provider: str = ""
    request_id: Optional[str] = None
    raw_response: dict = field(default_factory=dict)


@dataclass
class StreamChunk:
    delta: str
    is_final: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    request_id: Optional[str] = None


class BaseLLMProvider(ABC):
    provider_name: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Non-streaming chat completion."""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion, yields StreamChunk objects."""
        ...

    @property
    def name(self) -> str:
        return self.provider_name
