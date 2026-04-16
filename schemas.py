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


# --- Users ---


class UserCreate(BaseModel):
    email: str = Field(max_length=255)
    username: str | None = Field(default=None, max_length=50)
    password_hash: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=512)
    role: str = Field(default="user", max_length=50)
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
    def exactly_one_scope(self) -> UserCreate:
        p, c = self.partner_id, self.customer_id
        if (p is None) == (c is None):
            raise ValueError("Exactly one of partner_id or customer_id must be set")
        return self


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=50)
    password_hash: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=512)
    role: str | None = Field(default=None, max_length=50)
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
    """Row fields for API responses; OAuth token fields omitted."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str | None
    first_name: str | None
    last_name: str | None
    avatar_url: str | None
    role: str
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


