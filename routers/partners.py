from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from access import (
    AccessContext,
    effective_partner_id,
    ensure_partner_resource,
    get_access_context,
    require_admin,
)
from database import get_db
from models import Customer, Partner, Plan
from schemas import PartnerCreate, PartnerRead, PartnerUpdate, PartnerWithCustomersRead

router = APIRouter(prefix="/partners", tags=["partners"])


@router.get("/", response_model=list[PartnerRead])
async def list_partners(
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: str | None = Query(None, description="Filter by partner status"),
    omit_archived: bool = Query(
        True,
        description="Exclude partners with archived_at set (admin only; always shown for own org).",
    ),
) -> list[Partner]:
    if ctx.is_admin:
        stmt = select(Partner).order_by(Partner.id)
        if status is not None:
            stmt = stmt.where(Partner.status == status)
        if omit_archived:
            stmt = stmt.where(Partner.archived_at.is_(None))
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())
    ep = await effective_partner_id(db, ctx.user)
    if ep is None:
        return []
    stmt = select(Partner).where(Partner.id == ep)
    if status is not None:
        stmt = stmt.where(Partner.status == status)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{partner_id}/customers", response_model=PartnerWithCustomersRead)
async def get_partner_with_customers(
    partner_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> PartnerWithCustomersRead:
    await ensure_partner_resource(ctx, db, partner_id)
    partner = await db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    res = await db.execute(
        select(Customer).where(Customer.partner_id == partner_id).order_by(Customer.id)
    )
    customers = list(res.scalars().all())
    return PartnerWithCustomersRead(partner=partner, customers=customers)


@router.get("/{partner_id}", response_model=PartnerRead)
async def get_partner(
    partner_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> Partner:
    await ensure_partner_resource(ctx, db, partner_id)
    partner = await db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    return partner


@router.post("/", response_model=PartnerRead, status_code=201)
async def create_partner(
    payload: PartnerCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> Partner:
    require_admin(ctx)
    if await db.get(Plan, payload.plan_id) is None:
        raise HTTPException(status_code=400, detail="Invalid plan_id.")
    partner = Partner(**payload.model_dump())
    db.add(partner)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail="Could not create partner (duplicate slug or other constraint).",
        ) from e
    await db.refresh(partner)
    return partner


@router.patch("/{partner_id}", response_model=PartnerRead)
async def update_partner(
    partner_id: int,
    payload: PartnerUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> Partner:
    await ensure_partner_resource(ctx, db, partner_id)
    partner = await db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    if ctx.tier == "customer":
        raise HTTPException(status_code=403, detail="Cannot update partner with this account type.")
    updates = payload.model_dump(exclude_unset=True)
    if "plan_id" in updates and await db.get(Plan, updates["plan_id"]) is None:
        raise HTTPException(status_code=400, detail="Invalid plan_id.")
    for field, value in updates.items():
        setattr(partner, field, value)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not update partner.") from e
    await db.refresh(partner)
    return partner


@router.delete("/{partner_id}", status_code=204)
async def delete_partner(
    partner_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    require_admin(ctx)
    partner = await db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    await db.delete(partner)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not delete partner.") from e
