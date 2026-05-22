from typing import AsyncIterator
from .base import BaseLLMProvider, LLMResponse, StreamChunk
from app.config import settings


class GroqProvider(BaseLLMProvider):
    provider_name = "groq"

    def __init__(self):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    async def chat(self, messages: list[dict], model: str = "llama-3.3-70b-versatile", max_tokens: int = 2048, temperature: float = 0.7) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            content=choice.message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            model=response.model,
            provider=self.provider_name,
            request_id=response.id,
            raw_response=response.model_dump(),
        )

    async def stream_chat(self, messages: list[dict], model: str = "llama-3.3-70b-versatile", max_tokens: int = 2048, temperature: float = 0.7) -> AsyncIterator[StreamChunk]:
        stream = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        request_id = None
        async for chunk in stream:
            if not request_id:
                request_id = chunk.id
            delta = ""
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
            is_final = bool(chunk.choices and chunk.choices[0].finish_reason)
            usage = getattr(chunk, "usage", None)
            yield StreamChunk(
                delta=delta,
                is_final=is_final,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                request_id=request_id,
            )
