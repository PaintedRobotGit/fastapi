import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"  # Crockford base32 — no I, L, O, U
_LENGTH = 12
_RESERVED = {"new", "index", "settings", "dashboard", "admin", "api", "static", "login"}


def _random_slug() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))


async def generate_slug(db: AsyncSession, model_class) -> str:
    while True:
        slug = _random_slug()
        if slug in _RESERVED:
            continue
        exists = (await db.execute(select(model_class.id).where(model_class.slug == slug))).scalar_one_or_none()
        if exists is None:
            return slug
