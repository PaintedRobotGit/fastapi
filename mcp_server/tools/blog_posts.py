from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from sqlalchemy import select

from access import effective_partner_id
from models import (
    BlogPost,
    BlogPostVersion,
    BlogTemplate,
    BrandVoice,
    BrandVoiceInput,
    Customer,
    InfoBaseEntry,
    ProductOrService,
    TargetAudience,
)
from mcp_server.context import mcp_db_context
from mcp_server.tools.registry import mcp_tool


def _slugify(title: str, max_len: int = 80) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:max_len] or "post"


async def _alloc_slug(db, customer_id: int, base_slug: str) -> str:
    slug = base_slug
    n = 2
    while True:
        exists = (await db.execute(
            select(BlogPost.id).where(
                BlogPost.customer_id == customer_id,
                BlogPost.slug == slug,
            )
        )).scalar_one_or_none()
        if exists is None:
            return slug
        slug = f"{base_slug[:77]}-{n}"
        n += 1


async def _check_customer_access(ctx, db, customer_id: int) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise ValueError(f"Customer {customer_id} not found")
    if not ctx.is_admin:
        ep = await effective_partner_id(db, ctx.user)
        if ctx.tier == "partner":
            if ep is None or customer.partner_id != ep:
                raise PermissionError("Not allowed to access this customer")
        elif ctx.tier == "customer":
            if ctx.user.customer_id != customer_id:
                raise PermissionError("Not allowed to access this customer")
        else:
            raise PermissionError("Forbidden")
    return customer


@mcp_tool(
    description=(
        "Get all brand context for a customer: brand voice, target audiences, "
        "products/services, and key info base entries. Call this first before "
        "writing any blog post content."
    ),
    tags={"agent:blog_writer"},
)
async def get_customer_context(customer_id: int) -> dict:
    async with mcp_db_context() as (ctx, db):
        customer = await _check_customer_access(ctx, db, customer_id)

        # Brand voice
        bv_row = (await db.execute(
            select(BrandVoice).where(BrandVoice.customer_id == customer_id)
        )).scalar_one_or_none()
        brand_voice = None
        if bv_row:
            brand_voice = {
                "tone_descriptors": bv_row.tone_descriptors,
                "voice_detail": bv_row.voice_detail,
                "dos": bv_row.dos,
                "donts": bv_row.donts,
                "example_phrases": bv_row.example_phrases,
            }

        # Brand voice inputs (content samples)
        inputs = (await db.execute(
            select(BrandVoiceInput)
            .where(BrandVoiceInput.customer_id == customer_id)
            .order_by(BrandVoiceInput.created_at.desc())
            .limit(20)
        )).scalars().all()

        # Target audiences
        audiences = (await db.execute(
            select(TargetAudience)
            .where(TargetAudience.customer_id == customer_id)
            .order_by(TargetAudience.rank)
        )).scalars().all()

        # Products and services
        products = (await db.execute(
            select(ProductOrService)
            .where(ProductOrService.customer_id == customer_id)
            .order_by(ProductOrService.sort_order)
        )).scalars().all()

        # Info base — key messages first, then rest (cap at 30)
        info = (await db.execute(
            select(InfoBaseEntry)
            .where(InfoBaseEntry.customer_id == customer_id)
            .order_by(InfoBaseEntry.is_key_message.desc(), InfoBaseEntry.created_at.desc())
            .limit(30)
        )).scalars().all()

        return {
            "customer": {
                "id": customer.id,
                "name": customer.name,
                "website_url": customer.website_url,
                "industry_id": customer.industry_id,
            },
            "brand_voice": brand_voice,
            "brand_voice_inputs": [
                {"input_type": i.input_type, "content": i.content, "notes": i.notes}
                for i in inputs
            ],
            "target_audiences": [
                {
                    "id": a.id,
                    "name": a.name,
                    "description": a.description,
                    "buyer_stage": a.buyer_stage,
                    "pain_points": a.pain_points,
                    "goals": a.goals,
                    "demographics": a.demographics,
                    "psychographics": a.psychographics,
                }
                for a in audiences
            ],
            "products_and_services": [
                {
                    "id": p.id,
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "is_featured": p.is_featured,
                    "url": p.url,
                }
                for p in products
            ],
            "info_base": [
                {
                    "title": e.title,
                    "content": e.content,
                    "category": e.category,
                    "is_key_message": e.is_key_message,
                }
                for e in info
            ],
        }


@mcp_tool(
    description="Get a blog post by ID including its current body content.",
    tags={"agent:blog_writer"},
)
async def get_blog_post(customer_id: int, post_id: int) -> dict:
    async with mcp_db_context() as (ctx, db):
        await _check_customer_access(ctx, db, customer_id)
        post = await db.get(BlogPost, post_id)
        if post is None or post.customer_id != customer_id:
            raise ValueError(f"Blog post {post_id} not found")
        template_data = None
        if post.template_key:
            tmpl = await db.get(BlogTemplate, post.template_key)
            if tmpl:
                template_data = {
                    "label": tmpl.label,
                    "structure_prompt": tmpl.structure_prompt,
                    "suggested_word_count": {
                        "min": tmpl.suggested_word_count_min,
                        "max": tmpl.suggested_word_count_max,
                    },
                }

        return {
            "id": post.id,
            "title": post.title,
            "slug": post.slug,
            "status": post.status,
            "topic": post.topic,
            "template_key": post.template_key,
            "template": template_data,
            "target_audience_id": post.target_audience_id,
            "body_markdown": post.body_markdown,
            "excerpt": post.excerpt,
            "focus_keyword": post.focus_keyword,
            "meta_description": post.meta_description,
            "word_count": post.word_count,
        }


@mcp_tool(
    description=(
        "Create a new draft blog post for a customer. "
        "Returns the created post id and slug."
    ),
    tags={"agent:blog_writer"},
)
async def create_blog_post(
    customer_id: int,
    title: str,
    body_markdown: str,
    topic: str | None = None,
    template_key: str | None = None,
    target_audience_id: int | None = None,
    focus_keyword: str | None = None,
    meta_description: str | None = None,
    excerpt: str | None = None,
) -> dict:
    async with mcp_db_context() as (ctx, db):
        customer = await _check_customer_access(ctx, db, customer_id)

        if target_audience_id is not None:
            ta = await db.get(TargetAudience, target_audience_id)
            if ta is None or ta.customer_id != customer_id:
                raise ValueError("Invalid target_audience_id")

        slug = await _alloc_slug(db, customer_id, _slugify(title))
        wc = len(body_markdown.split()) if body_markdown else 0
        reading_time = max(60, round(wc / 200 * 60))

        post = BlogPost(
            partner_id=customer.partner_id,
            customer_id=customer_id,
            created_by_user_id=ctx.user.id,
            title=title,
            slug=slug,
            topic=topic,
            template_key=template_key,
            target_audience_id=target_audience_id,
            body_markdown=body_markdown,
            focus_keyword=focus_keyword,
            meta_description=meta_description,
            excerpt=excerpt,
            word_count=wc,
            reading_time_sec=reading_time,
            generated_by_agent_key="blog_writer",
        )
        db.add(post)
        await db.flush()

        db.add(BlogPostVersion(
            post_id=post.id,
            partner_id=post.partner_id,
            body_markdown=body_markdown,
            body_json=None,
            word_count=wc,
            created_by_user_id=ctx.user.id,
            source="ai:blog_writer",
            note="Initial draft generated by blog writer agent",
        ))
        await db.flush()
        await db.refresh(post)

        return {
            "id": post.id,
            "title": post.title,
            "slug": post.slug,
            "status": post.status,
            "word_count": post.word_count,
        }


@mcp_tool(
    description=(
        "Update an existing blog post's content and/or metadata. "
        "Only provide the fields you want to change."
    ),
    tags={"agent:blog_writer"},
)
async def update_blog_post(
    customer_id: int,
    post_id: int,
    body_markdown: str | None = None,
    title: str | None = None,
    excerpt: str | None = None,
    focus_keyword: str | None = None,
    meta_description: str | None = None,
) -> dict:
    async with mcp_db_context() as (ctx, db):
        await _check_customer_access(ctx, db, customer_id)
        post = await db.get(BlogPost, post_id)
        if post is None or post.customer_id != customer_id:
            raise ValueError(f"Blog post {post_id} not found")

        if post.status in ("published", "archived"):
            raise ValueError(f"Cannot edit body while post is '{post.status}'")

        body_changed = False
        if body_markdown is not None:
            post.body_markdown = body_markdown
            wc = len(body_markdown.split())
            post.word_count = wc
            post.reading_time_sec = max(60, round(wc / 200 * 60))
            body_changed = True
        if title is not None:
            post.title = title
        if excerpt is not None:
            post.excerpt = excerpt
        if focus_keyword is not None:
            post.focus_keyword = focus_keyword
        if meta_description is not None:
            post.meta_description = meta_description

        if body_changed:
            db.add(BlogPostVersion(
                post_id=post.id,
                partner_id=post.partner_id,
                body_markdown=post.body_markdown,
                body_json=post.body_json,
                word_count=post.word_count,
                created_by_user_id=ctx.user.id,
                source="ai:blog_writer",
                note=f"Updated by blog writer agent at {datetime.now(tz=timezone.utc).isoformat()}",
            ))

        await db.flush()
        await db.refresh(post)

        return {
            "id": post.id,
            "title": post.title,
            "slug": post.slug,
            "status": post.status,
            "word_count": post.word_count,
        }
