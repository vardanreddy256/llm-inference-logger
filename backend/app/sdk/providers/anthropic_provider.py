from typing import AsyncIterator
from .base import BaseLLMProvider, LLMResponse, StreamChunk
from app.config import settings


class AnthropicProvider(BaseLLMProvider):
    provider_name = "anthropic"

    def __init__(self):
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def chat(self, messages: list[dict], model: str = "claude-sonnet-4-5", max_tokens: int = 2048, temperature: float = 0.7) -> LLMResponse:
        # Anthropic uses a separate system field
        system_messages = [m["content"] for m in messages if m["role"] == "system"]
        user_messages = [m for m in messages if m["role"] != "system"]
        system_text = " ".join(system_messages) if system_messages else "You are a helpful assistant."

        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_text,
            messages=user_messages,
        )
        content = response.content[0].text if response.content else ""
        usage = response.usage
        return LLMResponse(
            content=content,
            prompt_tokens=usage.input_tokens if usage else 0,
            completion_tokens=usage.output_tokens if usage else 0,
            total_tokens=(usage.input_tokens + usage.output_tokens) if usage else 0,
            model=response.model,
            provider=self.provider_name,
            request_id=response.id,
            raw_response={"id": response.id, "model": response.model},
        )

    async def stream_chat(self, messages: list[dict], model: str = "claude-sonnet-4-5", max_tokens: int = 2048, temperature: float = 0.7) -> AsyncIterator[StreamChunk]:
        system_messages = [m["content"] for m in messages if m["role"] == "system"]
        user_messages = [m for m in messages if m["role"] != "system"]
        system_text = " ".join(system_messages) if system_messages else "You are a helpful assistant."

        request_id = None
        prompt_tokens = 0
        completion_tokens = 0

        async with self._client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_text,
            messages=user_messages,
        ) as stream:
            async for event in stream:
                event_type = type(event).__name__
                if event_type == "MessageStartEvent":
                    request_id = event.message.id
                    if event.message.usage:
                        prompt_tokens = event.message.usage.input_tokens
                elif event_type == "ContentBlockDeltaEvent":
                    delta = event.delta.text if hasattr(event.delta, "text") else ""
                    yield StreamChunk(delta=delta, is_final=False, request_id=request_id)
                elif event_type == "MessageDeltaEvent":
                    if event.usage:
                        completion_tokens = event.usage.output_tokens
                elif event_type == "MessageStopEvent":
                    yield StreamChunk(
                        delta="",
                        is_final=True,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=prompt_tokens + completion_tokens,
                        request_id=request_id,
                    )
