from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from access import AccessContext, effective_partner_id, ensure_customer_resource, get_access_context
from database import get_db
from models import BlogPost, BlogPostVersion, Customer, TargetAudience
from schemas import (
    BlogPostCreate,
    BlogPostListResponse,
    BlogPostRead,
    BlogPostRejectReviewInput,
    BlogPostScheduleInput,
    BlogPostSubmitReviewInput,
    BlogPostSummaryRead,
    BlogPostUpdate,
    BlogPostVersionListResponse,
    BlogPostVersionRead,
)

router = APIRouter(prefix="/customers/{customer_id}/blog-posts", tags=["Blog Posts"])


# ── Slug helpers ─────────────────────────────────────────────────────────────

def _slugify(title: str, max_len: int = 80) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:max_len] or "post"


async def _alloc_slug(
    db: AsyncSession,
    customer_id: int,
    base_slug: str,
    exclude_id: int | None = None,
) -> str:
    slug = base_slug
    n = 2
    while True:
        stmt = select(BlogPost.id).where(
            BlogPost.customer_id == customer_id,
            BlogPost.slug == slug,
        )
        if exclude_id is not None:
            stmt = stmt.where(BlogPost.id != exclude_id)
        exists = (await db.execute(stmt)).scalar_one_or_none()
        if exists is None:
            return slug
        slug = f"{base_slug[:77]}-{n}"
        n += 1


# ── Access helpers ────────────────────────────────────────────────────────────

async def _get_customer(
    db: AsyncSession,
    ctx: AccessContext,
    customer_id: int,
) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await ensure_customer_resource(ctx, db, customer)
    return customer


async def _get_post(
    db: AsyncSession,
    ctx: AccessContext,
    customer_id: int,
    post_id: int,
) -> BlogPost:
    await _get_customer(db, ctx, customer_id)
    post = await db.get(BlogPost, post_id)
    if post is None or post.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


# ── Version helper ────────────────────────────────────────────────────────────

async def _add_version(
    db: AsyncSession,
    post: BlogPost,
    source: str,
    user_id: int | None,
    note: str | None = None,
    *,
    autosave_throttle: bool = False,
) -> None:
    if autosave_throttle:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
        recent = (await db.execute(
            select(BlogPostVersion)
            .where(
                BlogPostVersion.post_id == post.id,
                BlogPostVersion.source == "autosave",
                BlogPostVersion.created_at > cutoff,
            )
            .order_by(BlogPostVersion.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if recent is not None:
            recent.body_markdown = post.body_markdown
            recent.body_json = post.body_json
            recent.word_count = post.word_count
            return
    db.add(BlogPostVersion(
        post_id=post.id,
        partner_id=post.partner_id,
        body_markdown=post.body_markdown,
        body_json=post.body_json,
        word_count=post.word_count,
        created_by_user_id=user_id,
        source=source,
        note=note,
    ))


def _bad_transition(current: str, target: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=f"Cannot transition from '{current}' to '{target}'.",
    )


def _reading_time(word_count: int) -> int:
    return max(60, round(word_count / 200 * 60))


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=BlogPostListResponse)
async def list_blog_posts(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    status: list[str] = Query(default=[]),
    include_archived: bool = Query(False),
    q: str | None = Query(None),
    sort: str = Query("updated_at"),
    order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> BlogPostListResponse:
    await _get_customer(db, ctx, customer_id)

    stmt = select(BlogPost).where(BlogPost.customer_id == customer_id)

    if status:
        stmt = stmt.where(BlogPost.status.in_(status))
    elif not include_archived:
        stmt = stmt.where(BlogPost.status != "archived")

    if include_archived and not status:
        pass  # show all including archived
    elif include_archived and status and "archived" not in status:
        stmt = stmt.where(BlogPost.status.in_(status + ["archived"]))

    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(
            BlogPost.title.ilike(pattern),
            BlogPost.excerpt.ilike(pattern),
            BlogPost.focus_keyword.ilike(pattern),
        ))

    sort_col = {
        "updated_at": BlogPost.updated_at,
        "created_at": BlogPost.created_at,
        "published_at": BlogPost.published_at,
        "title": BlogPost.title,
    }.get(sort, BlogPost.updated_at)
    stmt = stmt.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = list((await db.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return BlogPostListResponse(items=rows, total=total)


# ── Get ───────────────────────────────────────────────────────────────────────

@router.get("/{post_id}", response_model=BlogPostRead)
async def get_blog_post(
    customer_id: int,
    post_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    return await _get_post(db, ctx, customer_id, post_id)


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=BlogPostRead, status_code=201)
async def create_blog_post(
    customer_id: int,
    payload: BlogPostCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    customer = await _get_customer(db, ctx, customer_id)

    if payload.target_audience_id is not None:
        ta = await db.get(TargetAudience, payload.target_audience_id)
        if ta is None or ta.customer_id != customer_id:
            raise HTTPException(status_code=422, detail="Invalid target_audience_id.")

    ep = await effective_partner_id(db, ctx.user)
    if ep is None:
        raise HTTPException(status_code=403, detail="No partner associated with this account.")

    base_slug = _slugify(payload.slug or payload.title)
    slug = await _alloc_slug(db, customer_id, base_slug)

    wc = payload.body_markdown.split().__len__() if payload.body_markdown else 0
    post = BlogPost(
        partner_id=customer.partner_id,
        customer_id=customer_id,
        created_by_user_id=ctx.user.id,
        title=payload.title,
        slug=slug,
        template_key=payload.template_key,
        topic=payload.topic,
        target_audience_id=payload.target_audience_id,
        body_markdown=payload.body_markdown,
        body_json=payload.body_json,
        body_html=payload.body_html,
        focus_keyword=payload.focus_keyword,
        meta_description=payload.meta_description,
        generated_by_agent_key=payload.generated_by_agent_key,
        word_count=wc,
        reading_time_sec=_reading_time(wc),
    )
    db.add(post)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Could not create post (slug collision or constraint).") from e
    await db.refresh(post)
    return post


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{post_id}", response_model=BlogPostRead)
async def update_blog_post(
    customer_id: int,
    post_id: int,
    payload: BlogPostUpdate,
    save_kind: str = Query("manual"),
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)

    updates = payload.model_dump(exclude_unset=True)
    body_touched = any(k in updates for k in ("body_markdown", "body_json", "body_html"))

    if body_touched and post.status in ("published", "archived"):
        label = "Unpublish" if post.status == "published" else "Restore"
        raise HTTPException(
            status_code=422,
            detail=f"Cannot edit body while post is '{post.status}'. {label} it first.",
        )

    if "slug" in updates and updates["slug"] is not None:
        new_slug = _slugify(updates["slug"])
        updates["slug"] = await _alloc_slug(db, customer_id, new_slug, exclude_id=post_id)

    if "target_audience_id" in updates and updates["target_audience_id"] is not None:
        ta = await db.get(TargetAudience, updates["target_audience_id"])
        if ta is None or ta.customer_id != customer_id:
            raise HTTPException(status_code=422, detail="Invalid target_audience_id.")

    if "word_count" in updates and "reading_time_sec" not in updates:
        updates["reading_time_sec"] = _reading_time(updates["word_count"])

    for field, value in updates.items():
        setattr(post, field, value)

    if body_touched:
        is_auto = save_kind == "autosave"
        await _add_version(
            db, post,
            source="autosave" if is_auto else "manual_save",
            user_id=ctx.user.id,
            autosave_throttle=is_auto,
        )

    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Slug already in use.") from e
    await db.refresh(post)
    return post


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{post_id}", status_code=204)
async def delete_blog_post(
    customer_id: int,
    post_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    post = await _get_post(db, ctx, customer_id, post_id)
    await db.delete(post)
    await db.flush()


# ── Status transitions ────────────────────────────────────────────────────────

@router.post("/{post_id}/submit-review", response_model=BlogPostRead)
async def submit_review(
    customer_id: int,
    post_id: int,
    payload: BlogPostSubmitReviewInput = BlogPostSubmitReviewInput(),
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)
    if post.status != "draft":
        raise _bad_transition(post.status, "review")
    post.status = "review"
    post.review_requested_at = datetime.now(tz=timezone.utc)
    if payload.reviewer_user_id is not None:
        post.reviewer_user_id = payload.reviewer_user_id
    if payload.review_notes is not None:
        post.review_notes = payload.review_notes
    await _add_version(db, post, "status_change", ctx.user.id, note="Submitted for review")
    await db.flush()
    await db.refresh(post)
    return post


@router.post("/{post_id}/reject-review", response_model=BlogPostRead)
async def reject_review(
    customer_id: int,
    post_id: int,
    payload: BlogPostRejectReviewInput = BlogPostRejectReviewInput(),
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)
    if post.status != "review":
        raise _bad_transition(post.status, "draft")
    post.status = "draft"
    if payload.review_notes is not None:
        post.review_notes = payload.review_notes
    await _add_version(db, post, "status_change", ctx.user.id, note="Sent back to draft")
    await db.flush()
    await db.refresh(post)
    return post


@router.post("/{post_id}/approve", response_model=BlogPostRead)
async def approve(
    customer_id: int,
    post_id: int,
    payload: BlogPostScheduleInput,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)
    if post.status != "review":
        raise _bad_transition(post.status, "scheduled")
    _validate_future(payload.scheduled_for)
    post.status = "scheduled"
    post.scheduled_for = payload.scheduled_for
    await _add_version(db, post, "status_change", ctx.user.id, note=f"Approved & scheduled for {payload.scheduled_for.isoformat()}")
    await db.flush()
    await db.refresh(post)
    return post


@router.post("/{post_id}/schedule", response_model=BlogPostRead)
async def schedule(
    customer_id: int,
    post_id: int,
    payload: BlogPostScheduleInput,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)
    if post.status != "draft":
        raise _bad_transition(post.status, "scheduled")
    _validate_future(payload.scheduled_for)
    post.status = "scheduled"
    post.scheduled_for = payload.scheduled_for
    await _add_version(db, post, "status_change", ctx.user.id, note=f"Scheduled for {payload.scheduled_for.isoformat()}")
    await db.flush()
    await db.refresh(post)
    return post


@router.post("/{post_id}/unschedule", response_model=BlogPostRead)
async def unschedule(
    customer_id: int,
    post_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)
    if post.status != "scheduled":
        raise _bad_transition(post.status, "draft")
    post.status = "draft"
    post.scheduled_for = None
    await _add_version(db, post, "status_change", ctx.user.id, note="Unscheduled")
    await db.flush()
    await db.refresh(post)
    return post


@router.post("/{post_id}/publish", response_model=BlogPostRead)
async def publish(
    customer_id: int,
    post_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)
    if post.status not in ("draft", "review", "scheduled"):
        raise _bad_transition(post.status, "published")
    now = datetime.now(tz=timezone.utc)
    post.status = "published"
    post.published_at = now
    post.published_by_user_id = ctx.user.id
    post.scheduled_for = None
    await _add_version(db, post, "status_change", ctx.user.id, note=f"Published by {ctx.user.email}")
    await db.flush()
    await db.refresh(post)
    return post


@router.post("/{post_id}/unpublish", response_model=BlogPostRead)
async def unpublish(
    customer_id: int,
    post_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)
    if post.status != "published":
        raise _bad_transition(post.status, "draft")
    post.status = "draft"
    post.published_at = None
    post.published_by_user_id = None
    await _add_version(db, post, "status_change", ctx.user.id, note="Unpublished")
    await db.flush()
    await db.refresh(post)
    return post


@router.post("/{post_id}/archive", response_model=BlogPostRead)
async def archive(
    customer_id: int,
    post_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)
    if post.status == "archived":
        raise _bad_transition(post.status, "archived")
    post.status = "archived"
    post.archived_at = datetime.now(tz=timezone.utc)
    await _add_version(db, post, "status_change", ctx.user.id, note="Archived")
    await db.flush()
    await db.refresh(post)
    return post


@router.post("/{post_id}/restore", response_model=BlogPostRead)
async def restore(
    customer_id: int,
    post_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)
    if post.status != "archived":
        raise _bad_transition(post.status, "draft")
    post.status = "draft"
    post.archived_at = None
    await _add_version(db, post, "status_change", ctx.user.id, note="Restored from archive")
    await db.flush()
    await db.refresh(post)
    return post


# ── Versions ──────────────────────────────────────────────────────────────────

@router.get("/{post_id}/versions", response_model=BlogPostVersionListResponse)
async def list_versions(
    customer_id: int,
    post_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> BlogPostVersionListResponse:
    await _get_post(db, ctx, customer_id, post_id)
    total = (await db.execute(
        select(func.count()).where(BlogPostVersion.post_id == post_id)
    )).scalar_one()
    rows = list((await db.execute(
        select(BlogPostVersion)
        .where(BlogPostVersion.post_id == post_id)
        .order_by(BlogPostVersion.created_at.desc())
        .offset(offset).limit(limit)
    )).scalars().all())
    return BlogPostVersionListResponse(items=rows, total=total)


@router.get("/{post_id}/versions/{version_id}", response_model=BlogPostVersionRead)
async def get_version(
    customer_id: int,
    post_id: int,
    version_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPostVersion:
    await _get_post(db, ctx, customer_id, post_id)
    version = await db.get(BlogPostVersion, version_id)
    if version is None or version.post_id != post_id:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


@router.post("/{post_id}/versions/{version_id}/restore", response_model=BlogPostRead)
async def restore_version(
    customer_id: int,
    post_id: int,
    version_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogPost:
    post = await _get_post(db, ctx, customer_id, post_id)
    if post.status not in ("draft", "review"):
        raise HTTPException(
            status_code=422,
            detail=f"Cannot restore a version while post is '{post.status}'.",
        )
    version = await db.get(BlogPostVersion, version_id)
    if version is None or version.post_id != post_id:
        raise HTTPException(status_code=404, detail="Version not found")
    post.body_markdown = version.body_markdown
    post.body_json = version.body_json
    post.word_count = version.word_count
    post.reading_time_sec = _reading_time(version.word_count)
    await _add_version(
        db, post, "manual_save", ctx.user.id,
        note=f"Restored from version {version_id}",
    )
    await db.flush()
    await db.refresh(post)
    return post


# ── Internal helper ───────────────────────────────────────────────────────────

def _validate_future(dt: datetime) -> None:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt < datetime.now(tz=timezone.utc) + timedelta(minutes=1):
        raise HTTPException(status_code=422, detail="scheduled_for must be at least 1 minute in the future.")
