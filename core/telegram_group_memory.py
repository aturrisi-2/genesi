"""
Memoria contestuale per i membri del gruppo Telegram.

Ogni membro del gruppo ha:
- Account Genesi virtuale proprio (telegram_{from_id}@genesi.group)
- Profilo con fatti personali (città, professione, hobby, ecc.)
- Contatore messaggi e ultimo accesso

Il gruppo ha:
- Storia recente delle conversazioni (ultimi N turni, con attribuzione per nome)
- Insights consolidati ogni 24h (pattern della famiglia)

Feed nel sistema di automiglioramento:
- lab_feedback_cycle: osservazioni sulle interazioni di gruppo ogni 5 messaggi
- context_assembler: il proprietario del gruppo vede i profili dei membri nella chat privata
- group_insights: consolidazione LLM 24h → iniettata nel contesto di ogni membro
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_RELATIONSHIP_PROMPT = """\
Sei un estrattore di relazioni familiari. Leggi questo messaggio inviato in un gruppo Telegram familiare.
Il proprietario del gruppo si chiama Alfio (è il creatore di Genesi, l'AI del gruppo).

Determina SE il mittente sta dichiarando una relazione con Alfio o con la sua famiglia, anche implicitamente.
Esempi: "sono la sorella", "sono la figlia di Alfio", "sono sua madre", "sono il fratello",
"mi chiamo Rita, la moglie", "sono la cugina", "io sono Ennio il figlio" ecc.
Anche relazioni indirette: "sono il marito di tua sorella" → cognato di Alfio.

Se c'è una relazione, ritorna:
{
  "found": true,
  "relationship": "sorella",           // ruolo in italiano, singolare (sorella/fratello/figlia/figlio/moglie/madre/padre/cugina/nipote/cognata ecc.)
  "name": "Maria",                     // nome della persona se menzionato, altrimenti null
  "notes": "frase breve opzionale"     // max 10 parole di contesto
}

Se NON c'è nessuna dichiarazione di relazione: {"found": false}
Rispondi SOLO con JSON valido.
"""

MAX_HISTORY    = 20   # turni conservati per gruppo
MAX_FACTS      = 40   # fatti per membro
HISTORY_INJECT = 8    # turni iniettati nel prompt
MAX_RAW_MSGS   = 30   # messaggi grezzi conservati per gruppo (tutti, anche senza risposta)
RAW_INJECT     = 15   # ultimi N messaggi grezzi iniettati nel contesto
CONSOLIDATION_INTERVAL = 86400  # 24h in secondi
OBSERVATION_EVERY_N    = 5      # ogni N messaggi di gruppo → 1 osservazione lab

_GROUP_INSIGHT_PROMPT = """\
Sei un analista della dinamica di gruppo. Leggi questi scambi recenti di una chat di famiglia
con un'AI assistente (Genesi) e produci insight utili su:
- Come i membri comunicano e cosa apprezzano
- Pattern ricorrenti nelle domande o nei bisogni
- Come Genesi potrebbe migliorare le risposte in questo contesto familiare

Restituisci SOLO un JSON: {"insights": ["insight 1", "insight 2", ...]} (max 6 insights, max 15 parole ciascuno).
Se i dati sono insufficienti, restituisci {"insights": []}.
"""

_OBSERVATION_PROMPT = """\
Leggi questo scambio in una chat di famiglia con Genesi e valuta la qualità dell'interazione.
Produci UNA singola osservazione utile per migliorare il comportamento di Genesi nei gruppi familiari.
Massimo 2 righe. Sii concreto e specifico (es. "Ha risposto formalmente quando serviva calore",
"Ha ignorato il contesto emotivo", "Ha usato il nome corretto", ecc.)
Restituisci solo il testo dell'osservazione, senza prefissi.
"""


# ── Storage helpers ────────────────────────────────────────────────────────────

def _member_key(from_id: int) -> str:
    return f"telegram:group_member:{from_id}"

def _history_key(chat_id: int) -> str:
    return f"telegram:group_history:{chat_id}"

def _insights_key(chat_id: int) -> str:
    return f"telegram:group_insights:{chat_id}"

def _raw_key(chat_id: int) -> str:
    return f"telegram:group_raw:{chat_id}"

def _family_key(owner_user_id: str) -> str:
    return f"telegram:family_members:{owner_user_id}"


async def _storage():
    from core.storage import storage
    return storage


# ── Member profile ─────────────────────────────────────────────────────────────

async def get_member(from_id: int) -> dict:
    s = await _storage()
    return await s.load(_member_key(from_id), default={}) or {}


async def update_member_seen(from_id: int, first_name: str):
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


# ── Raw message buffer (tutti i messaggi, non solo quelli a cui Genesi risponde) ─

async def append_raw_message(chat_id: int, from_id: int, first_name: str, text: str):
    """Salva ogni messaggio del gruppo, anche quelli ignorati da Genesi."""
    s = await _storage()
    msgs = await s.load(_raw_key(chat_id), default=[]) or []
    msgs.append({
        "from_id":    from_id,
        "first_name": first_name,
        "text":       text[:200],
        "ts":         int(time.time()),
    })
    msgs = msgs[-MAX_RAW_MSGS:]
    await s.save(_raw_key(chat_id), msgs)


async def get_raw_messages(chat_id: int, limit: int = RAW_INJECT) -> list:
    s = await _storage()
    msgs = await s.load(_raw_key(chat_id), default=[]) or []
    return msgs[-limit:]


# ── Context builder ────────────────────────────────────────────────────────────

async def build_group_context(chat_id: int, from_id: int, first_name: str,
                               owner_name: str = "Alfio") -> str:
    member   = await get_member(from_id)
    history  = await get_group_history(chat_id, limit=HISTORY_INJECT)
    insights = await _get_group_insights(chat_id)
    raw_msgs = await get_raw_messages(chat_id, limit=RAW_INJECT)

    lines = []

    # Fatti noti sul membro che sta scrivendo
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
        lines.append(f"[{first_name.upper()}: nessun dato ancora — prima interazione]")

    # Insights consolidati del gruppo
    if insights:
        lines.append(f"[DINAMICHE DELLA FAMIGLIA (apprese nel tempo):]")
        for ins in insights:
            lines.append(f"  • {ins}")

    # Discussione in corso (tutti i messaggi recenti, anche quelli a cui Genesi non ha risposto)
    if raw_msgs:
        lines.append("[DISCUSSIONE IN CORSO — messaggi recenti del gruppo:]")
        for m in raw_msgs:
            name = m.get("first_name", "?")
            msg  = m.get("text", "")[:150]
            lines.append(f"  {name}: {msg}")
        lines.append("[FINE DISCUSSIONE]")
    elif history:
        # Fallback: storia vecchia se non ci sono messaggi raw
        lines.append("[STORIA RECENTE DEL GRUPPO:]")
        for h in history:
            name = h.get("first_name", "?")
            msg  = h.get("text", "")[:120]
            resp = h.get("response", "")[:120]
            lines.append(f"  {name}: {msg}")
            lines.append(f"  → Genesi: {resp}")
        lines.append("[FINE STORIA]")

    # Nota famiglia
    lines.append(
        f"[CONTESTO FAMIGLIA: {first_name} è un membro della famiglia di {owner_name}. "
        f"Trattalo/a con calore, familiarità e affetto. "
        f"Ricorda le conversazioni precedenti. "
        f"Puoi fare riferimento a quello che altri membri hanno detto.]"
    )

    return "\n".join(lines)


# ── Automiglioramento livello 1: lab_feedback_cycle ────────────────────────────

async def record_group_observation(chat_id: int, from_id: int, first_name: str,
                                    text: str, response: str):
    """
    Ogni OBSERVATION_EVERY_N messaggi di gruppo, analizza l'interazione e
    registra un'osservazione nel lab_feedback_cycle per il miglioramento del prompt.
    """
    try:
        member = await get_member(from_id)
        count  = member.get("message_count", 0)
        if count % OBSERVATION_EVERY_N != 0:
            return

        from core.llm_service import llm_service
        from core.lab_feedback_cycle import lab_feedback_cycle

        user_msg = (
            f"Membro del gruppo: {first_name}\n"
            f"Messaggio: {text}\n"
            f"Risposta Genesi: {response}"
        )
        observation = await llm_service._call_model(
            "openai/gpt-4o-mini",
            _OBSERVATION_PROMPT,
            user_msg,
            user_id="group-observation",
            route="memory",
        )
        if observation and observation.strip():
            lab_feedback_cycle.record_observation(
                category="GRUPPO_FAMIGLIA",
                observation=observation.strip()[:300],
                source=f"gruppo:{chat_id}:{first_name}",
            )
            logger.info("GROUP_OBSERVATION_RECORDED chat_id=%s member=%s", chat_id, first_name)
    except Exception as exc:
        logger.debug("GROUP_OBSERVATION_ERROR err=%s", exc)


# ── Automiglioramento livello 2: consolidazione insights di gruppo ─────────────

async def _get_group_insights(chat_id: int) -> list:
    s = await _storage()
    data = await s.load(_insights_key(chat_id), default={}) or {}
    return data.get("insights", [])


async def consolidate_group_insights_if_needed(chat_id: int):
    """
    Ogni 24h consolida la storia del gruppo in insights stabili via LLM.
    Risultato: arricchisce il contesto di tutti i membri e
    alimenta la cross-awareness del proprietario.
    """
    try:
        s    = await _storage()
        data = await s.load(_insights_key(chat_id), default={}) or {}
        last = data.get("last_consolidated_at", 0)
        if time.time() - last < CONSOLIDATION_INTERVAL:
            return

        history = await get_group_history(chat_id, limit=MAX_HISTORY)
        if len(history) < 4:
            return  # troppo poco per consolidare

        from core.llm_service import llm_service

        history_text = "\n".join(
            f"{h.get('first_name','?')}: {h.get('text','')[:100]}\n"
            f"→ Genesi: {h.get('response','')[:100]}"
            for h in history
        )
        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            _GROUP_INSIGHT_PROMPT,
            history_text,
            user_id="group-consolidation",
            route="memory",
        )
        if not raw:
            return

        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = json.loads(clean.strip())
        insights = parsed.get("insights", [])
        if not isinstance(insights, list):
            insights = []

        data["insights"]              = insights
        data["last_consolidated_at"]  = int(time.time())
        await s.save(_insights_key(chat_id), data)
        logger.info("GROUP_INSIGHTS_CONSOLIDATED chat_id=%s count=%d", chat_id, len(insights))

    except Exception as exc:
        logger.debug("GROUP_INSIGHTS_ERROR chat_id=%s err=%s", chat_id, exc)


# ── Automiglioramento livello 3: cross-awareness per il proprietario ───────────

async def sync_family_to_owner(chat_id: int, owner_user_id: str):
    """
    Scrive un riassunto dei membri della famiglia nel profilo del proprietario.
    Questo blocco viene iniettato da context_assembler nella chat privata di Alfio,
    così Genesi sa chi sono i suoi familiari anche quando parla solo con lui.
    Eseguito ogni 24h.
    """
    try:
        s    = await _storage()
        data = await s.load(_family_key(owner_user_id), default={}) or {}
        last = data.get("last_synced_at", 0)
        if time.time() - last < CONSOLIDATION_INTERVAL:
            return

        history = await get_group_history(chat_id, limit=MAX_HISTORY)
        # Raccogli from_id unici dalla storia
        seen_ids: dict[int, str] = {}
        for h in history:
            fid  = h.get("from_id")
            name = h.get("first_name", "")
            if fid and name:
                seen_ids[fid] = name

        members_summary = []
        for fid, name in seen_ids.items():
            member = await get_member(fid)
            facts  = member.get("facts", {})
            city   = member.get("city") or facts.get("city", "")
            relationship = member.get("relationship_to_owner", "")
            parts  = []
            if relationship:
                parts.append(f"relazione: {relationship}")
            if city:
                parts.append(f"città: {city}")
            for k, v in facts.items():
                if k not in ("city", "relazione_con_alfio"):
                    parts.append(f"{k.replace('_',' ')}: {v}")
            desc = f"{name}" + (f" ({'; '.join(parts[:5])})" if parts else "")
            members_summary.append(desc)

        group_insights = await _get_group_insights(chat_id)

        data["members"]          = members_summary
        data["group_insights"]   = group_insights
        data["last_synced_at"]   = int(time.time())
        await s.save(_family_key(owner_user_id), data)
        logger.info("FAMILY_SYNCED_TO_OWNER user_id=%s members=%d", owner_user_id, len(members_summary))

    except Exception as exc:
        logger.debug("FAMILY_SYNC_ERROR err=%s", exc)


async def get_family_context_block(owner_user_id: str) -> str:
    """
    Ritorna il blocco di contesto famiglia da iniettare nella chat privata del proprietario.
    Chiamato da context_assembler (fail-silent).
    """
    try:
        s    = await _storage()
        data = await s.load(_family_key(owner_user_id), default={}) or {}
        members  = data.get("members", [])
        insights = data.get("group_insights", [])
        if not members:
            return ""
        lines = ["[FAMIGLIA (dal gruppo Telegram):"]
        for m in members:
            lines.append(f"  • {m}")
        if insights:
            lines.append("  Dinamiche osservate:")
            for ins in insights:
                lines.append(f"    - {ins}")
        lines.append("]")
        return "\n".join(lines)
    except Exception:
        return ""


# ── Estrazione relazioni familiari e albero genealogico ────────────────────────

_OWNER_USER_ID_FOR_TREE = "6028d92a-94f2-4e2f-bcb7-012c861e3ab2"  # Alfio

async def extract_family_relationship(
    member_id: str, first_name: str, text: str, platform: str = "telegram"
) -> None:
    """
    Analizza ogni messaggio del gruppo con LLM leggero (qualsiasi piattaforma).
    Se il mittente dichiara una relazione con Alfio (sorella, madre, figlio, ecc.):
      1. Salva la relazione nel profilo del membro (Telegram) o in storage generico
      2. Aggiorna l'albero genealogico di Alfio (family_tree nel suo profilo)
      3. Aggiunge un fatto personale in personal_facts di Alfio
    Fail-silent. Non blocca il flusso principale.
    """
    if not text or len(text.strip()) < 3:
        return
    try:
        from core.llm_service import llm_service

        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            _RELATIONSHIP_PROMPT,
            f"Mittente: {first_name}\nMessaggio: {text[:300]}",
            user_id="group-relation-extractor",
            route="memory",
        )
        if not raw:
            return

        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = json.loads(clean.strip())

        if not parsed.get("found"):
            return

        relationship = parsed.get("relationship", "").strip().lower()
        name         = parsed.get("name") or first_name
        notes        = parsed.get("notes", "")

        if not relationship:
            return

        s = await _storage()

        # 1. Salva nel profilo del membro (solo Telegram ha _member_key int-based)
        if platform == "telegram":
            try:
                from_id_int = int(member_id)
                member = await get_member(from_id_int)
                member["relationship_to_owner"] = relationship
                member["display_name"] = name
                facts = member.get("facts", {})
                facts["relazione_con_alfio"] = relationship
                member["facts"] = facts
                await s.save(_member_key(from_id_int), member)
            except Exception:
                pass
        else:
            # Profilo generico per altre piattaforme
            generic_key = f"group_member:{platform}:{member_id}"
            member = await s.load(generic_key, default={}) or {}
            member["relationship_to_owner"] = relationship
            member["display_name"] = name
            member["platform"] = platform
            member["first_name"] = first_name
            await s.save(generic_key, member)

        # 2. Aggiorna albero genealogico nel profilo di Alfio
        profile_key = f"profile:{_OWNER_USER_ID_FOR_TREE}"
        profile = await s.load(profile_key, default={}) or {}
        family_tree = profile.get("family_tree", {})
        tree_key = f"{platform}_{member_id}"
        family_tree[tree_key] = {
            "name":         name,
            "relationship": relationship,
            "member_id":    member_id,
            "display_name": first_name,
            "notes":        notes,
            "platform":     platform,
            "source":       f"{platform}_group",
        }
        profile["family_tree"] = family_tree
        await s.save(profile_key, profile)

        # 3. Aggiunge fatto personale in personal_facts di Alfio
        # Formato canonico: {"facts": [...], "updated_at": "..."} — compatibile con personal_facts_service
        pf_key = f"personal_facts:{_OWNER_USER_ID_FOR_TREE}"
        pf_data = await s.load(pf_key, default={"facts": []}) or {"facts": []}
        if isinstance(pf_data, list):
            pf_data = {"facts": pf_data}  # migra vecchio formato lista
        pf_list = pf_data.get("facts", [])
        if not isinstance(pf_list, list):
            pf_list = []
        fact_key = f"famiglia_{relationship}_{platform}_{member_id}"
        pf_list = [f for f in pf_list if isinstance(f, dict) and f.get("key") != fact_key]
        pf_list.append({
            "key":    fact_key,
            "value":  f"{name} ({relationship})" + (f" — {notes}" if notes else ""),
            "source": f"{platform}_group",
        })
        pf_list = pf_list[-100:]
        pf_data["facts"] = pf_list
        pf_data["updated_at"] = datetime.utcnow().isoformat()
        await s.save(pf_key, pf_data)

        logger.info(
            "FAMILY_RELATIONSHIP_EXTRACTED platform=%s member_id=%s name=%s relationship=%s",
            platform, member_id, name, relationship
        )

    except Exception as exc:
        logger.debug("FAMILY_RELATIONSHIP_ERROR platform=%s member_id=%s err=%s",
                     platform, member_id, exc)
