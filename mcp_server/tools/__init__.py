"""
MCP tool registry.

Agent assignments live in each tool's decorator via tags — e.g.
`tags={"agent:general"}` or `tags={"agent:general", "agent:copywriter"}`.
Use the special tag `"agent:*"` to make a tool available to all agents.
Omitting agent tags entirely also means all agents (safe default).

`TOOL_AGENTS` is built automatically from those tags at startup — never
edit it manually. To assign a tool to an agent, update its decorator.
"""

from fastmcp.tools.base import Tool as FastMCPTool

from mcp_server.tools.customers import get_customer, list_customers  # noqa: F401
from mcp_server.server import mcp


def _build_tool_manifest() -> dict[str, list[str]]:
    manifest: dict[str, list[str]] = {}
    for component in mcp._local_provider._components.values():
        if not isinstance(component, FastMCPTool):
            continue
        agents = [
            t.removeprefix("agent:")
            for t in (component.tags or set())
            if t.startswith("agent:")
        ]
        manifest[component.name] = agents if agents else ["*"]
    return manifest


TOOL_AGENTS: dict[str, list[str]] = _build_tool_manifest()
