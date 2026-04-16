"""Build `/me` responses with resolved role, permissions, partner, plan, and customer."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer, Partner, Permission, Plan, Role, RolePermission, User
from schemas import CustomerRead, PartnerRead, PermissionRead, PlanRead, RoleRead, UserMe, UserRead


async def build_user_me(db: AsyncSession, user: User) -> UserMe:
    u = UserRead.model_validate(user)
    role_row = await db.get(Role, user.role_id)
    role_out = RoleRead.model_validate(role_row) if role_row is not None else None

    perm_stmt = (
        select(Permission)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.role_id == user.role_id)
        .order_by(Permission.key)
    )
    perm_result = await db.execute(perm_stmt)
    permission_rows = list(perm_result.scalars().all())
    permissions_out = [PermissionRead.model_validate(p) for p in permission_rows]

    partner_row: Partner | None = None
    customer_row: Customer | None = None
    plan_row: Plan | None = None

    if user.partner_id is not None:
        partner_row = await db.get(Partner, user.partner_id)
    elif user.customer_id is not None:
        customer_row = await db.get(Customer, user.customer_id)
        if customer_row is not None:
            partner_row = await db.get(Partner, customer_row.partner_id)

    if partner_row is not None:
        plan_row = await db.get(Plan, partner_row.plan_id)

    partner_out = PartnerRead.model_validate(partner_row) if partner_row is not None else None
    plan_out = PlanRead.model_validate(plan_row) if plan_row is not None else None
    customer_out = CustomerRead.model_validate(customer_row) if customer_row is not None else None

    return UserMe(
        user=u,
        role=role_out,
        permissions=permissions_out,
        partner=partner_out,
        partner_plan=plan_out,
        customer=customer_out,
    )
