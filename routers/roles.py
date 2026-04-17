from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from access import AccessContext, get_access_context
from database import get_db
from models import Permission, Role, RolePermission
from permission_rules import (
    can_assign_permission_key,
    can_manage_role_permissions,
    can_view_role,
    permission_key_scope,
)
from schemas import PermissionRead, RolePermissionAttach, RoleRead

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("/", response_model=list[RoleRead])
async def list_roles(
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    tier: str | None = Query(None, description="Filter by tier: admin, partner, customer"),
) -> list[Role]:
    stmt = select(Role).order_by(Role.id)
    if not ctx.is_admin:
        if ctx.tier == "partner":
            stmt = stmt.where(Role.tier.in_(("partner", "customer")))
        elif ctx.tier == "customer":
            stmt = stmt.where(Role.tier == "customer")
        else:
            return []
    if tier is not None:
        if not ctx.is_admin and tier == "admin":
            return []
        stmt = stmt.where(Role.tier == tier)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{role_id}/permissions", response_model=list[PermissionRead])
async def list_role_permissions(
    role_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> list[Permission]:
    role = await db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if not can_view_role(
        is_admin=ctx.is_admin,
        caller_tier=ctx.tier,
        target_role=role,
    ):
        raise HTTPException(status_code=403, detail="Not allowed to view this role.")
    stmt = (
        select(Permission)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.key)
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    if ctx.is_admin:
        return rows
    return [
        p
        for p in rows
        if can_assign_permission_key(
            is_admin=ctx.is_admin,
            caller_tier=ctx.tier,
            permission_key=p.key,
        )
    ]


@router.post("/{role_id}/permissions", status_code=201)
async def attach_role_permission(
    role_id: int,
    payload: RolePermissionAttach,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    role = await db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if not can_manage_role_permissions(
        is_admin=ctx.is_admin,
        caller_tier=ctx.tier,
        caller_role_name=ctx.role.name,
        target_role=role,
    ):
        raise HTTPException(status_code=403, detail="Cannot modify permissions for this role.")
    perm = await db.get(Permission, payload.permission_id)
    if perm is None:
        raise HTTPException(status_code=400, detail="Invalid permission_id.")
    if not can_assign_permission_key(
        is_admin=ctx.is_admin,
        caller_tier=ctx.tier,
        permission_key=perm.key,
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Cannot assign permission scope {permission_key_scope(perm.key)} with this account.",
        )
    row = RolePermission(role_id=role_id, permission_id=payload.permission_id)
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail="This permission is already attached to the role.",
        ) from e


@router.delete("/{role_id}/permissions/{permission_id}", status_code=204)
async def detach_role_permission(
    role_id: int,
    permission_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    role = await db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if not can_manage_role_permissions(
        is_admin=ctx.is_admin,
        caller_tier=ctx.tier,
        caller_role_name=ctx.role.name,
        target_role=role,
    ):
        raise HTTPException(status_code=403, detail="Cannot modify permissions for this role.")
    perm = await db.get(Permission, permission_id)
    if perm is None:
        raise HTTPException(status_code=400, detail="Invalid permission_id.")
    if not can_assign_permission_key(
        is_admin=ctx.is_admin,
        caller_tier=ctx.tier,
        permission_key=perm.key,
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Cannot modify permission scope {permission_key_scope(perm.key)} with this account.",
        )
    result = await db.execute(
        delete(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="This permission is not attached to the role.")


@router.get("/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> Role:
    role = await db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if not can_view_role(
        is_admin=ctx.is_admin,
        caller_tier=ctx.tier,
        target_role=role,
    ):
        raise HTTPException(status_code=403, detail="Not allowed to view this role.")
    return role
