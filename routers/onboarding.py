from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from deps import get_current_user
from me import build_user_me
from models import User
from routers.auth import _create_partner_and_balance
from schemas import OnboardingCompleteRequest, UserMe

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/complete", response_model=UserMe)
async def complete_onboarding(
    payload: OnboardingCompleteRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserMe:
    if current.onboarding_completed_at is not None:
        raise HTTPException(status_code=409, detail="Onboarding already completed.")
    if current.partner_id is not None:
        raise HTTPException(status_code=409, detail="User already belongs to a partner.")

    partner = await _create_partner_and_balance(
        db,
        name=payload.agency_name,
        email=current.email,
        country=payload.country,
    )
    current.partner_id = partner.id
    current.onboarding_completed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(current)
    return await build_user_me(db, current)
