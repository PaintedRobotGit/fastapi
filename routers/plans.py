from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Plan
from schemas import PlanRead

router = APIRouter(
    prefix="/plans",
    tags=["plans"],
)


@router.get("/", response_model=list[PlanRead])
async def list_plans(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    active_only: bool = Query(True, description="Only return active plans"),
) -> list[Plan]:
    stmt = select(Plan).order_by(Plan.id)
    if active_only:
        stmt = stmt.where(Plan.is_active.is_(True))
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{plan_id}", response_model=PlanRead)
async def get_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
) -> Plan:
    row = await db.get(Plan, plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return row
