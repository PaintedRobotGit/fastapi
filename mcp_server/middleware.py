from contextvars import ContextVar

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from security import safe_decode_access_token

# Holds the raw Bearer token for the duration of a single MCP HTTP request.
# ContextVar is propagated through the asyncio task context, so it is visible
# inside tool coroutines that are awaited within the same task.
_current_token: ContextVar[str | None] = ContextVar("_current_token", default=None)


class MCPAuthMiddleware:
    """Pure-ASGI JWT guard for the mounted MCP sub-app.

    Validates the Authorization: Bearer header before FastMCP sees the request,
    stores the token in _current_token so mcp_db_context() can retrieve it, and
    passes streaming responses through without buffering (safe for SSE transport).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        raw_auth = headers.get(b"authorization", b"").decode()

        if not raw_auth.lower().startswith("bearer "):
            await JSONResponse({"detail": "Not authenticated"}, status_code=401)(scope, receive, send)
            return

        token = raw_auth.split(" ", 1)[1]
        payload = safe_decode_access_token(token)
        if payload is None or "sub" not in payload:
            await JSONResponse({"detail": "Invalid or expired token"}, status_code=401)(scope, receive, send)
            return

        ctx_token = _current_token.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_token.reset(ctx_token)
