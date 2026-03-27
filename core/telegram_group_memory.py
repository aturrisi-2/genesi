"""
Memoria contestuale per i membri del gruppo Telegram.

Ogni membro del gruppo ha:
- Profilo con fatti personali (città, professione, hobby, ecc.)
- Contatore messaggi e ultimo accesso

Il gruppo ha:
- Storia recente delle conversazioni (ultimi N turni, con attribuzione per nome)

Tutto questo viene iniettato come contesto nel prompt quando Genesi risponde nel gruppo,
permettendole di ricordare chi è ogni membro e cosa è stato detto in precedenza.
"""

import asyncio
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

MAX_HISTORY  = 20   # turni conservati per gruppo
MAX_FACTS    = 40   # fatti per membro
HISTORY_INJECT = 8  # turni iniettati nel prompt

_EXTRACTION_PROMPT = """\
Analizza questo scambio e estrai fatti personali rilevanti sulla persona che ha scritto.
Restituisci SOLO un JSON object con coppie chiave-valore (max 6 fatti nuovi).

Chiavi utili: city, profession, age, hobby, sport_team, family_role, preference, pet, health_note.
Usa snake_case per le chiavi. Valori brevi (max 5 parole).
Se non ci sono fatti chiari e nuovi, restituisci {}.

Esempio output: {"city": "Milano", "profession": "architetto", "hobby": "fotografia"}
"""


# ── Storage helpers ────────────────────────────────────────────────────────────

def _member_key(from_id: int) -> str:
    return f"telegram:group_member:{from_id}"

def _history_key(chat_id: int) -> str:
    return f"telegram:group_history:{chat_id}"


async def _storage():
    from core.storage import storage
    return storage


# ── Member profile ─────────────────────────────────────────────────────────────

async def get_member(from_id: int) -> dict:
    s = await _storage()
    return await s.load(_member_key(from_id), default={}) or {}


async def update_member_seen(from_id: int, first_name: str):
    """Aggiorna last_seen e message_count. Crea il profilo se non esiste."""
    s = await _storage()
    member = await get_member(from_id)
    member["from_id"]       = from_id
    member["first_name"]    = first_name
    member["last_seen"]     = int(time.time())
    member["message_count"] = member.get("message_count", 0) + 1
    if "joined_at" not in member:
        member["joined_at"] = int(time.time())
    await s.save(_member_key(from_id), member)


async def save_member_city(from_id: int, city: str):
    s = await _storage()
    member = await get_member(from_id)
    member["city"] = city
    facts = member.get("facts", {})
    facts["city"] = city
    member["facts"] = facts
    await s.save(_member_key(from_id), member)


async def get_member_city(from_id: int) -> str:
    member = await get_member(from_id)
    return member.get("city") or member.get("facts", {}).get("city", "") or ""


# ── Group history ──────────────────────────────────────────────────────────────

async def get_group_history(chat_id: int, limit: int = HISTORY_INJECT) -> list:
    s = await _storage()
    history = await s.load(_history_key(chat_id), default=[]) or []
    return history[-limit:]


async def append_group_history(chat_id: int, from_id: int, first_name: str,
                                text: str, response: str):
    s = await _storage()
    history = await s.load(_history_key(chat_id), default=[]) or []
    history.append({
        "from_id":    from_id,
        "first_name": first_name,
        "text":       text[:200],
        "response":   response[:300],
        "ts":         int(time.time()),
    })
    history = history[-MAX_HISTORY:]
    await s.save(_history_key(chat_id), history)


# ── Context builder ────────────────────────────────────────────────────────────

async def build_group_context(chat_id: int, from_id: int, first_name: str,
                               owner_name: str = "Alfio") -> str:
    """
    Costruisce il blocco di contesto da iniettare nel prompt per le risposte di gruppo.
    Include: fatti noti sul membro, storia recente del gruppo, nota famiglia.
    """
    member  = await get_member(from_id)
    history = await get_group_history(chat_id, limit=HISTORY_INJECT)

    lines = []

    # ── Fatti noti sul membro che sta scrivendo ─────────────────────────────
    facts = member.get("facts", {})
    city  = member.get("city") or facts.get("city", "")
    fact_parts = []
    if city:
        fact_parts.append(f"città: {city}")
    for k, v in facts.items():
        if k != "city":
            fact_parts.append(f"{k.replace('_', ' ')}: {v}")

    if fact_parts:
        lines.append(f"[COSA SO DI {first_name.upper()}: {'; '.join(fact_parts)}]")
    else:
        lines.append(f"[{first_name.upper()}: nessun fatto ancora registrato — è la prima volta che interagisce o non ho ancora dati]")

    # ── Storia recente del gruppo ───────────────────────────────────────────
    if history:
        lines.append("[STORIA RECENTE DEL GRUPPO (ultimi scambi):]")
        for h in history:
            name = h.get("first_name", "?")
            msg  = h.get("text", "")[:120]
            resp = h.get("response", "")[:120]
            lines.append(f"  {name}: {msg}")
            lines.append(f"  → Genesi: {resp}")
        lines.append("[FINE STORIA]")

    # ── Nota famiglia ───────────────────────────────────────────────────────
    lines.append(
        f"[CONTESTO FAMIGLIA: questo è il gruppo famiglia di {owner_name}. "
        f"{first_name} è un membro della famiglia. "
        f"Trattalo/a con calore, familiarità e affetto — come faresti con una persona cara. "
        f"Puoi fare riferimento a cose dette in precedenza nel gruppo da {first_name} o dagli altri. "
        f"Se {first_name} chiede qualcosa che riguarda un altro membro, puoi menzionare "
        f"cosa sai di quella persona dal contesto del gruppo.]"
    )

    return "\n".join(lines)


# ── Background fact extraction ─────────────────────────────────────────────────

async def extract_member_facts_background(from_id: int, first_name: str,
                                           text: str, response: str):
    """
    Estrae fatti personali dal turno di conversazione e li salva nel profilo del membro.
    Chiamare con asyncio.create_task() per non bloccare la risposta.
    """
    try:
        from core.llm_service import llm_service

        user_msg = (
            f"Messaggio di {first_name}: {text}\n"
            f"Risposta Genesi: {response}"
        )
        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            _EXTRACTION_PROMPT,
            user_msg,
            user_id=f"group_member_{from_id}",
            route="memory",
        )
        if not raw:
            return

        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
            clean = clean.strip()

        new_facts = json.loads(clean)
        if not isinstance(new_facts, dict) or not new_facts:
            return

        s = await _storage()
        member = await get_member(from_id)
        facts  = member.get("facts", {})
        facts.update(new_facts)
        # Aggiorna anche city di primo livello se estratta
        if "city" in new_facts:
            member["city"] = new_facts["city"]
        # Cap
        if len(facts) > MAX_FACTS:
            facts = dict(list(facts.items())[-MAX_FACTS:])
        member["facts"] = facts
        await s.save(_member_key(from_id), member)
        logger.info("GROUP_MEMBER_FACTS from_id=%s name=%s keys=%s",
                    from_id, first_name, list(new_facts.keys()))

    except Exception as exc:
        logger.debug("GROUP_MEMBER_FACTS_ERROR from_id=%s err=%s", from_id, exc)
