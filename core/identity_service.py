import logging
from core.storage import storage

logger = logging.getLogger(__name__)

async def handle_identity_question(user_id: str, message: str) -> str:
    """
    Handle identity-related questions and return a deterministic response.
    """
    msg_lower = message.lower().strip()
    logger.info("IDENTITY_ROUTE_ENTER user=%s", user_id)

    # Determine response based on message
    if "come mi chiamo" in msg_lower:
        profile = await storage.load(f"profile:{user_id}", default={})
        name = profile.get("name")
        if name:
            response = f"Ti chiami {name.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "che lavoro faccio" in msg_lower:
        profile = await storage.load(f"profile:{user_id}", default={})
        profession = profile.get("profession")
        if profession:
            response = f"Sei un {profession.strip().lower()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come si chiama mia moglie" in msg_lower:
        relational = await storage.load(f"relational:{user_id}", default={})
        spouse = relational.get("spouse")
        if spouse:
            response = f"Tua moglie si chiama {spouse.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come si chiama il mio cane" in msg_lower:
        relational = await storage.load(f"relational:{user_id}", default={})
        pets = relational.get("pets", [])
        dog = next((pet for pet in pets if pet["type"] == "dog"), None)
        if dog:
            response = f"Il tuo cane si chiama {dog['name'].strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come si chiamano i miei figli" in msg_lower:
        relational = await storage.load(f"relational:{user_id}", default={})
        children = relational.get("children", [])
        if children:
            response = f"I tuoi figli si chiamano {', '.join(children)}."
        else:
            response = "Non me lo hai ancora detto."
    else:
        response = None

    logger.info("IDENTITY_RESPONSE user=%s response=%s", user_id, response)
    return response
