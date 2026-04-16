from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from access import (
    AccessContext,
    effective_partner_id,
    enforce_ai_usage_write,
    ensure_ai_token_usage_resource,
    get_access_context,
)
from database import get_db
from models import AiTokenUsage, Customer, Partner
from schemas import AiTokenUsageCreate, AiTokenUsageRead

router = APIRouter(prefix="/ai-token-usage", tags=["ai-token-usage"])


def _default_billable_period() -> date:
    now = datetime.now(timezone.utc)
    return date(now.year, now.month, 1)


@router.get("/", response_model=list[AiTokenUsageRead])
async def list_ai_token_usage(
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    partner_id: int | None = Query(None, description="Admin only: filter by partner"),
    customer_id: int | None = Query(None, description="Admin only: filter by customer"),
    created_after: datetime | None = Query(None),
    created_before: datetime | None = Query(None),
) -> list[AiTokenUsage]:
    stmt = select(AiTokenUsage).order_by(AiTokenUsage.created_at.desc())
    if ctx.is_admin:
        if partner_id is not None:
            stmt = stmt.where(AiTokenUsage.partner_id == partner_id)
        if customer_id is not None:
            stmt = stmt.where(AiTokenUsage.customer_id == customer_id)
    elif ctx.tier == "partner":
        ep = await effective_partner_id(db, ctx.user)
        if ep is None:
            return []
        stmt = stmt.where(AiTokenUsage.partner_id == ep)
    else:
        ep = await effective_partner_id(db, ctx.user)
        if ctx.user.customer_id is None or ep is None:
            return []
        stmt = stmt.where(
            AiTokenUsage.partner_id == ep,
            AiTokenUsage.customer_id == ctx.user.customer_id,
        )
    if created_after is not None:
        stmt = stmt.where(AiTokenUsage.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(AiTokenUsage.created_at <= created_before)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{log_id}", response_model=AiTokenUsageRead)
async def get_ai_token_usage(
    log_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> AiTokenUsage:
    row = await db.get(AiTokenUsage, log_id)
    if row is None:
        raise HTTPException(status_code=404, detail="AI token usage row not found")
    await ensure_ai_token_usage_resource(ctx, db, row)
    return row


@router.post("/", response_model=AiTokenUsageRead, status_code=201)
async def create_ai_token_usage(
    payload: AiTokenUsageCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> AiTokenUsage:
    await enforce_ai_usage_write(
        ctx, db, partner_id=payload.partner_id, customer_id=payload.customer_id
    )
    if await db.get(Partner, payload.partner_id) is None:
        raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    if payload.customer_id is not None:
        cust = await db.get(Customer, payload.customer_id)
        if cust is None:
            raise HTTPException(status_code=400, detail="Customer does not exist for customer_id.")
        if cust.partner_id != payload.partner_id:
            raise HTTPException(status_code=400, detail="customer_id does not belong to partner_id.")
    total = payload.total_tokens
    if total is None:
        total = (
            payload.input_tokens
            + payload.output_tokens
            + payload.cache_read_tokens
            + payload.cache_write_tokens
        )
    billable_period = payload.billable_period or _default_billable_period()
    row = AiTokenUsage(
        partner_id=payload.partner_id,
        customer_id=payload.customer_id,
        model=payload.model,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        cache_read_tokens=payload.cache_read_tokens,
        cache_write_tokens=payload.cache_write_tokens,
        total_tokens=total,
        feature=payload.feature,
        ai_provider=payload.ai_provider,
        provider_request_id=payload.provider_request_id,
        estimated_cost_cents=payload.estimated_cost_cents,
        billable_period=billable_period,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not create AI token usage row.") from e
    await db.refresh(row)
    return row
