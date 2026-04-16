from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from access import (
    AccessContext,
    effective_partner_id,
    ensure_user_resource,
    get_access_context,
    users_scope_statement,
    validate_user_create_payload,
)
from database import get_db
from deps import get_current_user
from me import build_user_me
from models import Customer, Partner, Role, User
from role_utils import assert_user_scope_db
from schemas import UserCreate, UserRead, UserMe, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserRead])
async def list_users(
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    partner_id: int | None = Query(None, description="Admin only: filter"),
    customer_id: int | None = Query(None, description="Admin only: filter"),
    role_id: int | None = Query(None, description="Admin only: filter"),
) -> list[User]:
    base = await users_scope_statement(ctx, db)
    stmt = base.order_by(User.id)
    if ctx.is_admin:
        if partner_id is not None:
            stmt = stmt.where(User.partner_id == partner_id)
        if customer_id is not None:
            stmt = stmt.where(User.customer_id == customer_id)
        if role_id is not None:
            stmt = stmt.where(User.role_id == role_id)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/me", response_model=UserMe)
async def read_me(
    current: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> UserMe:
    """Same payload as `GET /auth/me` — requires JWT."""
    return await build_user_me(db, current)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await ensure_user_resource(ctx, db, user)
    return user


@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    payload: UserCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> User:
    await validate_user_create_payload(
        ctx,
        db,
        partner_id=payload.partner_id,
        customer_id=payload.customer_id,
    )
    if await db.get(Role, payload.role_id) is None:
        raise HTTPException(status_code=400, detail="Invalid role_id.")
    if payload.partner_id is not None:
        if await db.get(Partner, payload.partner_id) is None:
            raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    if payload.customer_id is not None:
        if await db.get(Customer, payload.customer_id) is None:
            raise HTTPException(status_code=400, detail="Customer does not exist for customer_id.")
    user = User(**payload.model_dump())
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not create user.") from e
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await ensure_user_resource(ctx, db, user)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(user, field, value)
    assert_user_scope_db(user.partner_id, user.customer_id)
    if await db.get(Role, user.role_id) is None:
        raise HTTPException(status_code=400, detail="Invalid role_id.")
    if user.partner_id is not None and await db.get(Partner, user.partner_id) is None:
        raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    if user.customer_id is not None and await db.get(Customer, user.customer_id) is None:
        raise HTTPException(status_code=400, detail="Customer does not exist for customer_id.")
    if ctx.tier == "partner" and updates.get("partner_id") not in (None, user.partner_id):
        raise HTTPException(status_code=403, detail="Cannot move users to another partner.")
    if ctx.tier == "partner" and "customer_id" in updates:
        cid = updates["customer_id"]
        if cid is not None:
            cust = await db.get(Customer, cid)
            ep = await effective_partner_id(db, ctx.user)
            if cust is None or ep is None or cust.partner_id != ep:
                raise HTTPException(status_code=403, detail="Invalid customer for your partner.")
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not update user.") from e
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await ensure_user_resource(ctx, db, user)
    if ctx.tier == "customer":
        raise HTTPException(status_code=403, detail="Cannot delete users with this account type.")
    await db.delete(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not delete user.") from e
