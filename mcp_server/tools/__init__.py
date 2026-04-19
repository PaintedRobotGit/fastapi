"""
MCP tool registry.

Agent assignments live in each tool's decorator via tags — e.g.
`tags={"agent:general"}` or `tags={"agent:general", "agent:copywriter"}`.
Use the special tag `"agent:*"` to make a tool available to all agents.
Omitting agent tags entirely also means all agents (safe default).

`TOOL_AGENTS` is built automatically from those tags at startup — never
edit it manually. To assign a tool to an agent, update its decorator.
"""

from mcp_server.tools.customers import get_customer, list_customers  # noqa: F401
from mcp_server.server import mcp


def _build_tool_manifest() -> dict[str, list[str]]:
    manifest: dict[str, list[str]] = {}
    for name, tool in mcp._tool_manager.get_tools().items():
        agents = [
            t.removeprefix("agent:")
            for t in (tool.tags or set())
            if t.startswith("agent:")
        ]
        manifest[name] = agents if agents else ["*"]
    return manifest


TOOL_AGENTS: dict[str, list[str]] = _build_tool_manifest()
