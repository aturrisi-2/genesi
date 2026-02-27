"""
IDENTITY EXTRACTOR - Genesi Core
Extracts stable identity traits from user messages using LLM classification.
Only saves declarative, stable, non-situational identity data.
Routing: uses llm_service (OpenRouter) — never calls OpenAI directly.
"""

import json
import logging
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IdentityUpdate(BaseModel):
    interests: List[str] = Field(default_factory=list)
    preferences: List[str] = Field(default_factory=list)
    traits: List[str] = Field(default_factory=list)
    pets: List[Dict[str, str]] = Field(default_factory=list)
    children: List[Dict[str, str]] = Field(default_factory=list)
    spouse: Optional[str] = None


EXTRACTION_PROMPT = """Sei un classificatore di identita' personale.
Analizza il messaggio dell'utente considerando il contesto recente, e estrai SOLO informazioni identitarie STABILI.

REGOLE:
- Salva SOLO dichiarazioni stabili (gusti, preferenze, tratti, nomi di animali domestici o familiari)
- Animali (pets) devono avere "type" (es. dog, cat) e "name"
- Figli (children) devono avere "name"
- Coniuge (spouse) e' una stringa col nome
- NON salvare stati temporanei (stanchezza, umore)
- Rispondi SOLO con JSON valido

ESEMPI:
- "Adoro la musica elettronica" -> {"interests": ["musica elettronica"]}
- "I miei gatti Mignolo e Prof" -> {"pets": [{"type": "cat", "name": "Mignolo"}, {"type": "cat", "name": "Prof"}]}
- "Mia figlia Zoe" -> {"children": [{"name": "Zoe"}]}

Rispondi con questo formato JSON (aggiungi solo i campi pertinenti, omettendo quelli non trovati, e tieni validi quelli vuoti di default):
{"interests": [], "preferences": [], "traits": [], "pets": [], "children": [], "spouse": null}
"""


async def extract_identity_updates(message: str, history_text: str = "") -> IdentityUpdate:
    """
    Extract stable identity updates from a user message and history context using LLM.
    Returns empty IdentityUpdate if extraction fails or nothing stable found.
    Never interrupts chat flow.
    Uses llm_service (OpenRouter) — no direct OpenAI calls.
    """
    try:
        from core.llm_service import llm_service
        user_content = (
            f"Contesto recente: {history_text}\nMessaggio utente: {message}"
            if history_text else message
        )
        raw = await llm_service._call_with_protection(
            "gpt-4o-mini", EXTRACTION_PROMPT, user_content,
            user_id=None, route="identity_extractor"
        )
        if not raw:
            return IdentityUpdate()

        logger.info("IDENTITY_EXTRACTOR_RAW response=%s", raw)

        parsed = json.loads(raw)
        update = IdentityUpdate(**parsed)

        # Normalize all values to lowercase
        update.interests = [i.lower().strip() for i in update.interests if i.strip()]
        update.preferences = [p.lower().strip() for p in update.preferences if p.strip()]
        update.traits = [t.lower().strip() for t in update.traits if t.strip()]

        if update.interests or update.preferences or update.traits or update.pets or update.children or update.spouse:
            logger.info("IDENTITY_EXTRACTOR_RESULT has_data=true")
        else:
            logger.debug("IDENTITY_EXTRACTOR_RESULT empty=true")

        return update

    except json.JSONDecodeError as e:
        logger.warning("IDENTITY_EXTRACTOR_JSON_ERROR error=%s", e)
        return IdentityUpdate()
    except Exception as e:
        logger.warning("IDENTITY_EXTRACTOR_ERROR error=%s", e)
        return IdentityUpdate()


def merge_identity_update(profile, update: IdentityUpdate):
    """
    Merge identity update into profile with deduplication and lowercase normalization.
    Modifies profile in place. Does not overwrite existing data.
    """
    for field_name in ["interests", "preferences", "traits"]:
        existing = getattr(profile, field_name)
        new_values = getattr(update, field_name)

        existing_lower = {v.lower().strip() for v in existing}

        for val in new_values:
            normalized = val.lower().strip()
            if normalized and normalized not in existing_lower:
                existing.append(normalized)
                existing_lower.add(normalized)

    if update.spouse:
        profile.spouse = update.spouse

    if update.pets:
        from core.models.profile_model import Pet
        existing_pets_names = [p.name.lower() for p in profile.pets]
        for p in update.pets:
            if "name" in p and p["name"].lower() not in existing_pets_names:
                profile.pets.append(Pet(type=p.get("type", "unknown"), name=p["name"]))

    if update.children:
        from core.models.profile_model import Child
        existing_children_names = [c.name.lower() for c in profile.children]
        for c in update.children:
            if "name" in c and c["name"].lower() not in existing_children_names:
                profile.children.append(Child(name=c["name"]))

    return profile
