import re
import hashlib

def stable_hash(s: str) -> int:
    """Ritorna un intero a 9 cifre stabile da una stringa per prevenire la randomizzazione di hash()."""
    if not s:
        return 0
    return int(hashlib.md5(s.encode('utf-8')).hexdigest(), 16) % (10**9)

# ── Event change detection (memoria eventi dichiarati) ─────────────────────---

# Pattern semplici per cambiamenti/eventi personali (estendibili)
_EVENT_PATTERNS = [
    (re.compile(r"\bsono tornat[oa]\b", re.IGNORECASE), "rientro"),
    (re.compile(r"\b(sto meglio|sto peggio|ora sto bene|ora sto male)\b", re.IGNORECASE), "salute"),
    (re.compile(r"\b(ho cambiato lavoro|nuovo lavoro|ora lavoro da casa|ora lavoro in ufficio)\b", re.IGNORECASE), "lavoro"),
    (re.compile(r"\b(ho traslocato|mi sono trasferit[oa])\b", re.IGNORECASE), "trasloco"),
    (re.compile(r"\b(sono in ferie|sono in vacanza|sono tornat[oa] dalle ferie|sono tornat[oa] dalle vacanze)\b", re.IGNORECASE), "ferie"),
    (re.compile(r"\b(ho finito gli esami|ho superato l'esame|ho preso la patente)\b", re.IGNORECASE), "traguardo"),
]

async def detect_and_save_event_change(chat_id: int, from_id: int, first_name: str, text: str) -> dict:
    """
    Rileva cambiamenti/eventi personali dichiarati e li salva nel profilo membro.
    Restituisce info su cambiamento rilevato, altrimenti {}.
    """
    found = None
    for pattern, event_type in _EVENT_PATTERNS:
        m = pattern.search(text)
        if m:
            found = {
                "event_type": event_type,
                "matched_text": m.group(0),
                "full_text": text,
                "from_id": from_id,
                "first_name": first_name,
                "ts": int(time.time()),
            }
            break
    if found:
        member = await get_member(from_id)
        events = member.get("events", [])
        # Evita duplicati ravvicinati
        if not events or events[-1].get("event_type") != found["event_type"] or events[-1].get("matched_text") != found["matched_text"]:
            events.append(found)
            events = events[-10:]  # conserva solo ultimi 10 eventi
            member["events"] = events
            s = await _storage()
            await s.save(_member_key(from_id), member)
        return found
    return {}
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
from core.log import log

logger = logging.getLogger(__name__)

_RELATIONSHIP_PROMPT = """\
Sei un estrattore di relazioni familiari. Leggi questo messaggio inviato in un gruppo Telegram familiare.
Il proprietario del gruppo si chiama Alfio (è il creatore di Genesi, l'AI del gruppo).

Determina SE il mittente sta dichiarando la PROPRIA relazione con Alfio o con la sua famiglia (cioè chi è il mittente stesso rispetto ad Alfio).

ATTENZIONE CRITICA AI FALSI POSITIVI (VOCATIVI):
- Il mittente deve dichiarare se stesso/a! Non confondere quando il mittente si rivolge o chiama qualcun altro con un nome di parentela.
- Se Sandra scrive "Stamattina la connessione ti funziona mamma????", Sandra NON è la madre! Si sta rivolgendo a sua madre (mamma è usato come vocativo). In questo caso rispondi {"found": false}.
- Se qualcuno scrive "Auguri mamma!", il mittente NON è la mamma, ma sta facendo gli auguri alla propria mamma. Rispondi {"found": false}.
- Se Ennio scrive "Rita, ti amo", Ennio non è Rita. Rispondi {"found": false}.
- Esempi di relazioni proprie VALIDE (dove il mittente dice chi è LUI stesso):
  "Sono la sorella di Alfio", "sono sua madre" (detto da chi scrive riferendosi a se stesso, es. "qui scrive la mamma"), "sono il fratello", "mi chiamo Rita, la moglie", "io sono Ennio il figlio", "sono la cugina".

Se c'è una relazione dichiarata del MITTENTE stesso, ritorna:
{
  "found": true,
  "relationship": "sorella",           // ruolo in italiano, singolare (sorella/fratello/figlia/figlio/moglie/madre/padre/cugina/nipote/cognata ecc.)
  "name": "Maria",                     // nome del mittente se menzionato o se si auto-identifica, altrimenti null
  "notes": "frase breve opzionale"     // max 10 parole di contesto
}

Se NON c'è nessuna dichiarazione esplicita su chi sia il mittente stesso: {"found": false}
Rispondi SOLO con JSON valido.
"""

MAX_HISTORY    = 30   # turni conservati per gruppo (era 20)
MAX_FACTS      = 40   # fatti per membro
HISTORY_INJECT = 12   # turni iniettati nel prompt (era 8)
MAX_RAW_MSGS   = 500  # "diario" del gruppo persistito su disco (era 40): storico profondo
RAW_INJECT     = 20   # ultimi N messaggi iniettati nel prompt (snello = risposta più reattiva; il diario resta 500)
SUMMARY_RAW_LIMIT = 150  # quanti messaggi del diario alimentano il riepilogo periodico
CONSOLIDATION_INTERVAL = 86400  # 24h in secondi
OBSERVATION_EVERY_N    = 5      # ogni N messaggi di gruppo → 1 osservazione lab
SUMMARY_INTERVAL       = 21600  # 6h — riepilogo discussioni giornaliero

# ── Gender inference ───────────────────────────────────────────────────────────
_FEMALE_RELATIONS = {
    "madre", "mamma", "moglie", "sorella", "figlia", "nonna", "zia",
    "cugina", "nipote", "cognata", "nuora", "suocera", "matrigna",
    "fidanzata", "compagna", "ragazza", "ex",
}
_MALE_RELATIONS = {
    "padre", "papà", "papa", "marito", "fratello", "figlio", "nonno", "zio",
    "cugino", "nipote", "cognato", "genero", "suocero", "patrigno",
    "fidanzato", "compagno", "ragazzo",
}

def _infer_gender(relationship: str) -> str:
    """Ritorna 'F', 'M' o '' in base al tipo di relazione."""
    r = relationship.strip().lower()
    if r in _FEMALE_RELATIONS:
        return "F"
    if r in _MALE_RELATIONS:
        return "M"
    # suffisso -a → F, -o → M (cugina/cugino ecc.)
    if r.endswith("a"):
        return "F"
    if r.endswith("o"):
        return "M"
    return ""


_DAILY_SUMMARY_PROMPT = """\
Sei un assistente che riassume le discussioni di una chat familiare.
Leggi questi messaggi e scrivi un riepilogo compatto (max 5 righe, in italiano naturale)
di COSA si è discusso: argomenti concreti, aggiornamenti personali, notizie condivise.
NON elencare chi ha scritto cosa — sintetizza i temi. Usa frasi brevi.
Esempio: "Mariella è partita stamattina con le ruote nuove verso Siracusa. Rita aspettava Ennio alla fermata. Scambio di saluti mattutini con affetto."
Se non c'è nulla di rilevante oltre ai saluti, scrivi solo: "Saluti di routine."
"""

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

def _summary_key(chat_id: int) -> str:
    return f"telegram:group_summary:{chat_id}"


async def _storage():
    from core.storage import storage
    return storage


# ── Member profile ─────────────────────────────────────────────────────────────

async def get_member(from_id: int) -> dict:
    s = await _storage()
    return await s.load(_member_key(from_id), default={}) or {}


def _sanitize_member_name(name: str) -> str:
    """Pulisce un pushName strano: rimuove emoji/simboli, accorcia. NON inventa."""
    if not name:
        return ""
    n = re.sub(r"[^\w\sàèéìòóùÀÈÉÌÒÓÙ'’\-]", "", str(name), flags=re.UNICODE)
    n = re.sub(r"\s+", " ", n).strip()
    return n[:40]


def member_display_name(member: dict, fallback: str = "") -> str:
    """Nome con cui Genesi deve chiamare il membro: il preferito (corretto) vince."""
    return (member.get("preferred_name") or member.get("first_name")
            or member.get("display_name") or fallback or "").strip()


async def set_preferred_name(from_id: int, name: str):
    """Imposta il nome PREFERITO del membro (da una correzione): vince e non viene sovrascritto."""
    name = _sanitize_member_name(name)
    if not name:
        return
    s = await _storage()
    member = await get_member(from_id)
    member["from_id"]        = from_id
    member["preferred_name"] = name
    member["first_name"]     = name
    member.setdefault("joined_at", int(time.time()))
    await s.save(_member_key(from_id), member)
    log("GROUP_MEMBER_NAME_CORRECTED", from_id=from_id, name=name)


async def update_member_seen(from_id: int, first_name: str):
    s = await _storage()
    member = await get_member(from_id)
    member["from_id"]       = from_id
    # Non sovrascrivere mai un nome corretto dall'utente; altrimenti usa il pushName pulito
    if not member.get("preferred_name"):
        _clean = _sanitize_member_name(first_name)
        if _clean:
            member["first_name"] = _clean
    member["last_seen"]     = int(time.time())
    member["message_count"] = member.get("message_count", 0) + 1
    if "joined_at" not in member:
        member["joined_at"] = int(time.time())
    await s.save(_member_key(from_id), member)


async def detect_and_apply_name_correction(from_id: int, sender_name: str, text: str,
                                           participants: list[dict] | None = None):
    """
    Rileva una correzione di nome ("chiamami Pina", "mi chiamo X", "non sono Y sono X",
    "lei si chiama Z") riferita a sé o a un altro membro, e aggiorna il nome. Fail-silent.
    """
    if not text or len(text.strip()) < 5:
        return
    tl = text.lower()
    if not any(k in tl for k in ("chiam", "mi chiamo", "il mio nome", "non sono",
                                 "si chiama", "nome è", "nome e ", "sarei", "sono io")):
        return
    try:
        from core.llm_service import llm_service
        import json as _json
        plist = ", ".join(p.get("name", "") for p in (participants or []) if p.get("name"))
        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            ("In un gruppo, l'utente potrebbe indicare come va chiamato LUI STESSO o un'ALTRA "
             "persona. Estrai SOLO correzioni esplicite di nome (es. \"chiamami Pina\", "
             "\"mi chiamo Anna\", \"non sono X, sono Y\", \"lei si chiama Maria\"). "
             "NON dedurre nomi da saluti o menzioni casuali. Rispondi SOLO JSON: "
             "{\"corrections\":[{\"who\":\"self\"|\"<nome attuale della persona indicata>\",\"name\":\"<nome corretto>\"}]}. "
             "Se non c'è correzione, {\"corrections\":[]}."),
            f"Chi scrive si chiama ora: {sender_name}\nPartecipanti: {plist}\nMessaggio: {text.strip()[:300]}",
            user_id="name-correction", route="memory",
        )
        if not raw:
            return
        mt = re.search(r"\{.*\}", raw, re.S)
        if not mt:
            return
        corr = _json.loads(mt.group(0)).get("corrections", [])
        for c in corr:
            who = (c.get("who") or "").strip()
            new = (c.get("name") or "").strip()
            if not new:
                continue
            if who.lower() in ("self", "io", sender_name.lower(), ""):
                await set_preferred_name(from_id, new)
            else:
                # Correzione su un altro membro: abbinalo per nome attuale tra i partecipanti
                for p in (participants or []):
                    if (p.get("name") or "").lower() == who.lower() and not p.get("is_me"):
                        pid = str(p.get("id", "")).split("@")[0].replace("+", "")
                        try:
                            await set_preferred_name(stable_hash(pid), new)
                        except Exception:
                            pass
                        break
    except Exception as e:
        log("GROUP_NAME_CORRECTION_ERROR", error=str(e))


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

async def get_active_group_members(chat_id: int) -> list[str]:
    """Estrae i nomi unici dei partecipanti attivi che hanno inviato messaggi in questo gruppo."""
    if not chat_id:
        return []
    history = await get_group_history(chat_id, limit=80)
    raw_msgs = await get_raw_messages(chat_id, limit=80)
    
    active = set()
    for h in history:
        name = h.get("first_name")
        if name:
            active.add(name.strip())
    for m in raw_msgs:
        name = m.get("first_name")
        if name:
            active.add(name.strip())
            
    return sorted(list(active))


async def build_group_context(chat_id: int, from_id: int, first_name: str,
                              owner_name: str = "Alfio", current_message: str = "",
                              participants: Optional[list[dict]] = None,
                              is_family_group: bool = True) -> str:
    s        = await _storage()
    member   = await get_member(from_id)
    history  = await get_group_history(chat_id, limit=HISTORY_INJECT)
    insights = await _get_group_insights(chat_id)
    raw_msgs = await get_raw_messages(chat_id, limit=RAW_INJECT)
    summary  = await _get_group_summary(chat_id)

    # 1. Rileva nome del gruppo e membri attivi in questo specifico gruppo
    group_title = await s.load(f"group_title:{chat_id}", default="Casa Turrisi" if chat_id > 0 else "Gruppo")
    
    member_names_detailed = []
    num_humans = 0
    has_bot = False

    if participants:
        from collections import Counter
        name_counts = Counter()
        resolved_participants = []
        
        for p in participants:
            p_id = p.get("id", "")
            is_me = p.get("is_me", False)
            clean_jid = p_id.split("@")[0].replace("+", "")
            
            # Esclude esplicitamente il bot (sia per JID, sia per LID) dal conteggio umani
            if is_me or clean_jid in ("69123891531797", "393313650671"):
                has_bot = True
                continue
                
            try:
                p_int = stable_hash(clean_jid)
                p_member = await get_member(p_int)
            except Exception:
                p_member = {}
                
            p_name = member_display_name(p_member, fallback=_sanitize_member_name(p.get("name") or ""))
            if not p_name:
                p_name = f"+{clean_jid}"
                
            resolved_participants.append({
                "id": p_id,
                "name": p_name,
                "clean_jid": clean_jid
            })
            name_counts[p_name] += 1
            num_humans += 1
            
        for rp in resolved_participants:
            name = rp["name"]
            if name_counts[name] > 1:
                # Disambigua con le ultime 4 cifre del telefono
                suffix = rp["clean_jid"][-4:]
                disambiguated_name = f"{name} (tel: ...{suffix})"
            else:
                disambiguated_name = name
            member_names_detailed.append(disambiguated_name)
            
        active_members = sorted(member_names_detailed)
    else:
        # Fallback classico Telegram / Storico
        active_members = await get_active_group_members(chat_id)
        if first_name not in active_members:
            active_members.append(first_name)
            active_members = sorted(list(set(active_members)))
        num_humans = len(active_members)
        has_bot = True # Genesi è nel gruppo

    lines = []

    # [IDENTITÀ — globale per ogni gruppo/piattaforma]
    lines.append(
        "[IDENTITÀ — FONDAMENTALE: TU sei Genesi. In questo gruppo \"Genesi\" sei TU. "
        "Se qualcuno ti nomina, ti fa una domanda o ti critica (es. \"Genesi non ha capito\"), "
        "si rivolge a TE: rispondi SEMPRE in prima persona (\"io\"), non parlare MAI di Genesi "
        "in terza persona e non impersonare altri membri. Segui il filo della conversazione: "
        "rispondi davvero a ciò che è stato appena detto/chiesto, senza cambiare argomento né "
        "dare saluti generici fuori contesto.]"
    )

    # [INFO GRUPPO CORRENTE]
    lines.append(f"[INFO GRUPPO: Ti trovi nel gruppo '{group_title}']")
    total_members = num_humans + (1 if has_bot else 0)
    lines.append(f"[CONTEGGIO MEMBRI DEL GRUPPO: In totale ci sono {total_members} membri: tu (e gli altri umani) e io (Genesi, l'assistente AI).]")
    if active_members:
        lines.append(f"[LISTA DETTAGLIATA MEMBRI UMANI: {', '.join(active_members)}]")
    lines.append("[⚠️ IMPORTANTE: I membri che iniziano con '+' o contengono solo cifre sono partecipanti di cui non conosciamo ancora il nome (es. altri numeri o account secondari). NON associarli o confonderli MAI con Rita, Ennio o altri familiari dell'albero genealogico! Non allucinare i loro nomi.]")
    lines.append("")

    # 📅 Contesto Temporale, Festività e Compleanni di Oggi
    try:
        from core.birthday_service import get_today_events_context
        event_ctx = await get_today_events_context(chat_id)
        if event_ctx:
            lines.append("[📅 CONTESTO TEMPORALE, FESTIVITÀ E COMPLEANNI DI OGGI — argomenta coerentemente se rilevante:]")
            for line in event_ctx.split("\n"):
                lines.append(f"  {line}")
            lines.append("")
    except Exception as e:
        logger.warning("Error injecting today events context: %s", e)

    # 🧠 Memoria Episodica della Famiglia (eventi recenti e importanti di famiglia)
    if is_family_group:
        try:
            from core.episode_memory import episode_memory as _em
            relevant_episodes = await _em.get_relevant(_OWNER_USER_ID_FOR_TREE, current_message, limit=5)
            if relevant_episodes:
                lines.append("[MEMORIA EPISODICA DELLA FAMIGLIA (situazioni attive in corso):]")
                for ep in relevant_episodes:
                    lines.append(f"  • {ep.get('text')}")
                lines.append("")
        except Exception as e:
            logger.warning("Error injecting family episodic memory: %s", e)

    # ⚠️ Correzioni esplicite — INIETTATE PRIME, massima priorità
    corrections = await get_group_corrections(chat_id, max_age_seconds=604800)  # 7 giorni
    if corrections:
        lines.append("[⚠️ CORREZIONI IMPORTANTI — non ripetere le informazioni vecchie:]")
        for c in corrections[-8:]:  # max 8 correzioni recenti
            member_name = c.get("member", "?")
            old = c.get("old_info", "")
            new = c.get("new_info", "")
            lines.append(f"  • {member_name} ha corretto: '{old}' → ora è: '{new}'")
        lines.append("")

    # Riepilogo sessioni precedenti (ogni 6h) — dà a Genesi memoria cross-sessione
    if summary:
        lines.append("[RIEPILOGO DISCUSSIONI RECENTI (ultime ore):]")
        lines.append(f"  {summary}")

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
        lines.append("[DINAMICHE DELLA FAMIGLIA (apprese nel tempo):]")
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

    # Scambi con Genesi (storia con le risposte date) — sempre mostrata, non in elif
    if history:
        lines.append("[RISPOSTE RECENTI DI GENESI IN QUESTO GRUPPO:]")
        for h in history[-6:]:
            name = h.get("first_name", "?")
            msg  = h.get("text", "")[:100]
            resp = h.get("response", "")[:150]
            lines.append(f"  {name}: {msg}")
            lines.append(f"  → Genesi: {resp}")
        lines.append("[FINE RISPOSTE]")

    # Albero familiare completo (per inferenze sui gradi di parentela)
    if is_family_group:
        fdata = await s.load(_family_key(_OWNER_USER_ID_FOR_TREE), default={}) or {}
        family_chain = fdata.get("family_chain", "")
        if family_chain:
            lines.append(family_chain)

    # Nota famiglia o esterna
    rel = member.get("relationship_to_owner", "")
    gender = member.get("gender") or _infer_gender(rel)
    if is_family_group and rel and rel != "owner":
        pronoun = "a" if gender == "F" else "o" if gender == "M" else "o/a"
        tratta   = f"Trattala" if gender == "F" else "Trattalo" if gender == "M" else "Trattalo/a"
        rel_note = f" È {rel} di {owner_name} (genere: {'F — usa aggettivi/pronomi al femminile' if gender == 'F' else 'M — usa aggettivi/pronomi al maschile' if gender == 'M' else 'non determinato'})."
    else:
        tratta = "Trattalo/a"
        rel_note = ""
        
    if is_family_group:
        lines.append(
            f"[CONTESTO FAMIGLIA:{rel_note} "
            f"{tratta} con calore e familiarità, come un parente. "
            f"Usa i gradi di parentela corretti quando parli di altri membri. "
            f"Puoi fare riferimento a quello che altri hanno detto. "
            f"ATTENZIONE ASSOLUTA DI COERENZA: Ti trovi nel gruppo '{group_title}'. I membri attivi qui sono esclusivamente: {', '.join(active_members)}. "
            f"NON nominare, non salutare e non fare riferimento a parenti assenti da questo specifico gruppo (es. se sei nel gruppo di WhatsApp dove non ci sono Katia, Sandra, Mariella, Iolanda, non nominarle e non parlare di loro!). "
            f"SOLLECITAZIONE SITUAZIONI IN CORSO: Se tra le situazioni attive in corso ('situazioni attive in corso') ci sono problemi irrisolti (es. Rita con la caviglia slogata, o qualcuno in viaggio) e nella chat recente non se ne parla da un po', trova l'occasione adatta e in modo del tutto spontaneo ed affettuoso di chiedere aggiornamenti (es. 'Rita, come va la caviglia oggi? Ti fa ancora male?'). Se l'utente ti dice che è guarito o rientrato, commenta con gioia!]"
        )
    else:
        lines.append(
            f"[ATTENZIONE ASSOLUTA DI COERENZA: Ti trovi nel gruppo esterno '{group_title}'. "
            f"I membri attivi qui sono: {', '.join(active_members)}. "
            f"NON SEI NEL GRUPPO DELLA FAMIGLIA. NON nominare Alfio, Rita, Ennio o altri membri della famiglia Turrisi a meno che non siano esplicitamente presenti o menzionati in questo gruppo. Mantieni un profilo educato, distaccato ma utile.]"
        )

    # Regola anti-staleness: non tirare fuori vecchie discussioni senza motivo
    lines.append(
        "[REGOLA FONDAMENTALE: Rispondi SOLO a ciò che viene detto ADESSO. "
        "Non tirare in mezzo argomenti passati (malattie, problemi, eventi) "
        "a meno che il messaggio attuale non li citi esplicitamente. "
        "Se vuoi chiedere di un argomento passato, fallo con una domanda — non darlo per scontato ancora attuale.]"
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


# ── Riepilogo discussioni (cross-sessione) ────────────────────────────────────

async def _get_group_summary(chat_id: int) -> str:
    s = await _storage()
    data = await s.load(_summary_key(chat_id), default={}) or {}
    return data.get("summary", "")


async def summarize_group_discussion_if_needed(chat_id: int):
    """
    Ogni 6h genera un riepilogo compatto delle ultime discussioni del gruppo
    usando il buffer di messaggi grezzi. Iniettato in build_group_context()
    come memoria cross-sessione per Genesi.
    """
    try:
        s    = await _storage()
        data = await s.load(_summary_key(chat_id), default={}) or {}
        last = data.get("last_summarized_at", 0)
        if time.time() - last < SUMMARY_INTERVAL:
            return

        raw_msgs = await get_raw_messages(chat_id, limit=SUMMARY_RAW_LIMIT)
        if len(raw_msgs) < 5:
            return

        from core.llm_service import llm_service

        raw_text = "\n".join(
            f"{m.get('first_name', '?')}: {m.get('text', '')[:150]}"
            for m in raw_msgs
        )
        summary = await llm_service._call_model(
            "openai/gpt-4o-mini",
            _DAILY_SUMMARY_PROMPT,
            raw_text,
            user_id="group-summary",
            route="memory",
        )
        if not summary or not summary.strip():
            return

        data["summary"]           = summary.strip()[:600]
        data["last_summarized_at"] = int(time.time())
        await s.save(_summary_key(chat_id), data)
        logger.info("GROUP_SUMMARY_GENERATED chat_id=%s len=%d", chat_id, len(data["summary"]))

    except Exception as exc:
        logger.debug("GROUP_SUMMARY_ERROR chat_id=%s err=%s", chat_id, exc)


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
        # Albero genealogico con genere esplicito
        s2   = await _storage()
        prof = await s2.load(f"profile:{owner_user_id}", default={}) or {}
        ft   = prof.get("family_tree", {})
        if ft:
            gender_lines = []
            for v in ft.values():
                _n  = v.get("name") or v.get("display_name", "")
                _r  = v.get("relationship", "")
                _g  = v.get("gender") or _infer_gender(_r)
                if _n and _r:
                    _glabel = "F" if _g == "F" else "M" if _g == "M" else "?"
                    gender_lines.append(f"    {_n}: {_r} ({_glabel})")
            if gender_lines:
                lines.append("  Genere familiare (usa accordo grammaticale corretto):")
                lines.extend(gender_lines)
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
    if not first_name or first_name.lower().strip() == "alfio" or member_id == "494065944" or "494065944" in member_id:
        logger.info("FAMILY_RELATIONSHIP_SKIP: sender is owner (Alfio) to prevent self-mapping")
        return
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
                _g = _infer_gender(relationship)
                if _g:
                    member["gender"] = _g
                facts = member.get("facts", {})
                facts["relazione_con_alfio"] = relationship
                if _g:
                    facts["genere"] = _g
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
        _gender = _infer_gender(relationship)
        family_tree[tree_key] = {
            "name":         name,
            "relationship": relationship,
            "gender":       _gender,
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


# ── Correzioni esplicite dei membri ───────────────────────────────────────────
# Quando qualcuno corregge Genesi ("no, non è più così", "sbagliato", ecc.)
# la correzione viene salvata e iniettata in build_group_context() come avvertimento.

MAX_CORRECTIONS = 30  # max correzioni per gruppo

_CORRECTION_KEY = lambda chat_id: f"telegram:group_corrections:{chat_id}"

_CORRECTION_DETECT_PROMPT = """\
Stai analizzando un messaggio in una chat di famiglia dove Genesi (AI) ha appena risposto.
Determina SE il messaggio contiene una correzione esplicita di qualcosa che Genesi ha detto
o di un'informazione vecchia/sbagliata che Genesi ha tirato fuori.

Segnali di correzione: "no, non è così", "sbagliato", "quella cosa è cambiata", "non sono più",
"non è più", "adesso è diverso", "stai sbagliando", "ti sbagli", "non dire più", ecc.

Se c'è una correzione, rispondi con JSON:
{
  "found": true,
  "old_info": "breve descrizione della cosa errata/vecchia (max 20 parole)",
  "new_info": "la versione corretta/aggiornata (max 20 parole)",
  "member": "nome del membro che ha corretto"
}
Se NON è una correzione: {"found": false}
Rispondi SOLO con JSON valido.
"""


async def detect_and_save_correction(
    chat_id: int, from_id: int, first_name: str, text: str, last_genesi_response: str
) -> bool:
    """
    Rileva se il messaggio è una correzione a qualcosa che Genesi ha detto.
    Se sì, salva la correzione nel storage del gruppo.
    Ritorna True se è stata rilevata e salvata una correzione.
    Fail-silent.
    """
    # Fast-path: parole chiave di correzione per evitare LLM su ogni messaggio
    _CORRECTION_KW = (
        "sbagliato", "sbagliata", "sbagli", "ti sbagli",
        "non è così", "non è più", "non sono più", "non siamo più",
        "è cambiato", "è cambiata", "sono cambiate", "sono cambiati",
        "adesso è", "ora è", "adesso sono", "ora sono",
        "non dire più", "smettila di", "non tirare fuori",
        "quella cosa è passata", "è passato", "è passata",
        "non è vero", "non era vero", "questo non vale",
    )
    text_lower = text.lower()
    if not any(kw in text_lower for kw in _CORRECTION_KW):
        return False

    try:
        from core.llm_service import llm_service
        user_msg = (
            f"Ultima risposta di Genesi: {last_genesi_response[:300]}\n\n"
            f"Messaggio di {first_name}: {text[:300]}"
        )
        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            _CORRECTION_DETECT_PROMPT,
            user_msg,
            user_id="group-correction-detector",
            route="memory",
        )
        if not raw:
            return False
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = json.loads(clean.strip())
        if not parsed.get("found"):
            return False

        old_info = (parsed.get("old_info") or "").strip()
        new_info = (parsed.get("new_info") or text[:100]).strip()
        if not old_info or not new_info:
            return False

        # Salva la correzione
        s = await _storage()
        corrections = await s.load(_CORRECTION_KEY(chat_id), default=[]) or []
        if not isinstance(corrections, list):
            corrections = []

        corrections.append({
            "member":    first_name,
            "from_id":   from_id,
            "old_info":  old_info,
            "new_info":  new_info,
            "ts":        int(time.time()),
        })
        corrections = corrections[-MAX_CORRECTIONS:]
        await s.save(_CORRECTION_KEY(chat_id), corrections)

        # Aggiorna anche i facts del membro se la correzione riguarda lui/lei
        member = await get_member(from_id)
        member_corrections = member.get("corrections", [])
        if not isinstance(member_corrections, list):
            member_corrections = []
        member_corrections.append({"old": old_info, "new": new_info, "ts": int(time.time())})
        member["corrections"] = member_corrections[-10:]
        await s.save(_member_key(from_id), member)

        logger.info(
            "GROUP_CORRECTION_SAVED chat_id=%s member=%s old=%s new=%s",
            chat_id, first_name, old_info[:40], new_info[:40]
        )
        return True

    except Exception as exc:
        logger.debug("GROUP_CORRECTION_ERROR chat_id=%s err=%s", chat_id, exc)
        return False


async def get_group_corrections(chat_id: int, max_age_seconds: int = 604800) -> list:
    """
    Ritorna le correzioni recenti del gruppo (default: ultima settimana).
    """
    try:
        s = await _storage()
        corrections = await s.load(_CORRECTION_KEY(chat_id), default=[]) or []
        now = int(time.time())
        return [c for c in corrections if now - c.get("ts", 0) < max_age_seconds]
    except Exception:
        return []
