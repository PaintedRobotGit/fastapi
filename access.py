"""JWT-backed access control: tier (admin / partner / customer) and row-level scope."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from deps import http_bearer
from models import AiTokenUsage, Customer, PartnerTokenBalance, Role, User
from security import safe_decode_access_token


@dataclass
class AccessContext:
    user: User
    role: Role

    @property
    def tier(self) -> str:
        return self.role.tier

    @property
    def is_admin(self) -> bool:
        return self.role.tier == "admin"


async def build_access_context(token: str, db: AsyncSession) -> AccessContext:
    """Validate JWT, load user + role, configure all RLS session vars, return AccessContext.

    Raises ValueError on any auth failure. Framework-agnostic — callable from FastAPI deps
    or MCP tools without touching FastAPI's request/response machinery.
    """
    payload = safe_decode_access_token(token)
    if not payload or "sub" not in payload:
        raise ValueError("Invalid or expired token")
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as e:
        raise ValueError("Invalid token subject") from e

    # Set user_id first — RLS on the users table requires it before we can query our own row.
    await db.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": str(user_id)},
    )
    user = await db.get(User, user_id)
    if user is None or user.status != "active":
        raise ValueError("User not found or inactive")

    role = await db.get(Role, user.role_id)
    if role is None:
        raise ValueError("User role not found")

    ctx = AccessContext(user=user, role=role)
    await db.execute(
        text("""
            SELECT
                set_config('app.bypass_rls',          :bypass,      true),
                set_config('app.current_partner_id',  :partner_id,  true),
                set_config('app.current_customer_id', :customer_id, true)
        """),
        {
            "bypass":      "true" if ctx.is_admin else "false",
            "partner_id":  str(user.partner_id or ""),
            "customer_id": str(user.customer_id or ""),
        },
    )
    return ctx


async def get_access_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: AsyncSession = Depends(get_db),
) -> AccessContext:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return await build_access_context(credentials.credentials, db)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


async def effective_partner_id(db: AsyncSession, user: User) -> int | None:
    """Partner org id: direct partner user, or parent partner of a customer user."""
    if user.partner_id is not None:
        return user.partner_id
    if user.customer_id is not None:
        cust = await db.get(Customer, user.customer_id)
        return cust.partner_id if cust else None
    return None


def require_admin(ctx: AccessContext) -> None:
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")


async def ensure_partner_resource(ctx: AccessContext, db: AsyncSession, partner_id: int) -> None:
    if ctx.is_admin:
        return
    pid = await effective_partner_id(db, ctx.user)
    if pid is None or partner_id != pid:
        raise HTTPException(status_code=403, detail="Not allowed to access this partner.")


async def ensure_customer_resource(ctx: AccessContext, db: AsyncSession, customer: Customer) -> None:
    if ctx.is_admin:
        return
    if ctx.tier == "partner":
        ep = await effective_partner_id(db, ctx.user)
        if ep is None or customer.partner_id != ep:
            raise HTTPException(status_code=403, detail="Not allowed to access this customer.")
        return
    if ctx.tier == "customer":
        if ctx.user.customer_id != customer.id:
            raise HTTPException(status_code=403, detail="Not allowed to access this customer.")
        return
    raise HTTPException(status_code=403, detail="Forbidden.")


async def ensure_user_resource(ctx: AccessContext, db: AsyncSession, target: User) -> None:
    if ctx.is_admin:
        return
    if ctx.tier == "partner":
        ep = await effective_partner_id(db, ctx.user)
        if ep is None:
            raise HTTPException(status_code=403, detail="Forbidden.")
        if target.partner_id == ep:
            return
        if target.customer_id is not None:
            cust = await db.get(Customer, target.customer_id)
            if cust and cust.partner_id == ep:
                return
        raise HTTPException(status_code=403, detail="Not allowed to access this user.")
    if ctx.tier == "customer":
        if target.id == ctx.user.id:
            return
        if ctx.user.customer_id is not None and target.customer_id == ctx.user.customer_id:
            return
        raise HTTPException(status_code=403, detail="Not allowed to access this user.")
    raise HTTPException(status_code=403, detail="Forbidden.")


async def users_scope_statement(ctx: AccessContext, db: AsyncSession):
    """SELECT for users visible to this caller (apply .order_by etc. in router)."""
    if ctx.is_admin:
        return select(User)
    if ctx.tier == "partner":
        ep = await effective_partner_id(db, ctx.user)
        if ep is None:
            return select(User).where(User.id == -1)
        cust_sub = select(Customer.id).where(Customer.partner_id == ep)
        return select(User).where(or_(User.partner_id == ep, User.customer_id.in_(cust_sub)))
    if ctx.tier == "customer":
        if ctx.user.customer_id is None:
            return select(User).where(User.id == -1)
        return select(User).where(User.customer_id == ctx.user.customer_id)
    return select(User).where(User.id == -1)


async def validate_user_create_payload(
    ctx: AccessContext,
    db: AsyncSession,
    *,
    partner_id: int | None,
    customer_id: int | None,
) -> None:
    if ctx.is_admin:
        return
    if ctx.tier == "customer":
        raise HTTPException(status_code=403, detail="Cannot create users with this account type.")
    if ctx.tier == "partner":
        ep = await effective_partner_id(db, ctx.user)
        if ep is None:
            raise HTTPException(status_code=403, detail="Forbidden.")
        if partner_id is not None and partner_id != ep:
            raise HTTPException(status_code=403, detail="Cannot assign users outside your partner.")
        if customer_id is not None:
            cust = await db.get(Customer, customer_id)
            if cust is None or cust.partner_id != ep:
                raise HTTPException(status_code=403, detail="Customer must belong to your partner.")
        if partner_id is None and customer_id is None:
            raise HTTPException(status_code=400, detail="Specify partner_id or customer_id for the new user.")
        return
    raise HTTPException(status_code=403, detail="Forbidden.")


async def ensure_ai_token_usage_resource(ctx: AccessContext, db: AsyncSession, row: AiTokenUsage) -> None:
    if ctx.is_admin:
        return
    ep = await effective_partner_id(db, ctx.user)
    if ctx.tier == "partner":
        if ep is None or row.partner_id != ep:
            raise HTTPException(status_code=403, detail="Not allowed to access this usage log.")
        return
    if ctx.tier == "customer":
        if (
            ctx.user.customer_id is None
            or ep is None
            or row.partner_id != ep
            or row.customer_id != ctx.user.customer_id
        ):
            raise HTTPException(status_code=403, detail="Not allowed to access this usage log.")
        return
    raise HTTPException(status_code=403, detail="Forbidden.")


async def ensure_partner_token_balance_resource(
    ctx: AccessContext, db: AsyncSession, row: PartnerTokenBalance
) -> None:
    if ctx.is_admin:
        return
    ep = await effective_partner_id(db, ctx.user)
    if ep is None or row.partner_id != ep:
        raise HTTPException(status_code=403, detail="Not allowed to access this usage aggregate.")


async def enforce_ai_usage_write(
    ctx: AccessContext, db: AsyncSession, *, partner_id: int, customer_id: int | None
) -> None:
    if ctx.is_admin:
        return
    ep = await effective_partner_id(db, ctx.user)
    if ctx.tier == "partner":
        if ep is None or partner_id != ep:
            raise HTTPException(status_code=403, detail="Cannot log usage for another partner.")
        if customer_id is not None:
            cust = await db.get(Customer, customer_id)
            if cust is None or cust.partner_id != ep:
                raise HTTPException(status_code=400, detail="customer_id must belong to your partner.")
        return
    if ctx.tier == "customer":
        if (
            ctx.user.customer_id is None
            or ep is None
            or partner_id != ep
            or customer_id != ctx.user.customer_id
        ):
            raise HTTPException(status_code=403, detail="Cannot log usage outside your customer account.")
        return
    raise HTTPException(status_code=403, detail="Forbidden.")


async def enforce_partner_scope_id(ctx: AccessContext, db: AsyncSession, partner_id: int) -> None:
    """Non-admins writing rows keyed by partner_id (e.g. monthly usage create)."""
    if ctx.is_admin:
        return
    ep = await effective_partner_id(db, ctx.user)
    if ep is None or partner_id != ep:
        raise HTTPException(status_code=403, detail="Cannot modify data for another partner.")
