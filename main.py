import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text

from config import settings
from database import AsyncSessionLocal, engine
from routers import (
    ai_token_usage,
    auth,
    chat,
    customers,
    industries,
    onboarding,
    partner_token_balance,
    partners,
    permissions,
    plans,
    roles,
    users,
)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if settings.jwt_secret == "dev-only-change-me":
    logging.getLogger(__name__).critical(
        "JWT_SECRET is using the insecure default value. Set JWT_SECRET in your environment before deploying."
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    lifespan=lifespan,
    title="PaintedRobot API",
    # Default ReDoc uses `redoc@next` from a CDN, which often yields a blank page; we serve `/redoc` manually below.
    redoc_url=None,
    description=(
        "JWT (Bearer) protects all routes except: "
        "`GET /`, `GET /health/db`, `GET /plans`, `GET /industries`, "
        "and `POST /auth/register`, `/auth/login`, `/auth/oauth/google`, `/auth/oauth/apple`. "
        "Use **Authorize** in Swagger UI and paste `Bearer <token>` or just the raw JWT."
    ),
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _path_is_public(path: str) -> bool:
    if path in ("/", "/health/db"):
        return True
    if path.startswith("/openapi") or path.startswith("/docs") or path.startswith("/redoc"):
        return True
    if path.startswith("/plans"):
        return True
    if path.startswith("/industries"):
        return True
    if path in ("/auth/register", "/auth/login", "/auth/signup"):
        return True
    if path.startswith("/auth/oauth") or path.startswith("/auth/signup"):
        return True
    return False


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=getattr(app, "version", "0.1.0"),
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})["JWT"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT from `/auth/login`, `/auth/register`, or OAuth endpoints.",
    }
    for path, path_item in openapi_schema.get("paths", {}).items():
        is_public = _path_is_public(path)
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = path_item.get(method)
            if not op:
                continue
            if is_public:
                op.pop("security", None)
            else:
                op["security"] = [{"JWT": []}]
    app.openapi_schema = openapi_schema
    return openapi_schema


app.openapi = custom_openapi

app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(plans.router)
app.include_router(industries.router)
app.include_router(partners.router)
app.include_router(customers.router)
app.include_router(roles.router)
app.include_router(permissions.router)
app.include_router(users.router)
app.include_router(ai_token_usage.router)
app.include_router(partner_token_balance.router)
app.include_router(chat.router)


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    """Stable ReDoc bundle; the default `redoc@next` CDN URL often fails (blank page)."""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.1.3/bundles/redoc.standalone.js",
        with_google_fonts=False,
    )


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
