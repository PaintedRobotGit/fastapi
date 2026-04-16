from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    return pwd_context.verify(plain, hashed)


def create_access_token(subject_user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(subject_user_id), "exp": expire}
    encoded = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    if isinstance(encoded, bytes):
        return encoded.decode("utf-8")
    return encoded


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def safe_decode_access_token(token: str) -> dict | None:
    try:
        return decode_access_token(token)
    except jwt.PyJWTError:
        return None
