"""
ADMIN MOLTBOOK API — Genesi
Endpoint per monitorare il loop di auto-miglioramento via Moltbook.
"""

from fastapi import APIRouter, Depends
from auth.router import require_admin
from auth.models import AuthUser
from core.storage import storage
from core.moltbook_service import moltbook_service

router = APIRouter(prefix="/admin/moltbook", tags=["admin-moltbook"])


@router.get("/status")
async def moltbook_status(_: AuthUser = Depends(require_admin)):
    """Ritorna lo stato del loop di auto-apprendimento Moltbook."""

    # Heartbeat state
    state = await storage.load("moltbook:state", default={"heartbeat_count": 0})

    # Interaction log stats
    ilog = await storage.load("moltbook:interaction_log",
                              default={"interactions": [], "last_consolidated_at": None})
    interactions = ilog.get("interactions", [])
    by_type: dict[str, int] = {}
    for rec in interactions:
        t = rec.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    # Engagement on published posts (upvotes/comments aggiornati da _check_post_engagement)
    insight_tracker = await storage.load("moltbook:insight_tracker",
                                         default={"posts": []})
    posts = insight_tracker.get("posts", [])
    total_upvotes = sum(p.get("upvotes", 0) for p in posts)
    total_comments = sum(p.get("comments", 0) for p in posts)

    # Dati live dal profilo Moltbook (karma, post reali, commenti reali)
    live_profile: dict = {}
    try:
        live_profile = await moltbook_service.get_my_activity()
    except Exception:
        pass

    # Latest consolidated insights
    insights_data = await storage.load("moltbook:interaction_insights", default={})
    insights = insights_data.get("insights", [])
    top_topics = insights_data.get("top_topics", [])
    recommended_next = insights_data.get("recommended_next", "")
    consolidated_at = insights_data.get("consolidated_at")
    interactions_analyzed = insights_data.get("interactions_analyzed", 0)

    # Agent profiles (per-agent memory)
    agent_profiles = await storage.load("moltbook:agent_profiles", default={})
    agents_known = len(agent_profiles)
    total_exchanges = sum(p.get("exchange_count", 0) for p in agent_profiles.values())

    # Lab feedback cycle observations from Moltbook
    lab_data = await storage.load("lab:feedback_events", default={"events": []})
    moltbook_obs = [
        e for e in lab_data.get("events", [])
        if e.get("source") == "moltbook_interaction_log"
    ]

    return {
        "heartbeat_count": state.get("heartbeat_count", 0),
        "interaction_stats": {
            "total": len(interactions),
            "by_type": by_type,
            "last_consolidated_at": ilog.get("last_consolidated_at"),
        },
        "engagement": {
            "posts_published": len(posts),
            "total_upvotes": total_upvotes,
            "total_comments": total_comments,
        },
        # Dati live dal sito Moltbook (fonte autoritativa)
        "live_profile": {
            "karma": live_profile.get("karma", None),
            "followers": live_profile.get("followers", None),
            "posts_count": live_profile.get("posts_count", None),
            "comments_count": live_profile.get("comments_count", None),
        },
        "agent_memory": {
            "agents_known": agents_known,
            "total_exchanges": total_exchanges,
        },
        "last_consolidation": {
            "consolidated_at": consolidated_at,
            "interactions_analyzed": interactions_analyzed,
            "insights": insights,
            "technical_feedback": insights_data.get("technical_feedback", []),
            "top_topics": top_topics,
            "recommended_next": recommended_next,
        },
        "lab_cycle": {
            "moltbook_observations_fed": len(moltbook_obs),
            "last_observation": moltbook_obs[-1].get("observation") if moltbook_obs else None,
        },
    }
