"""Build `/me` responses with resolved role, partner (agency), and optional customer."""

from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer, Partner, Role, User
from schemas import CustomerRead, PartnerRead, RoleRead, UserMe, UserRead


async def build_user_me(db: AsyncSession, user: User) -> UserMe:
    u = UserRead.model_validate(user)
    role_row = await db.get(Role, user.role_id)
    role_out = RoleRead.model_validate(role_row) if role_row is not None else None

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

    return UserMe(user=u, role=role_out, partner=partner_out, customer=customer_out)
