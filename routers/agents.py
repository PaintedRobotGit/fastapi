from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from access import AccessContext, effective_partner_id, get_access_context
from database import get_db
from mcp_server.tools import TOOL_AGENTS
from models import AppAgent
from schemas import AppAgentRead

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AppAgentRead])
async def list_agents(
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> list[AppAgent]:
    """
    Return all enabled agents visible to the current user.
    Global agents (partner_id IS NULL) are available to everyone.
    Partner-specific agents are only returned when they match the caller's partner.
    """
    ep = await effective_partner_id(db, ctx.user)
    stmt = (
        select(AppAgent)
        .where(
            AppAgent.enabled.is_(True),
            (AppAgent.partner_id.is_(None)) | (AppAgent.partner_id == ep)
        )
        .order_by(AppAgent.is_default.desc(), AppAgent.key)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/tool-manifest", response_model=dict[str, list[str]])
async def get_tool_manifest(
    _ctx: AccessContext = Depends(get_access_context),
) -> dict[str, list[str]]:
    """
    Returns which MCP tools each agent key may call.
    Values are lists of agent keys; "*" means all agents.
    Nuxt uses this to filter the MCP tool list per active agent.
    """
    return TOOL_AGENTS
