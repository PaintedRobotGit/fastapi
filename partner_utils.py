import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Partner, PartnerTokenBalance

TRIAL_PLAN_ID = 1


def _slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:100]


async def _unique_slug(db: AsyncSession, base: str) -> str:
    slug = base or "agency"
    counter = 2
    while True:
        existing = await db.execute(select(Partner).where(Partner.slug == slug))
        if existing.scalars().first() is None:
            return slug
        suffix = f"-{counter}"
        slug = base[: 100 - len(suffix)] + suffix
        counter += 1


async def create_partner_and_balance(
    db: AsyncSession, *, name: str, email: str, country: str | None
) -> Partner:
    slug = await _unique_slug(db, _slugify(name))
    partner = Partner(
        name=name,
        slug=slug,
        email=email,
        plan_id=TRIAL_PLAN_ID,
        status="trial",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
        timezone="UTC",
        country=country,
    )
    db.add(partner)
    await db.flush()
    balance = PartnerTokenBalance(
        partner_id=partner.id,
        billable_period=datetime.now(timezone.utc).date().replace(day=1),
        included_tokens=500_000,
        tokens_used=0,
    )
    db.add(balance)
    return partner
