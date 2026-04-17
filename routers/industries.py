from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Industry
from schemas import IndustryRead

router = APIRouter(prefix="/industries", tags=["industries"])


@router.get("/", response_model=list[IndustryRead])
async def list_industries(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    active_only: bool = Query(True),
) -> list[Industry]:
    stmt = select(Industry).order_by(Industry.sort_order, Industry.name)
    if active_only:
        stmt = stmt.where(Industry.is_active.is_(True))
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
