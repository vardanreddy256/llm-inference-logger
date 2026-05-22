"""
Lightweight LLM SDK Wrapper.

Wraps any provider call to capture inference metadata, redact PII,
and publish a log event to Redis Streams for the ingestion service.
"""
import asyncio
import json
import time
import uuid
import logging
from typing import AsyncIterator, Optional
from dataclasses import dataclass, asdict

from .providers import get_provider, DEFAULT_MODELS, StreamChunk, LLMResponse
from .pii_redactor import redact_preview
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class InferenceEvent:
    event_id: str
    conversation_id: str
    message_id: Optional[str]
    provider: str
    model: str
    status: str  # success | error
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    input_preview: str
    output_preview: str
    error_message: Optional[str]
    request_id: Optional[str]
    timestamp: str


class LLMWrapper:
    """
    Drop-in wrapper around any LLM provider.
    - Captures timing, token usage, error status
    - Redacts PII from input/output previews
    - Publishes event to Redis Streams asynchronously (fire-and-forget)
    """

    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self._provider = get_provider(provider_name)
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def _publish_event(self, event: InferenceEvent):
        """Fire-and-forget publish to Redis Streams."""
        try:
            r = await self._get_redis()
            await r.xadd("inference_events", asdict(event), maxlen=10000)
        except Exception as exc:
            # Never let logging failure break the user-facing request
            logger.warning("Failed to publish inference event to Redis: %s", exc)

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> LLMResponse:
        model = model or DEFAULT_MODELS[self.provider_name]
        conversation_id = conversation_id or str(uuid.uuid4())
        start = time.monotonic()
        status = "success"
        error_msg = None
        response = None
        try:
            response = await self._provider.chat(
                messages=messages, model=model,
                max_tokens=max_tokens, temperature=temperature,
            )
            return response
        except Exception as exc:
            status = "error"
            error_msg = str(exc)
            raise
        finally:
            latency_ms = (time.monotonic() - start) * 1000
            user_input = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            event = InferenceEvent(
                event_id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                message_id=message_id,
                provider=self.provider_name,
                model=model,
                status=status,
                latency_ms=round(latency_ms, 2),
                prompt_tokens=response.prompt_tokens if response else 0,
                completion_tokens=response.completion_tokens if response else 0,
                total_tokens=response.total_tokens if response else 0,
                input_preview=redact_preview(user_input, 200) if settings.pii_redaction_enabled else user_input[:200],
                output_preview=redact_preview(response.content, 200) if (response and settings.pii_redaction_enabled) else (response.content[:200] if response else ""),
                error_message=error_msg,
                request_id=response.request_id if response else None,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
            try:
                asyncio.get_event_loop().create_task(self._publish_event(event))
            except Exception:
                pass

    async def stream_chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        model = model or DEFAULT_MODELS[self.provider_name]
        conversation_id = conversation_id or str(uuid.uuid4())
        start = time.monotonic()
        status = "success"
        error_msg = None
        full_content = []
        final_chunk = None

        try:
            async for chunk in self._provider.stream_chat(
                messages=messages, model=model,
                max_tokens=max_tokens, temperature=temperature,
            ):
                if chunk.delta:
                    full_content.append(chunk.delta)
                if chunk.is_final:
                    final_chunk = chunk
                yield chunk
        except Exception as exc:
            status = "error"
            error_msg = str(exc)
            logger.error("LLM provider stream error (%s): %s", self.provider_name, exc)
            # Yield an error delta so the UI shows something meaningful instead of hanging
            yield StreamChunk(delta=f"\n\n⚠️ Provider error: {exc}", is_final=True)
        finally:
            latency_ms = (time.monotonic() - start) * 1000
            user_input = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            output_text = "".join(full_content)
            event = InferenceEvent(
                event_id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                message_id=message_id,
                provider=self.provider_name,
                model=model,
                status=status,
                latency_ms=round(latency_ms, 2),
                prompt_tokens=final_chunk.prompt_tokens if final_chunk else 0,
                completion_tokens=final_chunk.completion_tokens if final_chunk else 0,
                total_tokens=final_chunk.total_tokens if final_chunk else 0,
                input_preview=redact_preview(user_input, 200) if settings.pii_redaction_enabled else user_input[:200],
                output_preview=redact_preview(output_text, 200) if settings.pii_redaction_enabled else output_text[:200],
                error_message=error_msg,
                request_id=final_chunk.request_id if final_chunk else None,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
            # Safe fire-and-forget — wrap in try/except so logging never breaks the stream
            try:
                asyncio.get_event_loop().create_task(self._publish_event(event))
            except Exception:
                pass
