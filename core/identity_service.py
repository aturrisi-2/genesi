import logging
from core.storage import storage
from core.models.profile_model import UserProfile

logger = logging.getLogger(__name__)

def normalize_profile_dict(data: dict) -> dict:
    """
    Normalize legacy profile data to match the Pydantic model schema.
    """
    # Normalize pets
    pets = data.get("pets", [])
    if isinstance(pets, dict):
        pets = [pets]
    elif not isinstance(pets, list):
        pets = []
    data["pets"] = pets

    # Normalize children
    children = data.get("children", [])
    normalized_children = []
    seen = set()
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                name = str(child.get("name", "")).strip()
            else:
                name = str(child).strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized_children.append({"name": name})
    data["children"] = normalized_children

    return data

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
    if any(kw in msg_lower for kw in ["come mi chiamo", "quale è il mio nome", "quale e' il mio nome",
                                        "qual è il mio nome", "qual e' il mio nome"]):
        name = profile.name
        if name:
            response = f"Ti chiami {name.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif any(kw in msg_lower for kw in ["dove vivo", "dove abito", "sai dove vivo", "sai dove abito"]):
        # Check raw profile first (city not in UserProfile model)
        city = raw_profile.get("city")
        if not city:
            city = profile.city if hasattr(profile, 'city') else None
        if city:
            response = f"Vivi a {city.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "che lavoro faccio" in msg_lower or "cosa faccio" in msg_lower:
        profession = profile.profession
        if profession:
            response = f"Sei un {profession.strip().lower()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come si chiama mia moglie" in msg_lower or "come si chiama mio marito" in msg_lower:
        spouse = profile.spouse
        if spouse:
            response = f"Il tuo coniuge si chiama {spouse.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come si chiama il mio cane" in msg_lower:
        pets = profile.pets
        dog = next((pet for pet in pets if pet.type == "dog"), None)
        if dog:
            response = f"Il tuo cane si chiama {dog.name.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come si chiama la mia gatta" in msg_lower:
        pets = profile.pets
        cat = next((pet for pet in pets if pet.type == "cat"), None)
        if cat:
            response = f"La tua gatta si chiama {cat.name.strip().title()}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come si chiamano i miei figli" in msg_lower:
        children = profile.children
        names = [c.name for c in children]
        if names:
            response = f"I tuoi figli si chiamano {', '.join(names)}."
        else:
            response = "Non me lo hai ancora detto."
    elif any(kw in msg_lower for kw in ["cosa mi piace", "che musica mi piace",
                                          "quali sono i miei interessi", "quale frutto mi piace"]):
        interests = profile.interests
        if interests:
            response = f"Ti piace: {', '.join(interests)}."
        else:
            response = "Non me lo hai ancora detto."
    elif "quali sono le mie preferenze" in msg_lower:
        preferences = profile.preferences
        if preferences:
            response = f"Le tue preferenze sono: {', '.join(preferences)}."
        else:
            response = "Non me lo hai ancora detto."
    elif "come sono" in msg_lower or "che tipo di persona sono" in msg_lower:
        traits = profile.traits
        if traits:
            response = f"Sei una persona {', '.join(traits)}."
        else:
            response = "Non me lo hai ancora detto."
    elif any(kw in msg_lower for kw in ["chi sono", "cosa sai di me"]):
        response = _build_full_identity_summary(profile, raw_profile)
    else:
        response = None

    logger.info("IDENTITY_RESPONSE user=%s response=%s", user_id, response)
    return response


def _build_full_identity_summary(profile, raw_profile=None) -> str:
    """Build a complete identity summary from all known profile fields."""
    facts = []
    if profile.name:
        facts.append(f"ti chiami {profile.name.strip().title()}")
    if raw_profile and raw_profile.get("city"):
        facts.append(f"vivi a {raw_profile['city'].strip().title()}")
    if profile.profession:
        facts.append(f"lavori come {profile.profession.strip().lower()}")
    if profile.spouse:
        facts.append(f"il tuo coniuge si chiama {profile.spouse.strip().title()}")
    if profile.children:
        names = [c.name for c in profile.children]
        facts.append(f"i tuoi figli si chiamano {', '.join(names)}")
    if profile.pets:
        pet_descs = [f"{p.name} ({p.type})" for p in profile.pets]
        facts.append(f"hai {', '.join(pet_descs)}")
    if profile.interests:
        facts.append(f"ti piace: {', '.join(profile.interests)}")
    if profile.preferences:
        facts.append(f"le tue preferenze sono: {', '.join(profile.preferences)}")
    if profile.traits:
        facts.append(f"sei una persona {', '.join(profile.traits)}")

    if facts:
        return f"Ecco cosa so di te: {', '.join(facts)}."
    return "Non me lo hai ancora detto."
