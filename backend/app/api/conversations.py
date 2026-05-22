"""
Conversations CRUD: create, list, cancel, resume, get messages.
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Conversation, Message
from app.models.conversation import ConversationStatus

router = APIRouter(prefix="/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    provider: str = "openai"
    model: Optional[str] = None
    title: Optional[str] = None


class ConversationOut(BaseModel):
    id: str
    session_id: str
    title: Optional[str]
    provider: str
    model: str
    status: str
    created_at: str
    updated_at: str
    message_count: int = 0

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sequence_number: int
    created_at: str

    class Config:
        from_attributes = True


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(Conversation.status == status)
    result = await db.execute(stmt)
    conversations = result.scalars().all()

    out = []
    for conv in conversations:
        count_result = await db.execute(
            select(func.count()).where(Message.conversation_id == conv.id)
        )
        msg_count = count_result.scalar() or 0
        out.append(ConversationOut(
            id=str(conv.id),
            session_id=conv.session_id,
            title=conv.title,
            provider=conv.provider,
            model=conv.model,
            status=conv.status,
            created_at=conv.created_at.isoformat(),
            updated_at=conv.updated_at.isoformat(),
            message_count=msg_count,
        ))
    return out


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: CreateConversationRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.sdk.providers import DEFAULT_MODELS
    model = body.model or DEFAULT_MODELS.get(body.provider, "gpt-4.1")
    conv = Conversation(
        session_id=str(uuid.uuid4()),
        provider=body.provider,
        model=model,
        title=body.title,
        status=ConversationStatus.ACTIVE.value,
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return ConversationOut(
        id=str(conv.id),
        session_id=conv.session_id,
        title=conv.title,
        provider=conv.provider,
        model=conv.model,
        status=conv.status,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        message_count=0,
    )


@router.get("/{session_id}", response_model=ConversationOut)
async def get_conversation(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    count_result = await db.execute(select(func.count()).where(Message.conversation_id == conv.id))
    msg_count = count_result.scalar() or 0
    return ConversationOut(
        id=str(conv.id),
        session_id=conv.session_id,
        title=conv.title,
        provider=conv.provider,
        model=conv.model,
        status=conv.status,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        message_count=msg_count,
    )


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def get_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msg_result = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()
    return [
        MessageOut(
            id=str(m.id),
            role=m.role,
            content=m.content,
            sequence_number=m.sequence_number,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.post("/{session_id}/cancel", response_model=ConversationOut)
async def cancel_conversation(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.status = ConversationStatus.CANCELLED.value
    await db.flush()
    await db.refresh(conv)
    return ConversationOut(
        id=str(conv.id),
        session_id=conv.session_id,
        title=conv.title,
        provider=conv.provider,
        model=conv.model,
        status=conv.status,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        message_count=0,
    )


@router.post("/{session_id}/resume", response_model=ConversationOut)
async def resume_conversation(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.status = ConversationStatus.ACTIVE.value
    await db.flush()
    await db.refresh(conv)
    return ConversationOut(
        id=str(conv.id),
        session_id=conv.session_id,
        title=conv.title,
        provider=conv.provider,
        model=conv.model,
        status=conv.status,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        message_count=0,
    )
