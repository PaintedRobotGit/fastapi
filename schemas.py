from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- Partners ---


class PartnerCreate(BaseModel):
    name: str = Field(max_length=255)
    email: str | None = Field(default=None, max_length=255)
    slug: str | None = Field(default=None, max_length=100)
    plan: str = Field(default="trial", max_length=50)
    timezone: str = Field(default="UTC", max_length=100)
    is_active: bool = True
    trial_ends_at: datetime | None = None
    subscription_expires_at: datetime | None = None


class PartnerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    slug: str | None = Field(default=None, max_length=100)
    plan: str | None = Field(default=None, max_length=50)
    timezone: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    trial_ends_at: datetime | None = None
    subscription_expires_at: datetime | None = None


class PartnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str | None
    slug: str | None
    plan: str
    timezone: str
    is_active: bool
    trial_ends_at: datetime | None
    subscription_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- Customers ---


class CustomerCreate(BaseModel):
    partner_id: int
    name: str = Field(max_length=255)
    email: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    timezone: str = Field(default="UTC", max_length=100)
    is_active: bool = True


class CustomerUpdate(BaseModel):
    partner_id: int | None = None
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    name: str
    email: str | None
    industry: str | None
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PartnerWithCustomersRead(BaseModel):
    partner: PartnerRead
    customers: list[CustomerRead]


# --- Roles & permissions (read models aligned with docs/database.md) ---


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tier: str
    description: str | None = None
    is_default: bool
    created_at: datetime


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str = Field(max_length=100)
    description: str | None = None
    created_at: datetime


# --- Users ---


class UserCreate(BaseModel):
    email: str = Field(max_length=255)
    username: str | None = Field(default=None, max_length=50)
    password_hash: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=512)
    role_id: int
    is_active: bool = True
    is_verified: bool = False
    partner_id: int | None = None
    customer_id: int | None = None
    auth_provider: str | None = Field(default=None, max_length=50)
    provider_id: str | None = Field(default=None, max_length=255)
    access_token: str | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    token_expires_at: datetime | None = None
    scope: str | None = Field(default=None, max_length=512)
    last_login: datetime | None = None

    @model_validator(mode="after")
    def at_most_one_partner_customer(self) -> UserCreate:
        if self.partner_id is not None and self.customer_id is not None:
            raise ValueError("partner_id and customer_id cannot both be set")
        return self


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=50)
    password_hash: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=512)
    role_id: int | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    partner_id: int | None = None
    customer_id: int | None = None
    auth_provider: str | None = Field(default=None, max_length=50)
    provider_id: str | None = Field(default=None, max_length=255)
    access_token: str | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    token_expires_at: datetime | None = None
    scope: str | None = Field(default=None, max_length=512)
    last_login: datetime | None = None


class UserRead(BaseModel):
    """API user row; OAuth secrets omitted."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str | None
    first_name: str | None
    last_name: str | None
    avatar_url: str | None
    role_id: int
    is_active: bool
    is_verified: bool
    partner_id: int | None
    customer_id: int | None
    auth_provider: str | None
    provider_id: str | None
    token_expires_at: datetime | None
    scope: str | None
    last_login: datetime | None
    created_at: datetime
    updated_at: datetime


class UserMe(BaseModel):
    """Session user, role, optional partner/customer context, and role permissions (UI hints only)."""

    user: UserRead
    role: RoleRead | None = None
    permissions: list[PermissionRead] = Field(
        default_factory=list,
        description="Permissions granted by the user's role (for menus/UI); enforce rules on each endpoint too.",
    )
    partner: PartnerRead | None = None
    customer: CustomerRead | None = None


# --- Auth ---


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=1, max_length=512)


class RegisterRequest(BaseModel):
    """Email/password sign-up. Default roles: partner_member / customer_member when scoped."""

    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=512)
    partner_id: int | None = None
    customer_id: int | None = None
    role_id: int | None = Field(
        default=None,
        description="Required if neither partner_id nor customer_id is set (admin-tier roles).",
    )
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def partner_customer_at_most_one(self) -> RegisterRequest:
        if self.partner_id is not None and self.customer_id is not None:
            raise ValueError("partner_id and customer_id cannot both be set")
        return self


class GoogleOAuthRequest(BaseModel):
    """Exchange a Google ID token for an API access token."""

    id_token: str = Field(min_length=10)
    partner_id: int | None = None
    customer_id: int | None = None
    role_id: int | None = Field(
        default=None,
        description="When creating a user without partner/customer scope, set an admin-tier role_id.",
    )

    @model_validator(mode="after")
    def scope_at_most_one(self) -> GoogleOAuthRequest:
        if self.partner_id is not None and self.customer_id is not None:
            raise ValueError("partner_id and customer_id cannot both be set")
        return self


class AppleOAuthRequest(BaseModel):
    identity_token: str = Field(min_length=10)
    partner_id: int | None = None
    customer_id: int | None = None
    role_id: int | None = Field(
        default=None,
        description="When creating a user without partner/customer scope, set an admin-tier role_id.",
    )

    @model_validator(mode="after")
    def scope_at_most_one(self) -> AppleOAuthRequest:
        if self.partner_id is not None and self.customer_id is not None:
            raise ValueError("partner_id and customer_id cannot both be set")
        return self
