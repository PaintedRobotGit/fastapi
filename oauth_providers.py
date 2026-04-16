"""Verify OAuth tokens from Google and Apple (server-side)."""

from __future__ import annotations

import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jwt import PyJWKClient

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_jwks_client: PyJWKClient | None = None


def get_apple_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(APPLE_JWKS_URL)
    return _jwks_client


def verify_google_id_token(token: str, client_id: str) -> dict:
    request = google_requests.Request()
    return google_id_token.verify_oauth2_token(token, request, client_id)


def verify_apple_identity_token(token: str, client_id: str) -> dict:
    """Validates Apple's `identity_token` (JWT) and returns claims."""
    client = get_apple_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=APPLE_ISSUER,
    )
