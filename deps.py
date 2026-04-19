from fastapi.security import HTTPBearer

http_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="JWT",
    description="Access token from POST /auth/login or POST /auth/register (Bearer).",
)
