from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --- Plans ---


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = Field(max_length=50)
    monthly_token_limit: int | None = None
    max_customers: int | None = None
    max_users: int | None = None
    price_monthly: Decimal | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Industries ---


class IndustryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    sort_order: int
    is_active: bool
    created_at: datetime


# --- Partners ---


class PartnerCreate(BaseModel):
    name: str = Field(max_length=255)
    email: str | None = Field(default=None, max_length=255)
    plan_id: int
    timezone: str = Field(default="UTC", max_length=100)
    status: str = Field(
        default="active",
        max_length=50,
        description="trial | active | past_due | canceled | suspended",
    )
    trial_ends_at: datetime | None = None
    subscription_expires_at: datetime | None = None
    country: str | None = None
    website: str | None = None
    archived_at: datetime | None = None


class PartnerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    plan_id: int | None = None
    timezone: str | None = Field(default=None, max_length=100)
    status: str | None = Field(
        default=None,
        max_length=50,
        description="trial | active | past_due | canceled | suspended",
    )
    trial_ends_at: datetime | None = None
    subscription_expires_at: datetime | None = None
    country: str | None = None
    website: str | None = None
    archived_at: datetime | None = None


class PartnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str | None
    slug: str | None
    plan_id: int
    timezone: str
    status: str
    trial_ends_at: datetime | None
    subscription_expires_at: datetime | None
    country: str | None
    website: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- Customers ---


class CustomerCreate(BaseModel):
    partner_id: int
    name: str = Field(max_length=255)
    email: str | None = Field(default=None, max_length=255)
    industry_id: int | None = None
    timezone: str = Field(default="UTC", max_length=100)
    website_url: str | None = None
    currency: str = Field(default="USD", max_length=16)
    customer_type: str | None = Field(default=None, max_length=32)
    status: str = Field(
        default="prep",
        max_length=32,
        description="prep | active | on_hold | archived",
    )
    notes: str | None = None
    colour: str | None = Field(default=None, description="Hex colour code e.g. #FF5733")
    archived_at: datetime | None = None

    @field_validator("colour")
    @classmethod
    def validate_colour(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            raise ValueError("colour must be a 6-digit hex code e.g. #FF5733")
        return v


class CustomerUpdate(BaseModel):
    partner_id: int | None = None
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    industry_id: int | None = None
    timezone: str | None = Field(default=None, max_length=100)
    website_url: str | None = None
    currency: str | None = Field(default=None, max_length=16)
    customer_type: str | None = Field(default=None, max_length=32)
    status: str | None = Field(
        default=None,
        max_length=32,
        description="prep | active | on_hold | archived",
    )
    notes: str | None = None
    colour: str | None = Field(default=None, description="Hex colour code e.g. #FF5733")
    archived_at: datetime | None = None

    @field_validator("colour")
    @classmethod
    def validate_colour(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            raise ValueError("colour must be a 6-digit hex code e.g. #FF5733")
        return v


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    name: str
    slug: str
    email: str | None
    industry_id: int | None
    timezone: str
    website_url: str | None
    currency: str
    customer_type: str | None
    status: str
    notes: str | None
    colour: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PartnerWithCustomersRead(BaseModel):
    partner: PartnerRead
    customers: list[CustomerRead]


# --- Roles & permissions ---


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str | None = None
    tier: str
    sort_order: int
    description: str | None = None
    is_default: bool
    created_at: datetime


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str = Field(max_length=100)
    description: str | None = None
    created_at: datetime


class RolePermissionAttach(BaseModel):
    permission_id: int


# --- Users ---


class UserCreate(BaseModel):
    email: str = Field(max_length=255)
    username: str | None = Field(default=None, max_length=50)
    password_hash: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=512)
    role_id: int
    status: str = Field(
        default="active",
        max_length=32,
        description="active | invited | suspended | deactivated",
    )
    email_verified_at: datetime | None = None
    mfa_enabled: bool = False
    mfa_secret: str | None = None
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
    status: str | None = Field(
        default=None,
        max_length=32,
        description="active | invited | suspended | deactivated",
    )
    email_verified_at: datetime | None = None
    mfa_enabled: bool | None = None
    mfa_secret: str | None = None
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
    status: str
    email_verified_at: datetime | None
    mfa_enabled: bool
    partner_id: int | None
    customer_id: int | None
    auth_provider: str | None
    provider_id: str | None
    token_expires_at: datetime | None
    scope: str | None
    last_login: datetime | None
    onboarding_completed_at: datetime | None
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
    partner_plan: PlanRead | None = Field(
        default=None,
        description="Subscription plan for the resolved partner (when applicable).",
    )
    customer: CustomerRead | None = None


# --- Auth ---


class SignupRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=512)
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)


class GoogleSignupRequest(BaseModel):
    id_token: str = Field(min_length=10)


class AppleSignupRequest(BaseModel):
    identity_token: str = Field(min_length=10)


class OnboardingCompleteRequest(BaseModel):
    agency_name: str = Field(max_length=255)
    country: str | None = None


class SignupUserInfo(BaseModel):
    id: int
    email: str
    first_name: str | None
    role: str


class SignupPartnerInfo(BaseModel):
    id: int
    name: str
    slug: str | None
    plan: str


class SignupResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email_verified: bool = False
    user: SignupUserInfo
    partner: SignupPartnerInfo | None = None


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


# --- Customer profile (services, channels, documents, brand, audiences, info base, products, contacts) ---


class CustomerServicesUpdate(BaseModel):
    seo_notes: str | None = None
    ads_notes: str | None = None
    social_notes: str | None = None
    email_notes: str | None = None
    website_notes: str | None = None
    creative_notes: str | None = None


class CustomerServicesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    customer_id: int
    seo_notes: str | None
    ads_notes: str | None
    social_notes: str | None
    email_notes: str | None
    website_notes: str | None
    creative_notes: str | None
    created_at: datetime
    updated_at: datetime


class CustomerServiceChannelCreate(BaseModel):
    service_area: str = Field(description="seo | ads | social | email | website | creative | reporting | analytics")
    channel_label: str
    is_active: bool = True
    notes: str | None = None


class CustomerServiceChannelUpdate(BaseModel):
    channel_label: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class CustomerServiceChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    customer_id: int
    service_area: str
    channel_label: str
    is_active: bool
    notes: str | None
    created_at: datetime


class CustomerDocumentCreate(BaseModel):
    document_type: str = Field(description="project_doc | audit_context | audit_summary | report | other")
    name: str
    version: str = "1.0"
    status: str = Field(default="current", description="current | stale | archived")
    content: str | None = None
    content_format: str = Field(default="markdown", description="markdown | html | plaintext | json")
    metadata: dict | None = None


class CustomerDocumentUpdate(BaseModel):
    name: str | None = None
    version: str | None = None
    status: str | None = Field(default=None, description="current | stale | archived")
    content: str | None = None
    content_format: str | None = None
    metadata: dict | None = None


class CustomerDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    customer_id: int
    document_type: str
    name: str
    version: str
    status: str
    content: str | None
    content_format: str
    metadata: dict | None
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class BrandVoiceUpdate(BaseModel):
    tone_descriptors: list[str] | None = None
    voice_detail: str | None = None
    dos: list[str] | None = None
    donts: list[str] | None = None
    example_phrases: list[str] | None = None


class BrandVoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    customer_id: int
    tone_descriptors: list[str] | None
    voice_detail: str | None
    dos: list[str] | None
    donts: list[str] | None
    example_phrases: list[str] | None
    created_at: datetime
    updated_at: datetime


class BrandVoiceInputCreate(BaseModel):
    input_type: str | None = None
    content: str
    submitted_by: str | None = None
    notes: str | None = None


class BrandVoiceInputRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    customer_id: int
    input_type: str | None
    content: str
    submitted_by: str | None
    notes: str | None
    created_at: datetime


class TargetAudienceCreate(BaseModel):
    name: str
    rank: int = 99
    demographics: dict | None = None
    psychographics: dict | None = None
    buyer_stage: str | None = Field(default=None, description="awareness | consideration | decision | retention")
    description: str | None = None
    pain_points: list[str] | None = None
    goals: list[str] | None = None


class TargetAudienceUpdate(BaseModel):
    name: str | None = None
    rank: int | None = None
    demographics: dict | None = None
    psychographics: dict | None = None
    buyer_stage: str | None = None
    description: str | None = None
    pain_points: list[str] | None = None
    goals: list[str] | None = None


class TargetAudienceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    customer_id: int
    name: str
    rank: int
    demographics: dict | None
    psychographics: dict | None
    buyer_stage: str | None
    description: str | None
    pain_points: list[str] | None
    goals: list[str] | None
    created_at: datetime
    updated_at: datetime


class InfoBaseEntryCreate(BaseModel):
    category: str | None = None
    title: str
    content: str
    is_key_message: bool = False


class InfoBaseEntryUpdate(BaseModel):
    category: str | None = None
    title: str | None = None
    content: str | None = None
    is_key_message: bool | None = None


class InfoBaseEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    customer_id: int
    category: str | None
    title: str
    content: str
    is_key_message: bool
    created_at: datetime
    updated_at: datetime


class ProductOrServiceCreate(BaseModel):
    name: str
    type: str = Field(description="product | service | bundle")
    description: str | None = None
    price_cents: int | None = None
    currency: str | None = None
    price_model: str | None = None
    url: str | None = None
    is_featured: bool = False
    sort_order: int = 0
    metadata: dict | None = None


class ProductOrServiceUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    description: str | None = None
    price_cents: int | None = None
    currency: str | None = None
    price_model: str | None = None
    url: str | None = None
    is_featured: bool | None = None
    sort_order: int | None = None
    metadata: dict | None = None


class ProductOrServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    customer_id: int
    name: str
    type: str
    description: str | None
    price_cents: int | None
    currency: str | None
    price_model: str | None
    url: str | None
    is_featured: bool
    sort_order: int
    metadata: dict | None
    created_at: datetime
    updated_at: datetime


class CustomerContactCreate(BaseModel):
    full_name: str
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    is_primary: bool = False
    receives_reports: bool = False
    notes: str | None = None


class CustomerContactUpdate(BaseModel):
    full_name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    is_primary: bool | None = None
    receives_reports: bool | None = None
    notes: str | None = None


class CustomerContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    customer_id: int
    full_name: str
    title: str | None
    email: str | None
    phone: str | None
    is_primary: bool
    receives_reports: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


# --- App agents ---


class AppAgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    category: str
    description: str
    is_default: bool
    enabled: bool
    thinking_default: bool
    partner_id: int | None


# --- Chat ---


class ChatSessionCreate(BaseModel):
    customer_id: int | None = None
    title: str | None = None


class ChatSessionUpdate(BaseModel):
    title: str | None = None
    customer_id: int | None = None
    archived_at: datetime | None = None
    current_agent_key: str | None = None


class ChatSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    user_id: int
    customer_id: int | None
    current_agent_key: str | None
    title: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ChatMessageCreate(BaseModel):
    role: str = Field(description="user | assistant | system")
    content: str
    model: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("user", "assistant", "system"):
            raise ValueError("role must be user, assistant, or system")
        return v


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    partner_id: int
    role: str
    content: str
    model: str | None
    created_at: datetime


class ChatSessionShareCreate(BaseModel):
    shared_with_user_id: int


class ChatSessionShareRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    shared_with_user_id: int
    shared_by_user_id: int | None
    created_at: datetime


# --- AI token usage & partner balance ---


class AiTokenUsageCreate(BaseModel):
    partner_id: int
    customer_id: int | None = None
    model: str = Field(max_length=100)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    total_tokens: int | None = Field(
        default=None,
        ge=0,
        description="Defaults to input + output + cache_read + cache_write when omitted.",
    )
    feature: str | None = Field(default=None, max_length=100)
    ai_provider: str = Field(default="default", max_length=64)
    provider_request_id: str | None = None
    estimated_cost_cents: int | None = Field(default=None, ge=0)
    billable_period: date | None = Field(
        default=None,
        description="First day of the billing month; defaults to the first day of the current UTC month.",
    )
    user_id: int | None = Field(
        default=None,
        description="User who triggered the AI call (must belong to the same partner org as partner_id).",
    )


class AiTokenUsageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    customer_id: int | None
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int | None
    feature: str | None
    ai_provider: str
    provider_request_id: str | None
    estimated_cost_cents: int | None
    billable_period: date
    user_id: int | None
    created_at: datetime


class PartnerTokenBalanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    partner_id: int
    billable_period: date
    included_tokens: int
    tokens_used: int
    tokens_remaining: int | None
    cap_warned_at: datetime | None
    cap_reached_at: datetime | None
    last_updated_at: datetime


class PartnerTokenBalanceCreate(BaseModel):
    partner_id: int
    billable_period: date
    included_tokens: int = Field(default=0, ge=0)
    tokens_used: int = Field(default=0, ge=0)


class PartnerTokenBalanceUpdate(BaseModel):
    """Patch rolling counters (e.g. background aggregation jobs)."""

    included_tokens: int | None = Field(default=None, ge=0)
    tokens_used: int | None = Field(default=None, ge=0)
    tokens_remaining: int | None = Field(default=None, ge=0)
    cap_warned_at: datetime | None = None
    cap_reached_at: datetime | None = None
