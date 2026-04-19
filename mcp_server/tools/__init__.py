"""
MCP tool registry.

Agent assignments live in each tool's decorator via tags — e.g.
`tags={"agent:general"}` or `tags={"agent:general", "agent:copywriter"}`.
Use the special tag `"agent:*"` to make a tool available to all agents.
Omitting agent tags entirely also means all agents (safe default).

Use @mcp_tool (from mcp_server.tools.registry) instead of @mcp.tool so
the decorator also populates TOOL_AGENTS automatically. Never edit
TOOL_AGENTS manually — update the decorator instead.
"""

from mcp_server.tools.registry import TOOL_AGENTS, mcp_tool  # noqa: F401
from mcp_server.tools.customers import get_customer, list_customers  # noqa: F401
