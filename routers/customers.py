from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from access import (
    AccessContext,
    effective_partner_id,
    ensure_customer_resource,
    get_access_context,
)
from database import get_db
from models import Customer, Partner
from schemas import CustomerCreate, CustomerRead, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/", response_model=list[CustomerRead])
async def list_customers(
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    partner_id: int | None = Query(None, description="Admin only: filter by partner id"),
) -> list[Customer]:
    stmt = select(Customer).order_by(Customer.id)
    if ctx.is_admin:
        if partner_id is not None:
            stmt = stmt.where(Customer.partner_id == partner_id)
    elif ctx.tier == "partner":
        ep = await effective_partner_id(db, ctx.user)
        if ep is None:
            return []
        stmt = stmt.where(Customer.partner_id == ep)
    else:
        if ctx.user.customer_id is None:
            return []
        stmt = stmt.where(Customer.id == ctx.user.customer_id)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await ensure_customer_resource(ctx, db, customer)
    return customer


@router.post("/", response_model=CustomerRead, status_code=201)
async def create_customer(
    payload: CustomerCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    if ctx.tier == "customer":
        raise HTTPException(status_code=403, detail="Cannot create customers with this account type.")
    if ctx.is_admin:
        parent = await db.get(Partner, payload.partner_id)
        if parent is None:
            raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    else:
        ep = await effective_partner_id(db, ctx.user)
        if ep is None or payload.partner_id != ep:
            raise HTTPException(status_code=403, detail="Cannot create customers for another partner.")
    customer = Customer(**payload.model_dump())
    db.add(customer)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not create customer.") from e
    await db.refresh(customer)
    return customer


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await ensure_customer_resource(ctx, db, customer)
    if ctx.tier == "customer":
        raise HTTPException(status_code=403, detail="Cannot update customer with this account type.")
    updates = payload.model_dump(exclude_unset=True)
    if "partner_id" in updates:
        if ctx.tier == "partner":
            raise HTTPException(status_code=403, detail="Cannot reassign customer to another partner.")
        parent = await db.get(Partner, updates["partner_id"])
        if parent is None:
            raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    for field, value in updates.items():
        setattr(customer, field, value)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not update customer.") from e
    await db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await ensure_customer_resource(ctx, db, customer)
    if ctx.tier == "customer":
        raise HTTPException(status_code=403, detail="Cannot delete customer with this account type.")
    await db.delete(customer)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not delete customer.") from e
