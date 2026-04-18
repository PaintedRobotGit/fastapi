from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from access import AccessContext, effective_partner_id, get_access_context
from database import get_db
from models import ChatMessage, ChatSession, ChatSessionShare, Customer, User
from schemas import (
    ChatMessageCreate,
    ChatMessageRead,
    ChatSessionCreate,
    ChatSessionRead,
    ChatSessionShareCreate,
    ChatSessionShareRead,
    ChatSessionUpdate,
)

router = APIRouter(prefix="/chat", tags=["chat"])


async def _get_session_or_404(db: AsyncSession, session_id: int) -> ChatSession:
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


async def _ensure_can_read(ctx: AccessContext, db: AsyncSession, session: ChatSession) -> None:
    """Owner, anyone it's shared with (same partner), or admin."""
    if ctx.is_admin:
        return
    ep = await effective_partner_id(db, ctx.user)
    if ep is None or session.partner_id != ep:
        raise HTTPException(status_code=403, detail="Not allowed to access this chat session.")
    if session.user_id == ctx.user.id:
        return
    share = await db.get(ChatSessionShare, {"session_id": session.id, "shared_with_user_id": ctx.user.id})
    if share is None:
        raise HTTPException(status_code=403, detail="Not allowed to access this chat session.")


async def _ensure_is_owner(ctx: AccessContext, session: ChatSession) -> None:
    """Only the owner or admin can mutate a session or its shares."""
    if ctx.is_admin:
        return
    if session.user_id != ctx.user.id:
        raise HTTPException(status_code=403, detail="Only the session owner can perform this action.")


# --- Sessions ---


@router.get("/sessions", response_model=list[ChatSessionRead])
async def list_chat_sessions(
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    shared_with_me: bool = Query(False, description="Return sessions shared with me instead of my own"),
    customer_id: int | None = Query(None, description="Filter by customer context"),
) -> list[ChatSession]:
    ep = await effective_partner_id(db, ctx.user)
    if not ctx.is_admin and ep is None:
        return []

    if shared_with_me and not ctx.is_admin:
        share_sub = select(ChatSessionShare.session_id).where(
            ChatSessionShare.shared_with_user_id == ctx.user.id
        )
        stmt = (
            select(ChatSession)
            .where(ChatSession.id.in_(share_sub), ChatSession.archived_at.is_(None))
            .order_by(ChatSession.updated_at.desc())
        )
    else:
        stmt = select(ChatSession).order_by(ChatSession.updated_at.desc())
        if not ctx.is_admin:
            stmt = stmt.where(ChatSession.user_id == ctx.user.id, ChatSession.archived_at.is_(None))

    if customer_id is not None:
        stmt = stmt.where(ChatSession.customer_id == customer_id)

    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/sessions/{session_id}", response_model=ChatSessionRead)
async def get_chat_session(
    session_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> ChatSession:
    session = await _get_session_or_404(db, session_id)
    await _ensure_can_read(ctx, db, session)
    return session


@router.post("/sessions", response_model=ChatSessionRead, status_code=201)
async def create_chat_session(
    payload: ChatSessionCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> ChatSession:
    ep = await effective_partner_id(db, ctx.user)
    if ep is None:
        raise HTTPException(status_code=403, detail="User is not associated with a partner.")
    if payload.customer_id is not None:
        cust = await db.get(Customer, payload.customer_id)
        if cust is None or cust.partner_id != ep:
            raise HTTPException(status_code=400, detail="Invalid customer_id.")
    session = ChatSession(
        partner_id=ep,
        user_id=ctx.user.id,
        customer_id=payload.customer_id,
        title=payload.title,
    )
    db.add(session)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not create chat session.") from e
    await db.refresh(session)
    return session


@router.patch("/sessions/{session_id}", response_model=ChatSessionRead)
async def update_chat_session(
    session_id: int,
    payload: ChatSessionUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> ChatSession:
    session = await _get_session_or_404(db, session_id)
    await _ensure_is_owner(ctx, session)
    if payload.customer_id is not None:
        ep = await effective_partner_id(db, ctx.user)
        cust = await db.get(Customer, payload.customer_id)
        if cust is None or cust.partner_id != ep:
            raise HTTPException(status_code=400, detail="Invalid customer_id.")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(session, field, value)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not update chat session.") from e
    await db.refresh(session)
    return session


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_chat_session(
    session_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    session = await _get_session_or_404(db, session_id)
    await _ensure_is_owner(ctx, session)
    await db.delete(session)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not delete chat session.") from e


# --- Messages ---


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageRead])
async def list_chat_messages(
    session_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[ChatMessage]:
    session = await _get_session_or_404(db, session_id)
    await _ensure_can_read(ctx, db, session)
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageRead, status_code=201)
async def create_chat_message(
    session_id: int,
    payload: ChatMessageCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> ChatMessage:
    session = await _get_session_or_404(db, session_id)
    await _ensure_can_read(ctx, db, session)
    message = ChatMessage(
        session_id=session_id,
        partner_id=session.partner_id,
        role=payload.role,
        content=payload.content,
        model=payload.model,
    )
    db.add(message)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not create message.") from e
    await db.refresh(message)
    return message


# --- Shares ---


@router.get("/sessions/{session_id}/shares", response_model=list[ChatSessionShareRead])
async def list_chat_session_shares(
    session_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> list[ChatSessionShare]:
    session = await _get_session_or_404(db, session_id)
    await _ensure_can_read(ctx, db, session)
    stmt = select(ChatSessionShare).where(ChatSessionShare.session_id == session_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/sessions/{session_id}/shares", response_model=ChatSessionShareRead, status_code=201)
async def share_chat_session(
    session_id: int,
    payload: ChatSessionShareCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionShare:
    session = await _get_session_or_404(db, session_id)
    await _ensure_is_owner(ctx, session)
    target = await db.get(User, payload.shared_with_user_id)
    if target is None:
        raise HTTPException(status_code=400, detail="User not found.")
    target_ep = await effective_partner_id(db, target)
    if target_ep != session.partner_id:
        raise HTTPException(status_code=400, detail="Can only share with users in the same partner account.")
    if target.id == ctx.user.id:
        raise HTTPException(status_code=400, detail="Cannot share a session with yourself.")
    share = ChatSessionShare(
        session_id=session_id,
        shared_with_user_id=payload.shared_with_user_id,
        shared_by_user_id=ctx.user.id,
    )
    db.add(share)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Already shared with this user.")
    await db.refresh(share)
    return share


@router.delete("/sessions/{session_id}/shares/{user_id}", status_code=204)
async def revoke_chat_session_share(
    session_id: int,
    user_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    session = await _get_session_or_404(db, session_id)
    await _ensure_is_owner(ctx, session)
    share = await db.get(ChatSessionShare, {"session_id": session_id, "shared_with_user_id": user_id})
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found.")
    await db.delete(share)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not revoke share.") from e
