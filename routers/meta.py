from fastapi import APIRouter

from constants import (
    BLOG_POST_STATUSES,
    BLOG_POST_TEMPLATE_KEYS,
    BUYER_STAGES,
    CONTENT_FORMATS,
    CUSTOMER_STATUSES,
    DOCUMENT_STATUSES,
    DOCUMENT_TYPES,
    PARTNER_STATUSES,
    PRODUCT_TYPES,
    SERVICE_AREAS,
    VOICE_INPUT_TYPES,
)

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/enums")
async def get_enums() -> dict[str, list[str]]:
    """Returns all picklist values used across the API. Frontend should fetch this rather than hardcoding values."""
    return {
        "service_areas": SERVICE_AREAS,
        "voice_input_types": VOICE_INPUT_TYPES,
        "document_types": DOCUMENT_TYPES,
        "document_statuses": DOCUMENT_STATUSES,
        "content_formats": CONTENT_FORMATS,
        "buyer_stages": BUYER_STAGES,
        "product_types": PRODUCT_TYPES,
        "partner_statuses": PARTNER_STATUSES,
        "customer_statuses": CUSTOMER_STATUSES,
        "blog_post_statuses": BLOG_POST_STATUSES,
        "blog_post_template_keys": BLOG_POST_TEMPLATE_KEYS,
    }
