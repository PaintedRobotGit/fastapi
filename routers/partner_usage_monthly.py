from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Partner, PartnerUsageMonthly
from schemas import PartnerUsageMonthlyCreate, PartnerUsageMonthlyRead, PartnerUsageMonthlyUpdate

router = APIRouter(prefix="/partner-usage-monthly", tags=["partner-usage-monthly"])


@router.get("/", response_model=list[PartnerUsageMonthlyRead])
async def list_partner_usage_monthly(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    partner_id: int | None = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
) -> list[PartnerUsageMonthly]:
    stmt = select(PartnerUsageMonthly).order_by(
        PartnerUsageMonthly.year.desc(),
        PartnerUsageMonthly.month.desc(),
        PartnerUsageMonthly.partner_id,
    )
    if partner_id is not None:
        stmt = stmt.where(PartnerUsageMonthly.partner_id == partner_id)
    if year is not None:
        stmt = stmt.where(PartnerUsageMonthly.year == year)
    if month is not None:
        stmt = stmt.where(PartnerUsageMonthly.month == month)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/", response_model=PartnerUsageMonthlyRead, status_code=201)
async def create_partner_usage_monthly(
    payload: PartnerUsageMonthlyCreate, db: AsyncSession = Depends(get_db)
) -> PartnerUsageMonthly:
    if await db.get(Partner, payload.partner_id) is None:
        raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    row = PartnerUsageMonthly(partner_id=payload.partner_id, year=payload.year, month=payload.month)
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail="Row already exists for this partner/year/month (use PATCH on existing row).",
        ) from e
    await db.refresh(row)
    return row


@router.get("/{row_id}", response_model=PartnerUsageMonthlyRead)
async def get_partner_usage_monthly_row(row_id: int, db: AsyncSession = Depends(get_db)) -> PartnerUsageMonthly:
    row = await db.get(PartnerUsageMonthly, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Partner usage monthly row not found")
    return row


@router.patch("/{row_id}", response_model=PartnerUsageMonthlyRead)
async def update_partner_usage_monthly(
    row_id: int, payload: PartnerUsageMonthlyUpdate, db: AsyncSession = Depends(get_db)
) -> PartnerUsageMonthly:
    row = await db.get(PartnerUsageMonthly, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Partner usage monthly row not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(row, field, value)
    if "total_tokens" not in updates and ("input_tokens" in updates or "output_tokens" in updates):
        row.total_tokens = int(row.input_tokens) + int(row.output_tokens)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not update partner usage monthly.") from e
    await db.refresh(row)
    return row
