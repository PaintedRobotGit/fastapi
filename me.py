"""Build `/me` responses with resolved partner (agency) and optional customer."""

from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer, Partner, User
from schemas import CustomerRead, PartnerRead, UserMe, UserRead


async def build_user_me(db: AsyncSession, user: User) -> UserMe:
    u = UserRead.model_validate(user)
    partner_row: Partner | None = None
    customer_row: Customer | None = None

    if user.partner_id is not None:
        partner_row = await db.get(Partner, user.partner_id)
    elif user.customer_id is not None:
        customer_row = await db.get(Customer, user.customer_id)
        if customer_row is not None:
            partner_row = await db.get(Partner, customer_row.partner_id)

    partner_out = PartnerRead.model_validate(partner_row) if partner_row is not None else None
    customer_out = CustomerRead.model_validate(customer_row) if customer_row is not None else None

    return UserMe(user=u, partner=partner_out, customer=customer_out)
