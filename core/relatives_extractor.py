"""
RELATIVES EXTRACTOR - Genesi Core

Estrazione SEMANTICA (LLM, nessuna lista hardcoded) di relazioni dell'utente:
parenti (sorella, fratello, zio, zia, cugino, nonno, suocero, cognato, nipote...)
e relazioni sociali (amico, collega, fidanzato, vicino...), ciascuna con il nome
proprio della persona.

Globale: usato sia in chat libera (background task in message_pipeline) sia nel
flusso foto (try_extract_faces_from_text), così "quella è mia sorella Elena"
salva sia il volto (Elena) sia la relazione (Elena = sorella).

Storage: profile["relatives"] = [{"name", "relation", "gender"}].
Usa _call_model (preserva il proprio prompt — regola d'oro, NON _call_with_protection).
Fail-silent: non interrompe mai il flusso chat.
"""

import json
import logging

from core.log import log

logger = logging.getLogger(__name__)


_EXTRACT_PROMPT = (
    "Sei un estrattore di RELAZIONI dell'utente che scrive.\n"
    "Dal messaggio (ed eventuale contesto), estrai le persone che l'utente collega a sé "
    "tramite una relazione, con il loro NOME PROPRIO e il TIPO di relazione.\n\n"
    "COSA ESTRARRE:\n"
    "- Parenti: sorella, fratello, madre, padre, figlio, figlia, moglie, marito, zio, zia, "
    "cugino, cugina, nonno, nonna, suocero, suocera, genero, nuora, cognato, cognata, nipote, ecc.\n"
    "- Relazioni sociali: amico, amica, collega, fidanzato, fidanzata, compagno, compagna, vicino, ecc.\n"
    "La 'relation' è testo LIBERO in minuscolo, forma base singolare (es. 'sorella', non 'sorelle'). "
    "NON sei limitato a un elenco fisso: usa la parola che l'utente ha usato.\n\n"
    "REGOLE FERREE:\n"
    "1. 'name' = SOLO il nome proprio di battesimo (es. 'Elena'). MAI un descrittore "
    "('mia sorella', 'lo zio') come nome.\n"
    "2. Estrai una voce SOLO se c'è SIA la relazione SIA il nome proprio. "
    "Se l'utente dice 'mia sorella' senza nome → NON estrarre. "
    "Se dice un nome senza relazione ('c'è Marco') → NON estrarre.\n"
    "3. NON estrarre l'utente stesso ('io', 'sono io').\n"
    "4. NON inventare relazioni non dette. NON dedurre parentele non esplicite.\n"
    "5. Ignora le domande ('chi è mia sorella?') e le negazioni ('non è mia sorella').\n"
    "6. 'gender': 'M', 'F' o null, dedotto dalla relazione o dal nome.\n"
    "7. Più persone nello stesso messaggio → più voci.\n\n"
    "ESEMPI:\n"
    "- 'quella è mia sorella Elena' -> [{\"name\":\"Elena\",\"relation\":\"sorella\",\"gender\":\"F\"}]\n"
    "- 'mio cugino Marco e mia zia Pina' -> [{\"name\":\"Marco\",\"relation\":\"cugino\",\"gender\":\"M\"},"
    "{\"name\":\"Pina\",\"relation\":\"zia\",\"gender\":\"F\"}]\n"
    "- 'lui è Gianvito, il marito di mia sorella' -> [{\"name\":\"Gianvito\",\"relation\":\"cognato\",\"gender\":\"M\"}]\n"
    "- 'il mio amico Luca' -> [{\"name\":\"Luca\",\"relation\":\"amico\",\"gender\":\"M\"}]\n"
    "- 'mia moglie' -> []  (manca il nome)\n"
    "- 'c'è anche Marco' -> []  (manca la relazione)\n"
    "- 'chi è mio fratello?' -> []  (domanda)\n\n"
    "Rispondi SOLO con un array JSON (vuoto [] se nulla). Nessun testo fuori dal JSON."
)


async def extract_relatives(message: str, history_text: str = "", speaker_name: str | None = None) -> list[dict]:
    """Estrae [{name, relation, gender}] dal messaggio. Fail-silent → [] su errore."""
    if not message or not message.strip():
        return []
    try:
        from core.llm_service import llm_service

        ctx = ""
        if speaker_name and str(speaker_name).strip():
            ctx += f"Chi scrive si chiama: {str(speaker_name).strip()} (NON estrarlo come parente).\n"
        if history_text:
            ctx += f"Contesto recente: {history_text}\n"
        user_content = f"{ctx}Messaggio: {message}"

        raw = await llm_service._call_model(
            "openai/gpt-4o-mini", _EXTRACT_PROMPT, user_content,
            user_id=None, route="memory",
        )
        if not raw:
            return []
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = json.loads(clean.strip())
        if not isinstance(parsed, list):
            return []

        out = []
        for r in parsed:
            if not isinstance(r, dict):
                continue
            name = (r.get("name") or "").strip()
            relation = (r.get("relation") or "").strip().lower()
            gender = r.get("gender")
            if not name or not relation:
                continue
            out.append({"name": name, "relation": relation,
                        "gender": gender if gender in ("M", "F") else None})
        return out
    except json.JSONDecodeError as e:
        logger.debug("RELATIVES_EXTRACT_JSON_ERR %s", e)
        return []
    except Exception as e:
        logger.debug("RELATIVES_EXTRACT_ERR %s", e)
        return []


def merge_relatives(profile: dict, relatives: list[dict]) -> bool:
    """Aggiorna profile['relatives'] (dict in-place). Dedup per nome (case-insensitive):
    aggiorna la relazione se il nome esiste già. Scarta nomi non validi/descrittori.
    Ritorna True se il profilo è cambiato."""
    if not relatives:
        return False
    from core.name_utils import sanitize_profile_name

    existing = profile.get("relatives")
    if not isinstance(existing, list):
        existing = []
    by_name = {}
    for r in existing:
        if isinstance(r, dict) and r.get("name"):
            by_name[r["name"].strip().lower()] = r

    changed = False
    for r in relatives:
        clean = sanitize_profile_name(r.get("name", ""))
        if not clean:
            continue
        key = clean.strip().lower()
        relation = (r.get("relation") or "").strip().lower()
        if not relation:
            continue
        gender = r.get("gender") if r.get("gender") in ("M", "F") else None
        if key in by_name:
            cur = by_name[key]
            if cur.get("relation") != relation or (gender and cur.get("gender") != gender):
                cur["relation"] = relation
                if gender:
                    cur["gender"] = gender
                changed = True
                log("RELATIVE_UPDATED", name=clean, relation=relation)
        else:
            entry = {"name": clean, "relation": relation, "gender": gender}
            by_name[key] = entry
            existing.append(entry)
            changed = True
            log("RELATIVE_SAVED", name=clean, relation=relation)

    if changed:
        profile["relatives"] = existing
    return changed
