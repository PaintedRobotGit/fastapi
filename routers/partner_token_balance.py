from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from access import (
    AccessContext,
    effective_partner_id,
    enforce_partner_scope_id,
    ensure_partner_token_balance_resource,
    get_access_context,
)
from database import get_db
from models import Partner, PartnerTokenBalance
from schemas import PartnerTokenBalanceCreate, PartnerTokenBalanceRead, PartnerTokenBalanceUpdate

router = APIRouter(prefix="/partner-token-balance", tags=["partner-token-balance"])


@router.get("/", response_model=list[PartnerTokenBalanceRead])
async def list_partner_token_balance(
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    partner_id: int | None = Query(None, description="Admin only: filter by partner"),
    billable_period: date | None = Query(None, description="Filter by billing month (first day)"),
) -> list[PartnerTokenBalance]:
    stmt = select(PartnerTokenBalance).order_by(
        PartnerTokenBalance.billable_period.desc(),
        PartnerTokenBalance.partner_id,
    )
    if ctx.is_admin:
        if partner_id is not None:
            stmt = stmt.where(PartnerTokenBalance.partner_id == partner_id)
    else:
        ep = await effective_partner_id(db, ctx.user)
        if ep is None:
            return []
        stmt = stmt.where(PartnerTokenBalance.partner_id == ep)
    if billable_period is not None:
        stmt = stmt.where(PartnerTokenBalance.billable_period == billable_period)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/", response_model=PartnerTokenBalanceRead, status_code=201)
async def create_partner_token_balance(
    payload: PartnerTokenBalanceCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> PartnerTokenBalance:
    await enforce_partner_scope_id(ctx, db, payload.partner_id)
    if await db.get(Partner, payload.partner_id) is None:
        raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    remaining = int(payload.included_tokens) - int(payload.tokens_used)
    row = PartnerTokenBalance(
        partner_id=payload.partner_id,
        billable_period=payload.billable_period,
        included_tokens=payload.included_tokens,
        tokens_used=payload.tokens_used,
        tokens_remaining=remaining,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail="Row already exists for this partner and billable_period (use PATCH).",
        ) from e
    await db.refresh(row)
    return row


@router.get("/{partner_id}/{billable_period}", response_model=PartnerTokenBalanceRead)
async def get_partner_token_balance(
    partner_id: int,
    billable_period: date,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> PartnerTokenBalance:
    row = await db.get(
        PartnerTokenBalance,
        {"partner_id": partner_id, "billable_period": billable_period},
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Partner token balance row not found")
    await ensure_partner_token_balance_resource(ctx, db, row)
    return row


@router.patch("/{partner_id}/{billable_period}", response_model=PartnerTokenBalanceRead)
async def update_partner_token_balance(
    partner_id: int,
    billable_period: date,
    payload: PartnerTokenBalanceUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> PartnerTokenBalance:
    row = await db.get(
        PartnerTokenBalance,
        {"partner_id": partner_id, "billable_period": billable_period},
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Partner token balance row not found")
    await ensure_partner_token_balance_resource(ctx, db, row)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(row, field, value)
    if "tokens_remaining" not in updates and (
        "included_tokens" in updates or "tokens_used" in updates
    ):
        row.tokens_remaining = int(row.included_tokens) - int(row.tokens_used)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not update partner token balance.") from e
    await db.refresh(row)
    return row
