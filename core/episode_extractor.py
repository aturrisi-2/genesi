"""
EPISODE EXTRACTOR — Genesi Episodic Memory System

Estrae eventi personali significativi dai messaggi in background.
Usa gpt-4o-mini con _call_model (NON _call_with_protection) per preservare
il prompt di estrazione.

Fail-silent: qualsiasi errore non interrompe il flusso chat.
"""

import json
import logging
import uuid
from datetime import datetime, date
from typing import List, Dict

logger = logging.getLogger("genesi")

_EXTRACTION_PROMPT_TEMPLATE = """\
Sei un assistente che estrae eventi personali significativi dai messaggi.
Data di oggi: {today}

ESTRAI SOLO:
- Appuntamenti concreti: "devo andare...", "domani ho...", "stasera vado..."
- Situazioni familiari importanti: "mia figlia arriva...", "mio figlio ha..."
- Esperienze significative personali: "ho avuto un colloquio", "ho incontrato..."
- Impegni pianificati: "la settimana prossima...", "fra due giorni..."

NON ESTRARRE:
- Domande su meteo, notizie, orari, calcoli
- Comandi tecnici o richieste di informazioni generiche
- Informazioni già nel profilo (nome, coniuge, figli, animali)
- Preferenze generali o gusti

Per ogni evento estratto:
- "text": descrizione in terza persona ("L'utente deve andare all'aeroporto...")
- "event_date": data ISO YYYY-MM-DD se desumibile dal contesto, altrimenti null
- "is_future": true se evento pianificato/futuro, false se già accaduto
- "tags": max 4 parole chiave rilevanti (es. ["aeroporto", "figlia", "viaggio"])

Rispondi SOLO con JSON valido:
{{"episodes": [{{"text":"...","event_date":"...","is_future":true,"tags":["..."]}}]}}
Se nessun evento significativo: {{"episodes": []}}
"""


async def extract_episodes(message: str, user_id: str) -> List[Dict]:
    """
    Estrae eventi personali dal messaggio usando gpt-4o-mini.
    Restituisce lista di dict pronti per EpisodeMemory.add().
    Mai interrompe il flusso — fail-silent.
    """
    try:
        from core.llm_service import llm_service, model_selector

        today_str = date.today().isoformat()
        prompt = _EXTRACTION_PROMPT_TEMPLATE.format(today=today_str)

        # Usa _call_model (non _call_with_protection) per preservare il prompt
        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            prompt,
            message,
            user_id=user_id,
            route="memory"
        )
        if not raw:
            return []

        # Pulizia: rimuovi wrapper ```json``` se presenti
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip()

        parsed = json.loads(clean)
        raw_episodes = parsed.get("episodes", [])
        if not isinstance(raw_episodes, list):
            return []

        result = []
        for ep in raw_episodes:
            if not isinstance(ep, dict) or not ep.get("text"):
                continue
            text = str(ep["text"]).strip()
            if not text:
                continue
            episode = {
                "id": str(uuid.uuid4())[:8],
                "text": text,
                "event_date": ep.get("event_date") or None,
                "is_future": bool(ep.get("is_future", True)),
                "tags": [str(t).lower() for t in ep.get("tags", []) if t][:4],
                "saved_at": datetime.utcnow().isoformat(),
                "last_used_at": None,
                "use_count": 0,
            }
            result.append(episode)

        return result

    except json.JSONDecodeError as e:
        logger.debug("EPISODE_EXTRACTOR_JSON_ERROR err=%s", e)
        return []
    except Exception as e:
        logger.debug("EPISODE_EXTRACTOR_ERROR err=%s", e)
        return []
