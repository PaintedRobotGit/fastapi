from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Permission, Role, RolePermission
from schemas import PermissionRead, RoleRead

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("/", response_model=list[RoleRead])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    tier: str | None = Query(None, description="Filter by tier: admin, partner, customer"),
) -> list[Role]:
    stmt = select(Role).order_by(Role.id)
    if tier is not None:
        stmt = stmt.where(Role.tier == tier)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{role_id}/permissions", response_model=list[PermissionRead])
async def list_role_permissions(role_id: int, db: AsyncSession = Depends(get_db)) -> list[Permission]:
    role = await db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    stmt = (
        select(Permission)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.key)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{role_id}", response_model=RoleRead)
async def get_role(role_id: int, db: AsyncSession = Depends(get_db)) -> Role:
    role = await db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role
