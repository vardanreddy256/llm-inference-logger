"""
Chat endpoint with SSE streaming and multi-turn context.
"""
import uuid
import json
import datetime
from typing import Optional, AsyncIterator
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, AsyncSessionLocal
from app.models import Conversation, Message
from app.models.conversation import ConversationStatus
from app.sdk import LLMWrapper, DEFAULT_MODELS
from app.sdk.providers import PROVIDER_MAP

router = APIRouter(prefix="/chat", tags=["chat"])

# Context window: keep last N message pairs to control token usage
MAX_CONTEXT_MESSAGES = 20


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    provider: str = "openai"
    model: Optional[str] = None
    stream: bool = True


async def _get_or_create_conversation(
    session_id: Optional[str],
    provider: str,
    model: str,
    db: AsyncSession,
) -> Conversation:
    if session_id:
        result = await db.execute(
            select(Conversation).where(Conversation.session_id == session_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conv.status == ConversationStatus.CANCELLED.value:
            raise HTTPException(status_code=409, detail="Conversation is cancelled. Resume it first.")
        return conv

    conv = Conversation(
        session_id=str(uuid.uuid4()),
        provider=provider,
        model=model,
        status=ConversationStatus.ACTIVE.value,
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


async def _load_context(conversation_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sequence_number.desc())
        .limit(MAX_CONTEXT_MESSAGES)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in messages]


async def _save_message(
    conversation_id: uuid.UUID, role: str, content: str,
    sequence_number: int, db: AsyncSession
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        content_preview=content[:500],
        sequence_number=sequence_number,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


async def _stream_sse(gen: AsyncIterator, session_id: str, model: str):
    """Wrap stream chunks as Server-Sent Events."""
    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id, 'model': model})}\n\n"
    full_content = []
    async for chunk in gen:
        if chunk.delta:
            full_content.append(chunk.delta)
            yield f"data: {json.dumps({'type': 'delta', 'content': chunk.delta})}\n\n"
        if chunk.is_final:
            yield f"data: {json.dumps({'type': 'done', 'content': ''.join(full_content)})}\n\n"
    yield "data: [DONE]\n\n"


@router.post("")
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    if body.provider not in PROVIDER_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{body.provider}'")

    model = body.model or DEFAULT_MODELS.get(body.provider, "gpt-4.1")
    conv = await _get_or_create_conversation(body.session_id, body.provider, model, db)

    # Build context
    context = await _load_context(conv.id, db)
    context.append({"role": "user", "content": body.message})

    # Count next sequence number
    seq = len(context)

    # Save user message
    user_msg = await _save_message(conv.id, "user", body.message, seq, db)

    # Auto-title on first message
    if seq == 1 and not conv.title:
        conv.title = body.message[:80]
        await db.flush()

    # Update conversation timestamp via model
    conv.updated_at = datetime.datetime.utcnow()
    await db.flush()
    await db.commit()

    wrapper = LLMWrapper(body.provider)

    if body.stream:
        async def _stream_and_save():
            full_content = []
            gen = wrapper.stream_chat(
                messages=context,
                model=model,
                conversation_id=str(conv.id),
                message_id=str(user_msg.id),
            )
            yield f"data: {json.dumps({'type': 'session', 'session_id': conv.session_id, 'model': model})}\n\n"
            async for chunk in gen:
                if chunk.delta:
                    full_content.append(chunk.delta)
                    yield f"data: {json.dumps({'type': 'delta', 'content': chunk.delta})}\n\n"
                if chunk.is_final:
                    complete = "".join(full_content)
                    # Persist assistant message in a fresh session (original db is closed after route handler returns)
                    async with AsyncSessionLocal() as save_db:
                        assistant_msg = Message(
                            conversation_id=conv.id,
                            role="assistant",
                            content=complete,
                            content_preview=complete[:500],
                            sequence_number=seq + 1,
                        )
                        save_db.add(assistant_msg)
                        await save_db.commit()
                    yield f"data: {json.dumps({'type': 'done', 'content': complete})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _stream_and_save(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            },
        )
    else:
        response = await wrapper.chat(
            messages=context,
            model=model,
            conversation_id=str(conv.id),
            message_id=str(user_msg.id),
        )
        # Save assistant message
        await _save_message(conv.id, "assistant", response.content, seq + 1, db)
        await db.commit()
        return {
            "session_id": conv.session_id,
            "model": model,
            "provider": body.provider,
            "content": response.content,
            "usage": {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
            },
        }
