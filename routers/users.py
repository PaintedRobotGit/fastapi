from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from deps import get_current_user
from me import build_user_me
from models import Customer, Partner, User
from schemas import UserCreate, UserRead, UserMe, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _assert_user_scope(partner_id: int | None, customer_id: int | None) -> None:
    if (partner_id is None) == (customer_id is None):
        raise HTTPException(
            status_code=400,
            detail="User must belong to exactly one partner or one customer.",
        )


@router.get("/", response_model=list[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    partner_id: int | None = Query(None),
    customer_id: int | None = Query(None),
) -> list[User]:
    stmt = select(User).order_by(User.id)
    if partner_id is not None:
        stmt = stmt.where(User.partner_id == partner_id)
    if customer_id is not None:
        stmt = stmt.where(User.customer_id == customer_id)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/me", response_model=UserMe)
async def read_me(
    current: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> UserMe:
    """Same payload as `GET /auth/me` — current user plus partner/customer context."""
    return await build_user_me(db, current)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=UserRead, status_code=201)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
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
    user_id: int, payload: UserUpdate, db: AsyncSession = Depends(get_db)
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(user, field, value)
    _assert_user_scope(user.partner_id, user.customer_id)
    if user.partner_id is not None and await db.get(Partner, user.partner_id) is None:
        raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    if user.customer_id is not None and await db.get(Customer, user.customer_id) is None:
        raise HTTPException(status_code=400, detail="Customer does not exist for customer_id.")
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not update user.") from e
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)) -> None:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not delete user.") from e
