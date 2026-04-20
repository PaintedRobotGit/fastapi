from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from access import AccessContext, get_access_context
from database import get_db
from models import BlogTemplate
from schemas import BlogTemplateCreate, BlogTemplateRead, BlogTemplateUpdate

router = APIRouter(prefix="/blog-templates", tags=["Blog Templates"])


async def _get_or_404(db: AsyncSession, key: str) -> BlogTemplate:
    tmpl = await db.get(BlogTemplate, key)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return tmpl


@router.get("", response_model=list[BlogTemplateRead])
async def list_blog_templates(
    db: AsyncSession = Depends(get_db),
) -> list[BlogTemplate]:
    """Public — returns all active templates ordered for the picker UI."""
    result = await db.execute(
        select(BlogTemplate)
        .where(BlogTemplate.is_active.is_(True))
        .order_by(BlogTemplate.sort_order, BlogTemplate.key)
    )
    return list(result.scalars().all())


@router.get("/{key}", response_model=BlogTemplateRead)
async def get_blog_template(
    key: str,
    db: AsyncSession = Depends(get_db),
) -> BlogTemplate:
    """Public — returns a single template by key."""
    return await _get_or_404(db, key)


@router.post("", response_model=BlogTemplateRead, status_code=201)
async def create_blog_template(
    payload: BlogTemplateCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogTemplate:
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    existing = await db.get(BlogTemplate, payload.key)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Template key '{payload.key}' already exists")
    tmpl = BlogTemplate(**payload.model_dump())
    db.add(tmpl)
    await db.flush()
    await db.refresh(tmpl)
    return tmpl


@router.patch("/{key}", response_model=BlogTemplateRead)
async def update_blog_template(
    key: str,
    payload: BlogTemplateUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BlogTemplate:
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    tmpl = await _get_or_404(db, key)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tmpl, field, value)
    await db.flush()
    await db.refresh(tmpl)
    return tmpl


@router.delete("/{key}", status_code=204)
async def delete_blog_template(
    key: str,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    tmpl = await _get_or_404(db, key)
    await db.delete(tmpl)
    await db.flush()
