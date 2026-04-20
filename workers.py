from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from database import AsyncSessionLocal
from models import BlogPost, BlogPostVersion

logger = logging.getLogger(__name__)


async def _publish_due_posts() -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            now = datetime.now(tz=timezone.utc)
            grace = now + timedelta(seconds=5)
            result = await db.execute(
                select(BlogPost)
                .where(BlogPost.status == "scheduled", BlogPost.scheduled_for <= grace)
                .with_for_update(skip_locked=True)
                .limit(100)
            )
            for post in result.scalars().all():
                try:
                    post.status = "published"
                    post.published_at = now
                    post.published_by_user_id = None
                    post.scheduled_for = None
                    db.add(BlogPostVersion(
                        post_id=post.id,
                        partner_id=post.partner_id,
                        body_markdown=post.body_markdown,
                        body_json=post.body_json,
                        word_count=post.word_count,
                        source="status_change",
                        note=f"Auto-published by scheduler at {now.isoformat()}",
                    ))
                except Exception:
                    logger.exception("Failed to auto-publish post %s", post.id)


async def scheduled_publish_worker() -> None:
    """Runs every 60 s and promotes scheduled posts whose scheduled_for has arrived."""
    while True:
        try:
            await _publish_due_posts()
        except Exception:
            logger.exception("scheduled_publish_worker error")
        await asyncio.sleep(60)
