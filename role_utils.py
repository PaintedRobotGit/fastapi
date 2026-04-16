"""Helpers for resolving default roles by tier (seeded `roles` rows)."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Role


async def get_role_by_name(db: AsyncSession, name: str) -> Role | None:
    r = await db.execute(select(Role).where(Role.name == name))
    return r.scalars().first()


def assert_at_most_one_partner_customer(partner_id: int | None, customer_id: int | None) -> None:
    if partner_id is not None and customer_id is not None:
        raise HTTPException(
            status_code=400,
            detail="partner_id and customer_id cannot both be set.",
        )


async def resolve_role_id_for_signup(
    db: AsyncSession,
    *,
    partner_id: int | None,
    customer_id: int | None,
    role_id: int | None,
) -> int:
    """Register / OAuth account creation: explicit role_id, defaults, or admin-tier when unscoped."""
    assert_at_most_one_partner_customer(partner_id, customer_id)
    if role_id is not None:
        role = await db.get(Role, role_id)
        if role is None:
            raise HTTPException(status_code=400, detail="Invalid role_id.")
        if partner_id is None and customer_id is None and role.tier != "admin":
            raise HTTPException(
                status_code=400,
                detail="When neither partner_id nor customer_id is set, role_id must reference an admin-tier role.",
            )
        return role_id
    if partner_id is not None:
        r = await get_role_by_name(db, "partner_member")
        if r is None:
            raise HTTPException(
                status_code=503,
                detail="Default role 'partner_member' is missing; seed the roles table.",
            )
        return r.id
    if customer_id is not None:
        r = await get_role_by_name(db, "customer_member")
        if r is None:
            raise HTTPException(
                status_code=503,
                detail="Default role 'customer_member' is missing; seed the roles table.",
            )
        return r.id
    raise HTTPException(
        status_code=400,
        detail="role_id is required when neither partner_id nor customer_id is set.",
    )


def assert_user_scope_db(partner_id: int | None, customer_id: int | None) -> None:
    """DB constraint: at most one of partner_id, customer_id may be set."""
    if partner_id is not None and customer_id is not None:
        raise HTTPException(
            status_code=400,
            detail="partner_id and customer_id cannot both be set.",
        )
