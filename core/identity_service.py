import logging
from core.storage import storage

logger = logging.getLogger(__name__)

async def handle_identity_question(user_id: str, message: str) -> str:
    """
    Handle identity-related questions and return a deterministic response.
    """
    msg_lower = message.lower().strip()
    logger.info("IDENTITY_ROUTE_ENTER user=%s", user_id)

    # Load profile directly from storage
    profile = {}
    logger.info("IDENTITY_PROFILE_LOADED user=%s profile=%s", user_id, profile)

    if not profile.get("profession"):
        logger.warning("IDENTITY_MISSING_FIELD profession")

    # Determine response based on message
    if "come mi chiamo" in msg_lower:
        name = profile.get("name")
        if name:
            response = f"Ti chiami {name.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "dove vivo" in msg_lower:
        city = profile.get("city")
        if city:
            response = f"Vivi a {city.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "che lavoro faccio" in msg_lower:
        profession = profile.get("profession")
        if profession:
            response = f"Sei un {profession.strip().lower()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "chi sono" in msg_lower:
        name = profile.get("name")
        city = profile.get("city")
        profession = profile.get("profession")
        parts = []
        if name:
            parts.append(f"Ti chiami {name.strip().title()}")
        if city:
            parts.append(f"vivi a {city.strip().title()}")
        if profession:
            parts.append(f"sei un {profession.strip().lower()}")
        if parts:
            response = ", ".join(parts) + "."
        else:
            response = "Non me lo hai ancora detto."
    else:
        response = None

    logger.info("IDENTITY_RESPONSE user=%s response=%s", user_id, response)
    return response
