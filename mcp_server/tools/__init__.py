"""
MCP tool registry.

Agent assignments live in each tool's decorator via tags — e.g.
`tags={"agent:general"}` or `tags={"agent:general", "agent:copywriter"}`.
Use the special tag `"agent:*"` to make a tool available to all agents.
Omitting agent tags entirely also means all agents (safe default).

`TOOL_AGENTS` is built automatically from those tags at startup — never
edit it manually. To assign a tool to an agent, update its decorator.
"""

try:
    from fastmcp.tools import Tool as _FastMCPTool  # 2.x + 3.x package export
except ImportError:
    _FastMCPTool = None  # type: ignore[assignment]

from mcp_server.tools.customers import get_customer, list_customers  # noqa: F401
from mcp_server.server import mcp


def _build_tool_manifest() -> dict[str, list[str]]:
    manifest: dict[str, list[str]] = {}
    for component in mcp._local_provider._components.values():
        if _FastMCPTool is not None and not isinstance(component, _FastMCPTool):
            continue
        if not hasattr(component, "name") or not hasattr(component, "tags"):
            continue
        agents = [
            t.removeprefix("agent:")
            for t in (component.tags or set())
            if t.startswith("agent:")
        ]
        manifest[component.name] = agents if agents else ["*"]
    return manifest


TOOL_AGENTS: dict[str, list[str]] = _build_tool_manifest()
