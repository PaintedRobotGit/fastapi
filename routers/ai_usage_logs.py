from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AiUsageLog, Customer, Partner
from schemas import AiUsageLogCreate, AiUsageLogRead

router = APIRouter(prefix="/ai-usage-logs", tags=["ai-usage-logs"])


@router.get("/", response_model=list[AiUsageLogRead])
async def list_ai_usage_logs(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    partner_id: int | None = Query(None),
    customer_id: int | None = Query(None),
    created_after: datetime | None = Query(None),
    created_before: datetime | None = Query(None),
) -> list[AiUsageLog]:
    stmt = select(AiUsageLog).order_by(AiUsageLog.created_at.desc())
    if partner_id is not None:
        stmt = stmt.where(AiUsageLog.partner_id == partner_id)
    if customer_id is not None:
        stmt = stmt.where(AiUsageLog.customer_id == customer_id)
    if created_after is not None:
        stmt = stmt.where(AiUsageLog.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(AiUsageLog.created_at <= created_before)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{log_id}", response_model=AiUsageLogRead)
async def get_ai_usage_log(log_id: int, db: AsyncSession = Depends(get_db)) -> AiUsageLog:
    row = await db.get(AiUsageLog, log_id)
    if row is None:
        raise HTTPException(status_code=404, detail="AI usage log not found")
    return row


@router.post("/", response_model=AiUsageLogRead, status_code=201)
async def create_ai_usage_log(
    payload: AiUsageLogCreate, db: AsyncSession = Depends(get_db)
) -> AiUsageLog:
    if await db.get(Partner, payload.partner_id) is None:
        raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    if payload.customer_id is not None:
        cust = await db.get(Customer, payload.customer_id)
        if cust is None:
            raise HTTPException(status_code=400, detail="Customer does not exist for customer_id.")
        if cust.partner_id != payload.partner_id:
            raise HTTPException(status_code=400, detail="customer_id does not belong to partner_id.")
    total = (
        payload.total_tokens
        if payload.total_tokens is not None
        else payload.input_tokens + payload.output_tokens
    )
    row = AiUsageLog(
        partner_id=payload.partner_id,
        customer_id=payload.customer_id,
        model=payload.model,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        total_tokens=total,
        feature=payload.feature,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not create AI usage log.") from e
    await db.refresh(row)
    return row
