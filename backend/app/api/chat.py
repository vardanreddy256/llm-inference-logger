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
import logging

from app.database import get_db, AsyncSessionLocal
from app.models import Conversation, Message
from app.models.conversation import ConversationStatus
from app.sdk import LLMWrapper, DEFAULT_MODELS
from app.sdk.providers import PROVIDER_MAP

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

# Context window: keep last N messages to control token usage
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


@router.post("")
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    if body.provider not in PROVIDER_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{body.provider}'")

    model = body.model or DEFAULT_MODELS.get(body.provider, "gpt-4.1")
    conv = await _get_or_create_conversation(body.session_id, body.provider, model, db)

    # Build context
    context = await _load_context(conv.id, db)
    context.append({"role": "user", "content": body.message})

    # Sequence number for new messages
    seq = len(context)

    # Save user message
    user_msg = await _save_message(conv.id, "user", body.message, seq, db)

    # Auto-title on first message
    if seq == 1 and not conv.title:
        conv.title = body.message[:80]
        await db.flush()

    # Capture values as plain Python before committing — avoids detached-instance errors in the generator
    conv_id: uuid.UUID = conv.id
    conv_session_id: str = conv.session_id
    user_msg_id: uuid.UUID = user_msg.id

    await db.commit()

    wrapper = LLMWrapper(body.provider)

    if body.stream:
        async def _stream_and_save():
            full_content: list[str] = []
            try:
                yield f"data: {json.dumps({'type': 'session', 'session_id': conv_session_id, 'model': model})}\n\n"

                async for chunk in wrapper.stream_chat(
                    messages=context,
                    model=model,
                    conversation_id=str(conv_id),
                    message_id=str(user_msg_id),
                ):
                    if chunk.delta:
                        full_content.append(chunk.delta)
                        yield f"data: {json.dumps({'type': 'delta', 'content': chunk.delta})}\n\n"

                # Stream finished — persist the assistant message
                complete = "".join(full_content)
                if complete:
                    try:
                        async with AsyncSessionLocal() as save_db:
                            assistant_msg = Message(
                                conversation_id=conv_id,
                                role="assistant",
                                content=complete,
                                content_preview=complete[:500],
                                sequence_number=seq + 1,
                            )
                            save_db.add(assistant_msg)
                            await save_db.commit()
                    except Exception as db_err:
                        logger.error("Failed to save assistant message: %s", db_err)

                yield f"data: {json.dumps({'type': 'done', 'content': complete})}\n\n"

            except Exception as exc:
                logger.error("Streaming error for session %s: %s", conv_session_id, exc)
                yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
            finally:
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            _stream_and_save(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
                "Connection": "keep-alive",
            },
        )
    else:
        response = await wrapper.chat(
            messages=context,
            model=model,
            conversation_id=str(conv_id),
            message_id=str(user_msg_id),
        )
        # Save assistant message
        async with AsyncSessionLocal() as save_db:
            await _save_message(conv_id, "assistant", response.content, seq + 1, save_db)
            await save_db.commit()

        return {
            "session_id": conv_session_id,
            "model": model,
            "provider": body.provider,
            "content": response.content,
            "usage": {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
            },
        }
