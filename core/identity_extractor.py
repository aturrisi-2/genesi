"""
IDENTITY EXTRACTOR - Genesi Core
Extracts stable identity traits from user messages using LLM classification.
Only saves declarative, stable, non-situational identity data.
"""

import json
import logging
from typing import List
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
import os

logger = logging.getLogger(__name__)


class IdentityUpdate(BaseModel):
    interests: List[str] = Field(default_factory=list)
    preferences: List[str] = Field(default_factory=list)
    traits: List[str] = Field(default_factory=list)


EXTRACTION_PROMPT = """Sei un classificatore di identita' personale.
Analizza il messaggio dell'utente e estrai SOLO informazioni identitarie STABILI.

REGOLE:
- Salva SOLO dichiarazioni stabili su se stessi (gusti, preferenze durature, tratti caratteriali)
- NON salvare stati temporanei (stanchezza, umore del momento, piani futuri)
- NON salvare informazioni situazionali (dove va oggi, cosa fa adesso)
- Normalizza tutto in lowercase
- Rispondi SOLO con JSON valido, nessun altro testo

ESEMPI DI COSA SALVARE:
- "Adoro la musica elettronica" -> interests: ["musica elettronica"]
- "Mi piace la fotografia" -> interests: ["fotografia"]
- "Sono una persona introversa" -> traits: ["introverso"]
- "Preferisco lavorare di notte" -> preferences: ["lavorare di notte"]

ESEMPI DI COSA NON SALVARE:
- "Oggi sono stanco" -> {} (stato temporaneo)
- "Mi fa male la testa" -> {} (stato temporaneo)
- "Domani vado al mare" -> {} (piano futuro)
- "Sono nervoso ora" -> {} (stato temporaneo)
- "Ciao come stai" -> {} (saluto)

Rispondi con questo formato JSON esatto:
{"interests": [], "preferences": [], "traits": []}

Se non c'e' nulla di stabile da estrarre, rispondi con:
{"interests": [], "preferences": [], "traits": []}

Messaggio utente: """


async def extract_identity_updates(message: str) -> IdentityUpdate:
    """
    Extract stable identity updates from a user message using LLM classification.
    Returns empty IdentityUpdate if extraction fails or nothing stable found.
    Never interrupts chat flow.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("sk-test"):
        logger.debug("IDENTITY_EXTRACTOR_SKIP reason=no_api_key")
        return IdentityUpdate()

    try:
        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": message}
            ],
            temperature=0.0,
            max_tokens=200
        )

        raw = response.choices[0].message.content.strip()
        logger.info("IDENTITY_EXTRACTOR_RAW response=%s", raw)

        parsed = json.loads(raw)
        update = IdentityUpdate(**parsed)

        # Normalize all values to lowercase
        update.interests = [i.lower().strip() for i in update.interests if i.strip()]
        update.preferences = [p.lower().strip() for p in update.preferences if p.strip()]
        update.traits = [t.lower().strip() for t in update.traits if t.strip()]

        if update.interests or update.preferences or update.traits:
            logger.info(
                "IDENTITY_EXTRACTOR_RESULT interests=%s preferences=%s traits=%s",
                update.interests, update.preferences, update.traits
            )
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

        # Normalize existing to lowercase for comparison
        existing_lower = {v.lower().strip() for v in existing}

        for val in new_values:
            normalized = val.lower().strip()
            if normalized and normalized not in existing_lower:
                existing.append(normalized)
                existing_lower.add(normalized)

    return profile
