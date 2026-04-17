from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from access import AccessContext, get_access_context
from database import get_db
from models import Permission
from permission_rules import can_assign_permission_key, permission_filter_for_caller
from schemas import PermissionRead

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("/", response_model=list[PermissionRead])
async def list_permissions(
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
) -> list[Permission]:
    stmt = select(Permission).order_by(Permission.key)
    filt = permission_filter_for_caller(is_admin=ctx.is_admin, caller_tier=ctx.tier)
    if filt is not None:
        stmt = stmt.where(filt)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{permission_id}", response_model=PermissionRead)
async def get_permission(
    permission_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> Permission:
    row = await db.get(Permission, permission_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Permission not found")
    if not can_assign_permission_key(
        is_admin=ctx.is_admin,
        caller_tier=ctx.tier,
        permission_key=row.key,
    ):
        raise HTTPException(status_code=403, detail="Not allowed to view this permission.")
    return row
