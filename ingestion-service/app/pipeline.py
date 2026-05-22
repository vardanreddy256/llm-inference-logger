"""
Ingestion pipeline: validate, parse, and persist inference events.
"""
import uuid
import logging
from typing import Optional
from pydantic import BaseModel, ValidationError, field_validator

from app.database import AsyncSessionLocal
from app.models import InferenceLog

logger = logging.getLogger(__name__)


class InferenceEventSchema(BaseModel):
    """Validates and normalises an event from Redis Streams."""
    event_id: str
    conversation_id: str
    message_id: Optional[str] = None
    provider: str
    model: str
    status: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    input_preview: Optional[str] = None
    output_preview: Optional[str] = None
    error_message: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ("success", "error"):
            raise ValueError(f"Invalid status: {v}")
        return v

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v):
        allowed = {"openai", "anthropic", "gemini"}
        if v not in allowed:
            raise ValueError(f"Unknown provider: {v}")
        return v

    @field_validator("latency_ms")
    @classmethod
    def validate_latency(cls, v):
        if v < 0:
            raise ValueError("latency_ms must be non-negative")
        return v


async def process_event(raw_event: dict) -> bool:
    """
    Validate raw event dict, then write to inference_logs table.
    Returns True on success, False on validation/DB error.
    """
    try:
        event = InferenceEventSchema(**raw_event)
    except (ValidationError, Exception) as exc:
        logger.warning("Event validation failed: %s | raw=%s", exc, raw_event)
        return False

    try:
        async with AsyncSessionLocal() as db:
            log = InferenceLog(
                id=uuid.uuid4(),
                conversation_id=_try_uuid(event.conversation_id),
                message_id=_try_uuid(event.message_id),
                provider=event.provider,
                model=event.model,
                status=event.status,
                latency_ms=event.latency_ms,
                prompt_tokens=event.prompt_tokens,
                completion_tokens=event.completion_tokens,
                total_tokens=event.total_tokens,
                input_preview=event.input_preview,
                output_preview=event.output_preview,
                error_message=event.error_message,
                request_id=event.request_id,
                raw_metadata={
                    "event_id": event.event_id,
                    "timestamp": event.timestamp,
                },
            )
            db.add(log)
            await db.commit()
        return True
    except Exception as exc:
        logger.error("Failed to persist inference log: %s", exc)
        return False


def _try_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
