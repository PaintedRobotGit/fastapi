from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from deps import get_current_user
from me import build_user_me
from models import Customer, Partner, User
from oauth_providers import verify_apple_identity_token, verify_google_id_token
from schemas import (
    AppleOAuthRequest,
    GoogleOAuthRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserMe,
)
from security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _assert_partner_xor_customer(partner_id: int | None, customer_id: int | None) -> None:
    if (partner_id is None) == (customer_id is None):
        raise HTTPException(
            status_code=400,
            detail="Exactly one of partner_id or customer_id must be set.",
        )


async def _user_by_oauth(db: AsyncSession, provider: str, provider_id: str) -> User | None:
    r = await db.execute(
        select(User).where(User.auth_provider == provider, User.provider_id == provider_id)
    )
    return r.scalars().first()


async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    r = await db.execute(select(User).where(User.email == email))
    return r.scalars().first()


def _issue_token(user_id: int) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user_id))


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    _assert_partner_xor_customer(payload.partner_id, payload.customer_id)
    if payload.partner_id is not None and await db.get(Partner, payload.partner_id) is None:
        raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    if payload.customer_id is not None and await db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=400, detail="Customer does not exist for customer_id.")

    user = User(
        email=payload.email.lower().strip(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        password_hash=hash_password(payload.password),
        partner_id=payload.partner_id,
        customer_id=payload.customer_id,
        auth_provider="email",
        provider_id=None,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Email already registered.") from e
    user.last_login = datetime.now(timezone.utc)
    await db.refresh(user)
    return _issue_token(user.id)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await _user_by_email(db, payload.email.lower().strip())
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if user.password_hash is None:
        raise HTTPException(status_code=401, detail="This account uses sign-in with Google or Apple.")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    user.last_login = datetime.now(timezone.utc)
    await db.flush()
    return _issue_token(user.id)


@router.post("/oauth/google", response_model=TokenResponse)
async def oauth_google(payload: GoogleOAuthRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if not settings.google_client_id:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured (set GOOGLE_CLIENT_ID).",
        )
    try:
        info = verify_google_id_token(payload.id_token, settings.google_client_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail="Invalid Google ID token.") from e

    sub = str(info.get("sub") or "")
    email = (info.get("email") or "").lower().strip() or None
    if not sub:
        raise HTTPException(status_code=401, detail="Google token missing subject.")

    existing = await _user_by_oauth(db, "google", sub)
    if existing:
        existing.last_login = datetime.now(timezone.utc)
        if email and existing.email != email:
            existing.email = email
        await db.flush()
        return _issue_token(existing.id)

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Google did not return an email; cannot create an account automatically.",
        )

    partner_id, customer_id = payload.partner_id, payload.customer_id
    if partner_id is None and customer_id is None:
        raise HTTPException(
            status_code=404,
            detail="No user linked to this Google account. Register with partner_id or customer_id first.",
        )
    _assert_partner_xor_customer(partner_id, customer_id)
    if partner_id is not None and await db.get(Partner, partner_id) is None:
        raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    if customer_id is not None and await db.get(Customer, customer_id) is None:
        raise HTTPException(status_code=400, detail="Customer does not exist for customer_id.")

    user = User(
        email=email,
        auth_provider="google",
        provider_id=sub,
        partner_id=partner_id,
        customer_id=customer_id,
        is_verified=bool(info.get("email_verified", False)),
        first_name=(info.get("given_name") or None),
        last_name=(info.get("family_name") or None),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Email already in use.") from e
    user.last_login = datetime.now(timezone.utc)
    await db.refresh(user)
    return _issue_token(user.id)


@router.post("/oauth/apple", response_model=TokenResponse)
async def oauth_apple(payload: AppleOAuthRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if not settings.apple_client_id:
        raise HTTPException(
            status_code=503,
            detail="Apple OAuth is not configured (set APPLE_CLIENT_ID).",
        )
    try:
        claims = verify_apple_identity_token(payload.identity_token, settings.apple_client_id)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid Apple identity token.") from e

    sub = str(claims.get("sub") or "")
    email = (claims.get("email") or "").lower().strip() or None
    if not sub:
        raise HTTPException(status_code=401, detail="Apple token missing subject.")

    existing = await _user_by_oauth(db, "apple", sub)
    if existing:
        existing.last_login = datetime.now(timezone.utc)
        if email and existing.email != email:
            existing.email = email
        await db.flush()
        return _issue_token(existing.id)

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Apple did not include email on this sign-in; use the first sign-in response or link an email.",
        )

    partner_id, customer_id = payload.partner_id, payload.customer_id
    if partner_id is None and customer_id is None:
        raise HTTPException(
            status_code=404,
            detail="No user linked to this Apple account. Register with partner_id or customer_id first.",
        )
    _assert_partner_xor_customer(partner_id, customer_id)
    if partner_id is not None and await db.get(Partner, partner_id) is None:
        raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    if customer_id is not None and await db.get(Customer, customer_id) is None:
        raise HTTPException(status_code=400, detail="Customer does not exist for customer_id.")

    user = User(
        email=email,
        auth_provider="apple",
        provider_id=sub,
        partner_id=partner_id,
        customer_id=customer_id,
        is_verified=bool(claims.get("email_verified", True)),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Email already in use.") from e
    user.last_login = datetime.now(timezone.utc)
    await db.refresh(user)
    return _issue_token(user.id)


@router.get("/me", response_model=UserMe)
async def auth_me(current: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UserMe:
    return await build_user_me(db, current)
