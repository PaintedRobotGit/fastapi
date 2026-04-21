from sqlalchemy import or_, select

from access import effective_partner_id
from models import Customer
from mcp_server.context import mcp_db_context
from mcp_server.tools.registry import mcp_tool


@mcp_tool(
    description=(
        "List customers visible to the authenticated user. Pass `q` to "
        "do a case-insensitive keyword search across name, slug, and "
        "website URL (e.g. q='blue horizon' resolves to 'Blue Horizon "
        "Spa'). Use this to look up a customer by name instead of asking "
        "the user for a numeric id."
    ),
    tags={"agent:general", "agent:customer_agent"},
)
async def list_customers(q: str | None = None, limit: int = 50) -> list[dict]:
    async with mcp_db_context() as (ctx, db):
        stmt = select(Customer).order_by(Customer.name)

        if ctx.is_admin:
            pass  # admins see all customers
        elif ctx.tier == "partner":
            ep = await effective_partner_id(db, ctx.user)
            if ep is None:
                return []
            stmt = stmt.where(Customer.partner_id == ep)
        else:
            # customer-tier users see only their own customer record
            if ctx.user.customer_id is None:
                return []
            stmt = stmt.where(Customer.id == ctx.user.customer_id)

        stmt = stmt.where(Customer.archived_at.is_(None))

        # Keyword search. Blank / whitespace-only `q` is treated as "no
        # filter" — keeps the tool forgiving when the caller passes an
        # empty string. `ilike` against nullable columns (slug can be
        # null in theory, website_url often is) returns false for null,
        # which is the right behaviour.
        if q and q.strip():
            needle = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    Customer.name.ilike(needle),
                    Customer.slug.ilike(needle),
                    Customer.website_url.ilike(needle),
                )
            )

        stmt = stmt.limit(min(max(limit, 1), 200))
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "slug": c.slug,
                "status": c.status,
                "partner_id": c.partner_id,
                "email": c.email,
                "timezone": c.timezone,
                "currency": c.currency,
                "customer_type": c.customer_type,
                "website_url": c.website_url,
            }
            for c in rows
        ]


@mcp_tool(description="Get a single customer by ID.", tags={"agent:general", "agent:customer_agent"})
async def get_customer(customer_id: int) -> dict:
    async with mcp_db_context() as (ctx, db):
        customer = await db.get(Customer, customer_id)
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found")

        if not ctx.is_admin:
            ep = await effective_partner_id(db, ctx.user)
            if ctx.tier == "partner":
                if ep is None or customer.partner_id != ep:
                    raise PermissionError("Not allowed to access this customer")
            elif ctx.tier == "customer":
                if ctx.user.customer_id != customer.id:
                    raise PermissionError("Not allowed to access this customer")
            else:
                raise PermissionError("Forbidden")

        return {
            "id": customer.id,
            "name": customer.name,
            "slug": customer.slug,
            "email": customer.email,
            "status": customer.status,
            "partner_id": customer.partner_id,
            "industry_id": customer.industry_id,
            "timezone": customer.timezone,
            "website_url": customer.website_url,
            "currency": customer.currency,
            "customer_type": customer.customer_type,
            "notes": customer.notes,
            "colour": customer.colour,
            "archived_at": customer.archived_at.isoformat() if customer.archived_at else None,
            "created_at": customer.created_at.isoformat(),
            "updated_at": customer.updated_at.isoformat(),
        }
