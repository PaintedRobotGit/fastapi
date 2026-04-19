from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from access import AccessContext, build_access_context
from database import AsyncSessionLocal
from mcp_server.middleware import _current_token


@asynccontextmanager
async def mcp_db_context() -> AsyncGenerator[tuple[AccessContext, AsyncSession], None]:
    """Open a JWT-authenticated, RLS-scoped database session for an MCP tool call.

    Usage in tools::

        @mcp.tool
        async def my_tool(arg: str) -> dict:
            async with mcp_db_context() as (ctx, db):
                # ctx.user, ctx.tier, ctx.is_admin available
                # db session has all four RLS session vars configured
                ...

    The middleware has already verified the JWT signature; this function loads the
    full user + role from the database and sets all RLS session variables so every
    query is automatically scoped to what the caller is allowed to see.

    Commits on clean exit, rolls back on any exception.
    """
    token = _current_token.get()
    if token is None:
        raise PermissionError("Not authenticated")

    async with AsyncSessionLocal() as db:
        try:
            ctx = await build_access_context(token, db)
        except ValueError as e:
            raise PermissionError(str(e)) from e

        try:
            yield ctx, db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
