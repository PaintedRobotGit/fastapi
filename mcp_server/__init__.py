from mcp_server.server import mcp
from mcp_server.middleware import MCPAuthMiddleware

# Import tool modules to register their @mcp.tool decorators on the mcp instance.
# Add new tool modules here as the surface area grows.
import mcp_server.tools.customers  # noqa: F401

__all__ = ["mcp", "MCPAuthMiddleware"]
