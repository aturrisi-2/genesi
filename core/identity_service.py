import logging
from core.storage import storage
from core.models.profile_model import UserProfile

logger = logging.getLogger(__name__)

def normalize_profile_dict(profile_dict):
    # Add temporary verification log
    logger.info("NORMALIZE_PROFILE_DICT profile_dict=%s", profile_dict)
    return profile_dict

async def handle_identity_question(user_id: str, message: str) -> str:
    """
    Handle identity-related questions and return a deterministic response.
    """
    msg_lower = message.lower().strip()
    logger.info("IDENTITY_ROUTE_ENTER user=%s", user_id)

    # Load profile directly from storage
    raw_profile = await storage.load(f"profile:{user_id}", default={})
    normalized = normalize_profile_dict(raw_profile)

    try:
        profile = UserProfile(**normalized)
    except Exception as e:
        logger.critical(
            "PROFILE_SCHEMA_VIOLATION user=%s data=%s error=%s",
            user_id,
            normalized,
            e
        )
        raise RuntimeError("Invalid profile structure — system halted")

    logger.info("IDENTITY_PROFILE_SNAPSHOT user=%s profile=%s", user_id, profile)

    # Determine response based on message
    if "come mi chiamo" in msg_lower:
        name = profile.name
        if name:
            response = f"Ti chiami {name.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "che lavoro faccio" in msg_lower:
        profession = profile.profession
        if profession:
            response = f"Sei un {profession.strip().lower()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come si chiama mia moglie" in msg_lower:
        spouse = profile.spouse
        if spouse:
            response = f"Tua moglie si chiama {spouse.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come si chiama il mio cane" in msg_lower:
        pets = profile.pets
        dog = next(
            (
                pet for pet in pets
                if isinstance(pet, dict) and pet.get("type") == "dog"
            ),
            None
        )
        if dog:
            response = f"Il tuo cane si chiama {dog['name'].strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come si chiamano i miei figli" in msg_lower:
        children = profile.children
        names = [c.name for c in children]
        if names:
            response = f"I tuoi figli si chiamano {', '.join(names)}."
        else:
            response = "Non me lo hai ancora detto."
    else:
        response = None

    logger.info("IDENTITY_RESPONSE user=%s response=%s", user_id, response)
    return response
