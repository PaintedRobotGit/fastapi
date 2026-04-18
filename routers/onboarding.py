from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from access import AccessContext, get_access_context
from database import get_db
from me import build_user_me
from partner_utils import create_partner_and_balance
from schemas import OnboardingCompleteRequest, UserMe

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/complete", response_model=UserMe)
async def complete_onboarding(
    payload: OnboardingCompleteRequest,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> UserMe:
    current = ctx.user
    if current.onboarding_completed_at is not None:
        raise HTTPException(status_code=409, detail="Onboarding already completed.")
    if current.partner_id is not None:
        raise HTTPException(status_code=409, detail="User already belongs to a partner.")

    partner = await create_partner_and_balance(
        db,
        name=payload.agency_name,
        email=current.email,
        country=payload.country,
    )
    current.partner_id = partner.id
    current.onboarding_completed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(current)
    # Partner didn't exist at auth time so current_partner_id was empty — update it now
    # so build_user_me can read the newly created partner row through RLS.
    await db.execute(
        text("SELECT set_config('app.current_partner_id', :pid, true)"),
        {"pid": str(partner.id)},
    )
    return await build_user_me(db, current)
