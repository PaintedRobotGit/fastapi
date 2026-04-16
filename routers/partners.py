from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Customer, Partner, Plan
from schemas import PartnerCreate, PartnerRead, PartnerUpdate, PartnerWithCustomersRead

router = APIRouter(prefix="/partners", tags=["partners"])


@router.get("/", response_model=list[PartnerRead])
async def list_partners(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[Partner]:
    result = await db.execute(select(Partner).order_by(Partner.id).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.get("/{partner_id}/customers", response_model=PartnerWithCustomersRead)
async def get_partner_with_customers(
    partner_id: int, db: AsyncSession = Depends(get_db)
) -> PartnerWithCustomersRead:
    partner = await db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    res = await db.execute(
        select(Customer).where(Customer.partner_id == partner_id).order_by(Customer.id)
    )
    customers = list(res.scalars().all())
    return PartnerWithCustomersRead(partner=partner, customers=customers)


@router.get("/{partner_id}", response_model=PartnerRead)
async def get_partner(partner_id: int, db: AsyncSession = Depends(get_db)) -> Partner:
    partner = await db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    return partner


@router.post("/", response_model=PartnerRead, status_code=201)
async def create_partner(payload: PartnerCreate, db: AsyncSession = Depends(get_db)) -> Partner:
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
    partner_id: int, payload: PartnerUpdate, db: AsyncSession = Depends(get_db)
) -> Partner:
    partner = await db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
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
async def delete_partner(partner_id: int, db: AsyncSession = Depends(get_db)) -> None:
    partner = await db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    await db.delete(partner)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not delete partner.") from e
