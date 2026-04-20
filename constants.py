"""
Picklist constants — single source of truth for every constrained enum field.

IMPORTANT: Each type here has a matching CHECK constraint in the database.
If you add, rename, or remove a value you must also run an ALTER TABLE migration
to update the CHECK constraint. The /meta/enums endpoint exposes these values
to the frontend so it never needs to hardcode them.
"""

from typing import Literal, get_args

# ── Service / channel routing ────────────────────────────────────────────────
ServiceArea = Literal["seo", "ads", "social", "email", "website", "creative", "reporting", "analytics"]

# Voice input types mirror service areas (minus reporting/analytics) plus general.
# These are the routing keys that determine which AI agent receives a sample as context.
VoiceInputType = Literal["seo", "ads", "social", "email", "website", "creative", "general"]

# ── Customer documents ───────────────────────────────────────────────────────
DocumentType = Literal["project_doc", "audit_context", "audit_summary", "report", "other"]
DocumentStatus = Literal["current", "stale", "archived"]
ContentFormat = Literal["markdown", "html", "plaintext", "json"]

# ── Target audiences ─────────────────────────────────────────────────────────
BuyerStage = Literal["awareness", "consideration", "decision", "retention"]

# ── Products & services ──────────────────────────────────────────────────────
ProductType = Literal["product", "service", "bundle"]

# ── Account statuses ─────────────────────────────────────────────────────────
PartnerStatus = Literal["trial", "active", "past_due", "canceled", "suspended"]
CustomerStatus = Literal["prep", "active", "on_hold", "archived"]

# ── Blog posts ───────────────────────────────────────────────────────────────
BlogPostStatus = Literal["draft", "review", "scheduled", "published", "archived"]
BlogPostVersionSource = Literal["manual_save", "autosave", "ai:blog_writer", "ai:revise", "status_change"]
# Blog post template keys live in the `blog_templates` DB table — no Literal needed.

# ── Derived lists (used by /meta/enums and DB migrations) ───────────────────
SERVICE_AREAS: list[str] = list(get_args(ServiceArea))
VOICE_INPUT_TYPES: list[str] = list(get_args(VoiceInputType))
DOCUMENT_TYPES: list[str] = list(get_args(DocumentType))
DOCUMENT_STATUSES: list[str] = list(get_args(DocumentStatus))
CONTENT_FORMATS: list[str] = list(get_args(ContentFormat))
BUYER_STAGES: list[str] = list(get_args(BuyerStage))
PRODUCT_TYPES: list[str] = list(get_args(ProductType))
PARTNER_STATUSES: list[str] = list(get_args(PartnerStatus))
CUSTOMER_STATUSES: list[str] = list(get_args(CustomerStatus))
BLOG_POST_STATUSES: list[str] = list(get_args(BlogPostStatus))
