import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from deps import get_current_user
from me import build_user_me
from models import Customer, Partner, PartnerTokenBalance, User
from oauth_providers import verify_apple_identity_token, verify_google_id_token
from role_utils import resolve_role_id_for_signup
from schemas import (
    AppleOAuthRequest,
    AppleSignupRequest,
    GoogleOAuthRequest,
    GoogleSignupRequest,
    LoginRequest,
    RegisterRequest,
    SignupPartnerInfo,
    SignupRequest,
    SignupResponse,
    SignupUserInfo,
    TokenResponse,
    UserMe,
)
from security import create_access_token, hash_password, verify_password

PARTNER_OWNER_ROLE_ID = 3
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


async def _create_partner_and_balance(
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

router = APIRouter(prefix="/auth", tags=["auth"])


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


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)) -> SignupResponse:
    if await _user_by_email(db, payload.email.lower().strip()):
        raise HTTPException(status_code=409, detail="Email already registered.")
    user = User(
        email=payload.email.lower().strip(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        password_hash=hash_password(payload.password),
        role_id=PARTNER_OWNER_ROLE_ID,
        status="active",
        auth_provider="email",
        last_login=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return SignupResponse(
        access_token=create_access_token(user.id),
        email_verified=False,
        user=SignupUserInfo(id=user.id, email=user.email, first_name=user.first_name, role="partner_owner"),
        partner=None,
    )


@router.post("/signup/google", response_model=SignupResponse, status_code=201)
async def signup_google(payload: GoogleSignupRequest, db: AsyncSession = Depends(get_db)) -> SignupResponse:
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured (set GOOGLE_CLIENT_ID).")
    try:
        info = verify_google_id_token(payload.id_token, settings.google_client_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail="Invalid Google ID token.") from e

    sub = str(info.get("sub") or "")
    email = (info.get("email") or "").lower().strip() or None
    if not sub:
        raise HTTPException(status_code=401, detail="Google token missing subject.")
    if not email:
        raise HTTPException(status_code=400, detail="Google did not return an email.")

    existing = await _user_by_oauth(db, "google", sub) or await _user_by_email(db, email)
    if existing:
        if existing.status != "active":
            raise HTTPException(status_code=401, detail="Account is not active.")
        existing.last_login = datetime.now(timezone.utc)
        await db.flush()
        return SignupResponse(
            access_token=create_access_token(existing.id),
            email_verified=existing.email_verified_at is not None,
            user=SignupUserInfo(id=existing.id, email=existing.email, first_name=existing.first_name, role="partner_owner"),
            partner=None,
        )

    email_verified = bool(info.get("email_verified"))
    user = User(
        email=email,
        first_name=info.get("given_name") or None,
        last_name=info.get("family_name") or None,
        avatar_url=info.get("picture") or None,
        auth_provider="google",
        provider_id=sub,
        role_id=PARTNER_OWNER_ROLE_ID,
        status="active",
        email_verified_at=datetime.now(timezone.utc) if email_verified else None,
        last_login=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return SignupResponse(
        access_token=create_access_token(user.id),
        email_verified=email_verified,
        user=SignupUserInfo(id=user.id, email=user.email, first_name=user.first_name, role="partner_owner"),
        partner=None,
    )


@router.post("/signup/apple", response_model=SignupResponse, status_code=201)
async def signup_apple(payload: AppleSignupRequest, db: AsyncSession = Depends(get_db)) -> SignupResponse:
    if not settings.apple_client_id:
        raise HTTPException(status_code=503, detail="Apple OAuth is not configured (set APPLE_CLIENT_ID).")
    try:
        claims = verify_apple_identity_token(payload.identity_token, settings.apple_client_id)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid Apple identity token.") from e

    sub = str(claims.get("sub") or "")
    email = (claims.get("email") or "").lower().strip() or None
    if not sub:
        raise HTTPException(status_code=401, detail="Apple token missing subject.")
    if not email:
        raise HTTPException(status_code=400, detail="Apple did not include an email; cannot create an account.")

    existing = await _user_by_oauth(db, "apple", sub) or await _user_by_email(db, email)
    if existing:
        if existing.status != "active":
            raise HTTPException(status_code=401, detail="Account is not active.")
        existing.last_login = datetime.now(timezone.utc)
        await db.flush()
        email_verified = existing.email_verified_at is not None
        return SignupResponse(
            access_token=create_access_token(existing.id),
            email_verified=email_verified,
            user=SignupUserInfo(id=existing.id, email=existing.email, first_name=existing.first_name, role="partner_owner"),
            partner=None,
        )

    email_verified = bool(claims.get("email_verified", True))
    user = User(
        email=email,
        auth_provider="apple",
        provider_id=sub,
        role_id=PARTNER_OWNER_ROLE_ID,
        status="active",
        email_verified_at=datetime.now(timezone.utc) if email_verified else None,
        last_login=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return SignupResponse(
        access_token=create_access_token(user.id),
        email_verified=email_verified,
        user=SignupUserInfo(id=user.id, email=user.email, first_name=user.first_name, role="partner_owner"),
        partner=None,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if payload.partner_id is not None and await db.get(Partner, payload.partner_id) is None:
        raise HTTPException(status_code=400, detail="Partner does not exist for partner_id.")
    if payload.customer_id is not None and await db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=400, detail="Customer does not exist for customer_id.")

    role_id = await resolve_role_id_for_signup(
        db,
        partner_id=payload.partner_id,
        customer_id=payload.customer_id,
        role_id=payload.role_id,
    )
    user = User(
        email=payload.email.lower().strip(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        password_hash=hash_password(payload.password),
        partner_id=payload.partner_id,
        customer_id=payload.customer_id,
        role_id=role_id,
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
    if user.status != "active":
        # Same message as wrong password to avoid account enumeration (matches get_current_user behavior).
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
    if not existing and email:
        existing = await _user_by_email(db, email)
    if existing:
        if existing.status != "active":
            raise HTTPException(status_code=401, detail="Account is not active.")
        existing.last_login = datetime.now(timezone.utc)
        if email and existing.email != email:
            existing.email = email
        await db.flush()
        return _issue_token(existing.id)

    if not email:
        raise HTTPException(status_code=400, detail="Google did not return an email.")
    email_verified = bool(info.get("email_verified"))
    user = User(
        email=email,
        first_name=info.get("given_name") or None,
        last_name=info.get("family_name") or None,
        avatar_url=info.get("picture") or None,
        auth_provider="google",
        provider_id=sub,
        role_id=PARTNER_OWNER_ROLE_ID,
        status="active",
        email_verified_at=datetime.now(timezone.utc) if email_verified else None,
        last_login=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
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
    if not existing and email:
        existing = await _user_by_email(db, email)
    if existing:
        if existing.status != "active":
            raise HTTPException(status_code=401, detail="Account is not active.")
        existing.last_login = datetime.now(timezone.utc)
        if email and existing.email != email:
            existing.email = email
        await db.flush()
        return _issue_token(existing.id)

    if not email:
        raise HTTPException(status_code=400, detail="Apple did not include an email on this sign-in.")
    email_verified = bool(claims.get("email_verified", True))
    user = User(
        email=email,
        auth_provider="apple",
        provider_id=sub,
        role_id=PARTNER_OWNER_ROLE_ID,
        status="active",
        email_verified_at=datetime.now(timezone.utc) if email_verified else None,
        last_login=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return _issue_token(user.id)


@router.get("/me", response_model=UserMe)
async def auth_me(current: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UserMe:
    return await build_user_me(db, current)
