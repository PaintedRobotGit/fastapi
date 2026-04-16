import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from database import AsyncSessionLocal, engine
from routers import (
    ai_token_usage,
    auth,
    customers,
    industries,
    partner_token_balance,
    partners,
    permissions,
    plans,
    roles,
    users,
)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

app.include_router(auth.router)
app.include_router(plans.router)
app.include_router(industries.router)
app.include_router(partners.router)
app.include_router(customers.router)
app.include_router(roles.router)
app.include_router(permissions.router)
app.include_router(users.router)
app.include_router(ai_token_usage.router)
app.include_router(partner_token_balance.router)


@app.get("/")
async def root():
    return {"greeting": "Hello, World!", "message": "Welcome to FastAPI!"}


@app.get("/health/db")
async def db_health():
    """Verifies DATABASE_URL is valid and the database accepts connections."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database connection failed") from exc
    return {"ok": True, "database": True}
