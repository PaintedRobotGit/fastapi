"""
Tool-agent assignment registry.

Use @mcp_tool in place of @mcp.tool. It's a drop-in wrapper that
registers the tool with FastMCP and simultaneously populates TOOL_AGENTS
so GET /agents/tool-manifest can return the mapping.

Agent tags follow the same convention as before:
  tags={"agent:general"}        → only the general agent
  tags={"agent:general", "agent:copywriter"}
  tags={"agent:*"} or no tags   → all agents
"""

from mcp_server.server import mcp

TOOL_AGENTS: dict[str, list[str]] = {}


def mcp_tool(description: str = "", tags: set[str] | None = None, **kwargs):
    """Drop-in for @mcp.tool that also registers agent assignments."""
    def decorator(fn):
        tool_name = kwargs.get("name", fn.__name__)
        agents = [t.removeprefix("agent:") for t in (tags or set()) if t.startswith("agent:")]
        TOOL_AGENTS[tool_name] = agents if agents else ["*"]
        return mcp.tool(description=description, tags=tags, **kwargs)(fn)
    return decorator
