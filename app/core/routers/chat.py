"""
Chat Router — Conversational AI endpoints for department chats.

Users interact with department head employees directly. Each department
has its own chat. Conversations are persisted in the database so chat
history survives page refreshes.

Flow:
  1. User describes what they want
  2. Department head asks clarifying questions
  3. Department head executes actions via platform tools
"""

import logging
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.core.models.business import Business
from app.core.models.conversation import Conversation, ConversationMessage
from app.core.models.organization import Employee
from app.core.services.auth_service import get_current_user_id
from app.core.services.foundry_service import foundry_service, FoundryServiceError, FoundryAgentNotFound
from app.core.services.openai_service import openai_service, OpenAIServiceError
from app.core.services.openai_service import build_profile_context

logger = logging.getLogger(__name__)


def _fresh_system_prompt(emp: "Employee") -> str:
    """
    Return the employee's system prompt from the database.
    This is the source of truth for employee prompts.
    """
    return emp.system_prompt

router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Schemas ──


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    """Send a message to the business automation assistant."""
    business_id: UUID
    conversation_id: Optional[UUID] = None  # If resuming an existing conversation
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Previous conversation messages for context",
    )
    user_message: str = Field(..., min_length=1, max_length=5000)


class ChatResponse(BaseModel):
    content: str
    conversation_id: Optional[UUID] = None  # Persisted conversation ID
    error: Optional[str] = None
    auth_error: bool = False
    auth_error_type: Optional[str] = None  # "token_expired" | "not_connected"


# ── Agent Chat Schemas ──


class AgentChatRequest(BaseModel):
    business_id: UUID
    agent: str  # "admin" | "billing" | "marketing" | "operations" | "sales" | "james"
    message: str = Field(..., min_length=1, max_length=5000)
    thread_id: Optional[str] = None


class AgentChatResponse(BaseModel):
    content: str
    thread_id: Optional[str] = None
    error: Optional[str] = None


# ── Conversation List/Detail Schemas ──

class ConversationMessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    proposal: Optional[dict] = None
    delivery_content: Optional[dict] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: UUID
    title: Optional[str] = None
    status: str
    source: str = "user_chat"
    employee_id: Optional[UUID] = None
    employee_name: Optional[str] = None  # Denormalized from relationship
    is_read: bool = True
    message_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailOut(ConversationOut):
    messages: list[ConversationMessageOut] = Field(default_factory=list)


# ── Helpers ──


def _generate_title(user_message: str) -> str:
    """Generate a short conversation title from the first user message."""
    clean = user_message.strip()
    if len(clean) <= 60:
        return clean
    return clean[:57] + "..."


# ── Agent Chat Endpoint ──


@router.post("/agent", response_model=AgentChatResponse)
async def chat_with_agent(
    payload: AgentChatRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Chat with a Foundry department agent.

    Agents are looked up by name from Azure AI Foundry directly.
    Threads persist across calls when thread_id is provided.
    """
    # Verify business
    stmt = select(Business).where(Business.id == payload.business_id)
    business = (await db.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Build business context from profile
    profile_ctx = build_profile_context(business)
    business_context = (
        f"Business: {business.name}\n\n{profile_ctx}"
        if profile_ctx
        else f"Business: {business.name}"
    )

    try:
        content, thread_id = await foundry_service.chat(
            agent_name=payload.agent,
            message=payload.message,
            business_context=business_context,
            thread_id=payload.thread_id,
            business_id=str(payload.business_id),
        )
        return AgentChatResponse(content=content, thread_id=thread_id)
    except FoundryAgentNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{payload.agent}' not found. Run deploy_agents.py first.",
        )
    except FoundryServiceError as e:
        logger.error(f"Agent chat failed: {e}")
        return AgentChatResponse(
            content="I'm having trouble connecting. Please try again.",
            error=str(e),
        )


# ── Chat Endpoint ──


@router.post("", response_model=ChatResponse)
async def send_chat_message(
    payload: ChatRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message to the business automation assistant.

    If conversation_id is provided, resumes that conversation.
    Otherwise, creates a new conversation automatically.
    """
    # Verify business exists
    stmt = select(Business).where(Business.id == payload.business_id)
    business = (await db.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Get or create conversation
    conversation = None
    if payload.conversation_id:
        conv_stmt = select(Conversation).where(
            Conversation.id == payload.conversation_id,
            Conversation.business_id == payload.business_id,
            Conversation.user_id == current_user_id,
        )
        conversation = (await db.execute(conv_stmt)).scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        # Create a new conversation
        conversation = Conversation(
            business_id=payload.business_id,
            user_id=current_user_id,
            title=_generate_title(payload.user_message),
            status="active",
            message_count=0,
        )
        db.add(conversation)
        await db.flush()

    # Save the user message
    user_msg = ConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content=payload.user_message,
        status="complete",
    )
    db.add(user_msg)

    # Build assistant's system prompt with business context
    profile_content = build_profile_context(business) or None

    system_context = _build_assistant_context(business, profile_content)

    # Build the full message with conversation history
    conversation_parts = []
    for msg in payload.messages[-20:]:  # Last 20 messages for context window
        role_label = "User" if msg.role == "user" else "Assistant"
        conversation_parts.append(f"{role_label}: {msg.content}")
    conversation_parts.append(f"User: {payload.user_message}")
    full_message = "\n\n".join(conversation_parts)

    try:
        response = await openai_service._call_model(
            system_prompt=system_context,
            message=full_message,
            label="Chat",
        )

        # Save assistant message
        assistant_msg = ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=response,
            status="complete",
        )
        db.add(assistant_msg)

        # Update conversation message count
        conversation.message_count = (conversation.message_count or 0) + 2
        conversation.updated_at = datetime.now(timezone.utc)

        return ChatResponse(
            content=response,
            conversation_id=conversation.id,
        )

    except OpenAIServiceError as e:
        logger.error(f"Chat failed for business {payload.business_id}: {e}")

        error_msg = ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content="I'm having trouble connecting right now. Please try again in a moment.",
            status="error",
        )
        db.add(error_msg)
        conversation.message_count = (conversation.message_count or 0) + 2

        return ChatResponse(
            content="I'm having trouble connecting right now. Please try again in a moment.",
            error=str(e),
            conversation_id=conversation.id,
        )


# ── Direct Employee Chat ──


class EmployeeChatRequest(BaseModel):
    business_id: UUID
    employee_id: str  # Employee UUID
    messages: list[dict] = Field(default_factory=list)  # conversation history
    user_message: str


class EmployeeChatResponse(BaseModel):
    content: str
    error: Optional[str] = None


@router.post("/employee", response_model=EmployeeChatResponse)
async def chat_with_employee(
    payload: EmployeeChatRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Chat directly with any employee using their system prompt.
    Used by department page chat features.

    Department heads (is_head=True) get platform tool access — they can
    provision phone numbers, update phone settings, call external APIs, etc.
    Regular employees get text-only chat.
    """
    # Load the employee
    emp = await db.get(Employee, payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Build conversation history into a single message
    history_parts = []
    for msg in payload.messages[-20:]:
        role_label = "User" if msg.get("role") == "user" else emp.name
        history_parts.append(f"{role_label}: {msg.get('content', '')}")
    history_parts.append(f"User: {payload.user_message}")
    full_message = "\n\n".join(history_parts)

    system_prompt = _fresh_system_prompt(emp)

    try:
        response = await openai_service._call_model(
            system_prompt=system_prompt,
            message=full_message,
            label=f"Employee/{emp.name}",
            model=getattr(emp, "model_tier", "haiku"),
        )
        return EmployeeChatResponse(content=response)
    except OpenAIServiceError as e:
        logger.error(f"Employee chat error for {emp.name}: {e}")
        return EmployeeChatResponse(
            content="Something went wrong. Please try again.",
            error=str(e),
        )


# ── Conversation Management Endpoints ──


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    business_id: UUID = Query(...),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="user_chat | department_chat"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List conversations for a business, newest first."""
    stmt = (
        select(Conversation)
        .where(
            Conversation.business_id == business_id,
            Conversation.user_id == current_user_id,
        )
        .options(selectinload(Conversation.employee))
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Conversation.status == status)
    if source:
        stmt = stmt.where(Conversation.source == source)

    result = await db.execute(stmt)
    conversations = result.scalars().all()
    return [
        ConversationOut(
            id=c.id,
            title=c.title,
            status=c.status,
            source=c.source,
            employee_id=c.employee_id,
            employee_name=c.employee.name if c.employee else None,
            is_read=c.is_read,
            message_count=c.message_count,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get a conversation with all its messages."""
    stmt = (
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user_id,
        )
        .options(
            selectinload(Conversation.messages),
            selectinload(Conversation.employee),
        )
    )
    conversation = (await db.execute(stmt)).scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Mark as read when opened
    if not conversation.is_read:
        conversation.is_read = True
        await db.flush()

    return ConversationDetailOut(
        id=conversation.id,
        title=conversation.title,
        status=conversation.status,
        source=conversation.source,
        employee_id=conversation.employee_id,
        employee_name=conversation.employee.name if conversation.employee else None,
        is_read=conversation.is_read,
        message_count=conversation.message_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            ConversationMessageOut.model_validate(m)
            for m in conversation.messages
        ],
    )


@router.delete("/conversations/{conversation_id}")
async def archive_conversation(
    conversation_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Archive (soft-delete) a conversation."""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user_id,
    )
    conversation = (await db.execute(stmt)).scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.status = "archived"
    return {"message": "Conversation archived"}


def _build_assistant_context(business: Business, profile_content: Optional[str]) -> str:
    """Build additional context for the assistant based on the business."""
    parts = []

    if profile_content:
        parts.append(
            f"## Business Profile\n\n{profile_content}"
        )
    else:
        parts.append(
            f"## Business: {business.name}\n\n"
            f"No profile has been built yet. The user should onboard first "
            f"so you have context about their business."
        )

    return "\n\n".join(parts)
