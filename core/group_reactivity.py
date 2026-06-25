"""
Reattività dei gruppi — logica GLOBALE condivisa (Telegram + WhatsApp + Meta).

Funzioni:
1) Anti-stale: se mentre Genesi elabora una risposta la STESSA persona scrive un
   nuovo messaggio, la risposta vecchia ha perso il contesto → va scartata. Il
   messaggio nuovo riceverà una risposta fresca.
2) Domande inevase: trova l'ultima domanda di un utente a cui NESSUNO ha risposto,
   così Genesi può rispondere direttamente a quella persona.
3) Rilevamento tono emotivo: analizza i messaggi recenti e identifica se il gruppo
   è in modalità umoristica, di lutto/dolore o neutrale, per adattare il tono di risposta.
4) Emotional cooldown: dopo che Genesi risponde a un evento di lutto/ricordo,
   entra in cooldown per quel tema (default 4h) e sopprime risposte empatiche
   ripetitive alle reazioni minimali successive.
"""
from __future__ import annotations

import re
import time

from core.affective_event_decay import (
    ACUTE_SUPPORT,
    GENTLE_AWARENESS,
    affective_decay_stage,
    is_sensitive_affective_text,
)

# (platform, group_id, user_id) -> timestamp ultimo messaggio
_ARRIVALS: dict[tuple, float] = {}

# (platform, group_id) -> list of (user_id, ts) — tutti i messaggi arrivati
_GROUP_ARRIVALS: dict[tuple, list] = {}


# ── Emoji detection helpers ───────────────────────────────────────────────────

_EMOJI_STRIP_RE = re.compile(
    "[\U0001F300-\U0001FAFF"   # Main emoji + supplemental
    "\U00002600-\U000027BF"    # Misc symbols
    "\U0001F1E0-\U0001F1FF"    # Regional indicators (flags)
    "\U0000FE00-\U0000FE0F"    # Variation selectors
    "\U0001F900-\U0001F9FF"    # Supplemental symbols & pictographs
    "\U00002300-\U000023FF"    # Misc technical
    "\U0000200D"               # Zero-width joiner
    "]+",
    flags=re.UNICODE,
)

# Frasi brevi di solidarietà/condoglianza che non devono scatenare risposta
_MINIMAL_REACTION_PHRASES = frozenset((
    "ovunque sei", "sempre con noi", "sempre con te", "sempre tra noi",
    "sempre nei nostri cuori", "sempre nel cuore", "sempre nel nostro cuore",
    "ti pensiamo", "ci pensiamo", "pensando a te", "pensiamo a te",
    "sei sempre", "è sempre con noi", "è sempre con te",
    "sei sempre nel nostro cuore", "sei sempre con noi",
    "un abbraccio", "abbracciamo", "tanti abbracci", "vi abbracciamo",
    "in cielo", "con gli angeli", "tra gli angeli", "sei un angelo",
    "è un angelo", "è con gli angeli", "è tra gli angeli",
    "preghiamo", "nelle nostre preghiere", "nella nostra preghiera",
    "riposa in pace", "rip",
    "ci mancherai", "ci manca", "ci mancavi",
    "nel nostro cuore", "nei nostri cuori",
    "non ti dimenticheremo", "non ti dimentico", "non ti dimentichiamo",
    "ti ricordiamo", "ti ricordo", "ti vogliamo bene",
))

_GRIEF_EMOJIS_SET = frozenset("🙏❤🤍🖤😢😭🕯🌹🕊✝💔😔🥺🫂")

# Frasi canoniche di ricordo/lutto non coperte da _GRIEF_PHRASES
_MEMORIAL_TRIGGER_PHRASES = (
    "non è più con noi", "non è più tra noi", "non c'è più con noi",
    "anche se non è più", "anche se non è più con noi",
    "è sempre con noi", "è sempre tra noi",
    "sempre con noi", "sempre nel cuore", "sempre nei nostri cuori",
    "ricordiamo il suo compleanno", "ricordiamo il suo", "ricordiamo la sua",
    "preghiera per", "con una preghiera", "una preghiera per lui",
    "una preghiera per lei",
    "è tra gli angeli", "è in cielo", "è con gli angeli",
    "ci ha preceduto", "ci ha preceduta",
    "il nostro angelo in cielo",
)


def is_emoji_only_or_reaction(text: str) -> bool:
    """True if the text contains only emoji/symbols and whitespace — no meaningful letters."""
    if not text or not text.strip():
        return True
    clean = _EMOJI_STRIP_RE.sub("", text.strip())
    return not clean.strip()


def is_minimal_social_reaction(text: str) -> bool:
    """
    True for short emotional solidarity messages that don't warrant a standalone
    Genesi response during an emotional cooldown period:
    - Emoji-only (🙏🙏❤️)
    - Short condolence phrase + emoji without a question (❤️❤️❤️ ovunque sei ❤️)
    False for direct questions, long messages, or topic changes.
    """
    if not text or not text.strip():
        return True
    stripped = text.strip()
    # Questions always escape the minimal-reaction gate
    if "?" in stripped:
        return False
    # Pure emoji → minimal
    if is_emoji_only_or_reaction(stripped):
        return True
    # Strip emoji, check what text remains
    text_no_emoji = _EMOJI_STRIP_RE.sub("", stripped).strip()
    if not text_no_emoji:
        return True
    # Long text is substantive — not minimal
    if len(text_no_emoji) > 80:
        return False
    text_lower = text_no_emoji.lower()
    for phrase in _MINIMAL_REACTION_PHRASES:
        if phrase in text_lower:
            return True
    # Short text (≤4 words) combined with grief emoji → social reaction
    words = text_lower.split()
    if len(words) <= 4 and any(e in stripped for e in _GRIEF_EMOJIS_SET):
        return True
    return False


def is_memorial_trigger(text: str) -> bool:
    """
    True if the message describes a memorial/grief event that warrants setting the
    emotional cooldown after Genesi responds to it.
    Covers both the existing _GRIEF_PHRASES/_GRIEF_WORDS and additional Italian
    canonical phrases like "non è più con noi" / "sempre con noi".
    """
    if not text:
        return False
    text_lower = text.lower()
    for phrase in _GRIEF_PHRASES:
        if phrase in text_lower:
            return True
    for word in _GRIEF_WORDS:
        if re.search(r"\b" + word + r"\b", text_lower):
            return True
    for phrase in _MEMORIAL_TRIGGER_PHRASES:
        if phrase in text_lower:
            return True
    return is_sensitive_affective_text(text_lower)


# ── Emotional Cooldown (per-group, in-memory) ────────────────────────────────
# Dopo che Genesi risponde a un evento di lutto/ricordo, il cooldown blocca
# risposte empatiche ripetitive per EMOTIONAL_COOLDOWN_HOURS ore.
# (In-memory: si azzera al riavvio del processo — accettabile per 4h.)

EMOTIONAL_COOLDOWN_HOURS: float = 4.0

# (platform, group_id) → {"topic": str, "set_at": float, "expires_at": float}
_EMOTIONAL_COOLDOWNS: dict[tuple, dict] = {}


def set_group_emotional_cooldown(
    platform: str,
    group_id,
    topic: str = "memorial",
    hours: float = EMOTIONAL_COOLDOWN_HOURS,
) -> None:
    """Activate (or extend) the emotional cooldown for a group.
    Does not shorten an already longer active cooldown."""
    key = (platform, str(group_id))
    now = time.time()
    new_expires = now + hours * 3600
    existing = _EMOTIONAL_COOLDOWNS.get(key)
    if existing and existing.get("expires_at", 0) >= new_expires:
        return
    _EMOTIONAL_COOLDOWNS[key] = {"topic": topic, "set_at": now, "expires_at": new_expires}


def get_group_emotional_cooldown(platform: str, group_id) -> dict | None:
    """Return the active cooldown dict or None if expired/absent.
    Evicts expired entries automatically."""
    key = (platform, str(group_id))
    cd = _EMOTIONAL_COOLDOWNS.get(key)
    if not cd:
        return None
    if time.time() >= cd.get("expires_at", 0):
        _EMOTIONAL_COOLDOWNS.pop(key, None)
        return None
    return cd


def clear_group_emotional_cooldown(platform: str, group_id) -> None:
    """Explicitly clear the cooldown (e.g., after a clear topic change)."""
    _EMOTIONAL_COOLDOWNS.pop((platform, str(group_id)), None)


def mark_arrival(platform: str, group_id, user_id) -> float:
    """Segna l'arrivo di un messaggio e ritorna il suo timestamp."""
    ts = time.time()
    gk = (platform, str(group_id))
    uid = str(user_id)
    _ARRIVALS[(platform, str(group_id), uid)] = ts
    # Aggiorna anche il buffer group-level per il controllo conversazione avanzata
    arrivals = _GROUP_ARRIVALS.setdefault(gk, [])
    arrivals.append((uid, ts))
    # Mantieni solo ultime 200 entries per gruppo
    if len(arrivals) > 200:
        _GROUP_ARRIVALS[gk] = arrivals[-200:]
    # housekeeping globale
    if len(_ARRIVALS) > 5000:
        cutoff = ts - 3600
        for k in [k for k, v in _ARRIVALS.items() if v < cutoff]:
            _ARRIVALS.pop(k, None)
    return ts


def is_superseded(platform: str, group_id, user_id, arrival_ts: float, margin: float = 0.3) -> bool:
    """True se la STESSA persona ha scritto un messaggio più nuovo dopo `arrival_ts`."""
    last = _ARRIVALS.get((platform, str(group_id), str(user_id)), 0.0)
    return last > arrival_ts + margin


def is_conversation_moved_on(platform: str, group_id, arrival_ts: float,
                              threshold: int = 4) -> bool:
    """True se nel gruppo sono arrivati ≥ threshold messaggi da ALTRI utenti dopo arrival_ts.

    Usato per scartare risposte stantie quando la conversazione è avanzata
    significativamente mentre Genesi elaborava, anche se la stessa persona
    non ha scritto di nuovo.
    """
    gk = (platform, str(group_id))
    arrivals = _GROUP_ARRIVALS.get(gk, [])
    count = sum(1 for _, ts in arrivals if ts > arrival_ts + 0.3)
    return count >= threshold


# ── Rilevamento tono emotivo del gruppo ───────────────────────────────────────

# Segnali di lutto/dolore (peso 3 per occorrenza — prevale su humor)
_GRIEF_PHRASES = (
    "lutto", "è mancato", "è mancata", "ci ha lasciato", "ci ha lasciati",
    "è venuto a mancare", "è venuta a mancare", "condoglianze", "rip ",
    "riposa in pace", "funerale", "scomparso", "scomparsa",
    "se n'è andato", "se n'è andata", "il signore lo ha chiamato",
    "preghiamo per", "pregare per", "nostro angelo", "in lutto",
    "ha perso la vita", "deceduto", "deceduta", "veglia funebre",
    "dolore immenso", "ci mancherà", "era una persona", "un grande vuoto",
    "addio per sempre", "lo ricorderemo", "la ricorderemo",
    # Frasi canoniche italiane per ricordi di persone non più in vita
    "non è più con noi", "non è più tra noi", "anche se non è più con noi",
    "ci ha preceduto", "ci ha preceduta",
    "è tra gli angeli", "è in cielo con",
)
# Parole singole di lutto (controllate come parola intera)
_GRIEF_WORDS = ("morto", "morta", "morti", "morte", "perdita", "dolore")

# Segnali di umorismo (peso 2 per occorrenza)
_HUMOR_PHRASES = (
    "ahah", "ahahah", "hahaha", "haha", "hehe", "lol", "lmao",
    "che ridere", "muoio dal ridere", "sto morendo", "troppo forte",
    "che storia", "stavo scherzando", "era uno scherzo", "dai su",
    "ma va", "ma figurati", "ma dai", "ahahha", "hahah",
    "mi fai morire", "ci fai morire",
)
_HUMOR_EMOJIS = frozenset("😂🤣😅😜🤪🙃😝😁😆🤭😈🃏🎭")


def detect_group_emotional_tone(raw_msgs: list, lookback: int = 20) -> dict:
    """Analizza gli ultimi messaggi e rileva il tono emotivo dominante del gruppo.

    Ritorna {"tone": "grief"|"humor"|"normal", "note": str, "prompt_block": str}
    Il prompt_block è la stringa pronta da iniettare nel contesto del LLM.
    """
    msgs = (raw_msgs or [])[-lookback:]
    if not msgs:
        return {"tone": "normal", "note": "", "prompt_block": ""}

    grief_score = 0
    humor_score = 0
    latest_grief_ts = None

    for m in msgs:
        text_lower = (m.get("text") or "").lower()
        text_orig  = (m.get("text") or "")

        # --- Evento delicato ---
        for phrase in _GRIEF_PHRASES:
            if phrase in text_lower:
                grief_score += 3
                latest_grief_ts = m.get("ts", latest_grief_ts)
                break
        else:
            # Solo se nessuna frase composta trovata, controlla parole singole
            import re as _re
            for word in _GRIEF_WORDS:
                if _re.search(r"\b" + word + r"\b", text_lower):
                    grief_score += 3
                    latest_grief_ts = m.get("ts", latest_grief_ts)
                    break
            else:
                if is_sensitive_affective_text(text_lower):
                    grief_score += 3
                    latest_grief_ts = m.get("ts", latest_grief_ts)

        # --- Umorismo ---
        for phrase in _HUMOR_PHRASES:
            if phrase in text_lower:
                humor_score += 2
                break
        else:
            for emoji in _HUMOR_EMOJIS:
                if emoji in text_orig:
                    humor_score += 1
                    break

    if grief_score >= 3:
        stage = affective_decay_stage(latest_grief_ts)
        if stage not in (ACUTE_SUPPORT, GENTLE_AWARENESS):
            return {
                "tone": "normal",
                "note": "memoria storica di evento delicato non piu in stato attivo",
                "stage": stage,
                "prompt_block": "",
            }
        note = "lutto o perdita rilevata nella conversazione del gruppo"
        if stage == ACUTE_SUPPORT:
            block = (
                "[TONO DEL GRUPPO - EVENTO DELICATO RECENTE: Nella chat e emersa una perdita "
                "o una situazione dolorosa recente. Rispondi con rispetto, calore e vicinanza emotiva "
                "solo se il messaggio corrente lo rende appropriato. Evita scherzi fuori luogo e non forzare domande.]\n"
            )
        else:
            block = (
                "[TONO DEL GRUPPO - CONSAPEVOLEZZA DELICATA: Nel gruppo e emerso nei giorni scorsi "
                "un evento doloroso. Mantieni delicatezza di fondo, ma non riportare il tema al centro "
                "e non usare tono condolente se il messaggio corrente e generico.]\n"
            )
        return {"tone": "grief", "note": note, "stage": stage, "prompt_block": block}

    if humor_score >= 4:
        note = "conversazione giocosa e ironica nel gruppo"
        block = (
            "[😄 TONO DEL GRUPPO — GIOCOSO/IRONICO: La conversazione è leggera, spiritosa e ironica. "
            "Sentiti libera di rispondere con umorismo, vivacità e spirito. "
            "Se qualcuno ti prende in giro (foto assurde, scherzi, meme, reazioni buffe), "
            "ricambia nello stesso tono scherzoso — non prendere tutto alla lettera. "
            "Leggi l'ironia: una foto di un piede o di una mano in modo ridicolo è uno scherzo, "
            "non una richiesta medica. Puoi fare battute, rispondere con ironia leggera, "
            "partecipare alla goliardia. Mantieni però sempre il rispetto reciproco.]\n"
        )
        return {"tone": "humor", "note": note, "prompt_block": block}

    return {"tone": "normal", "note": "", "prompt_block": ""}


# Parole che indicano una domanda anche senza punto interrogativo
_Q_HINTS = ("come", "cosa", "quando", "quanto", "dove", "perché", "perche", "chi ",
            "quale", "quali", "qualcuno sa", "mi sapete dire", "mi dite", "consiglio")


def _is_question(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if "?" in t:
        return True
    return any(t.startswith(h) or f" {h}" in t for h in _Q_HINTS) and len(t) > 12


def _q_key(text: str) -> str:
    return "".join(c for c in (text or "").lower() if c.isalnum())[:60]


# group_id -> {question_key: ts} delle domande a cui Genesi ha già risposto
_HANDLED_Q: dict[str, dict] = {}
_HANDLED_TTL = 3600  # 1h


def mark_question_handled(group_id, question_text: str):
    g = str(group_id)
    d = _HANDLED_Q.setdefault(g, {})
    d[_q_key(question_text)] = time.time()
    # pulizia
    cut = time.time() - _HANDLED_TTL
    for k in [k for k, v in d.items() if v < cut]:
        d.pop(k, None)


def _question_handled(group_id, question_text: str) -> bool:
    d = _HANDLED_Q.get(str(group_id), {})
    ts = d.get(_q_key(question_text))
    return bool(ts and time.time() - ts < _HANDLED_TTL)


def find_unanswered_question(raw_msgs: list, current_sender: str = "",
                             group_id=None, lookback: int = 12) -> dict | None:
    """
    Cerca nel buffer recente l'ULTIMA domanda di un utente rimasta senza risposta:
    - è una domanda (punto interrogativo o forma interrogativa)
    - sono arrivati DOPO almeno 2 messaggi di altri (la conversazione è andata avanti)
    - non l'ha posta la persona che sta scrivendo ora (non è il suo stesso messaggio)
    Ritorna {name, text} oppure None.
    """
    if not raw_msgs:
        return None
    msgs = raw_msgs[-lookback:]
    n = len(msgs)
    for i in range(n - 2, -1, -1):  # dalla più recente (escludendo le ultimissime)
        m = msgs[i]
        name = (m.get("first_name") or m.get("name") or "").strip()
        text = (m.get("text") or "").strip()
        if not name or name.lower() == "genesi":
            continue
        if not _is_question(text):
            continue
        # quante repliche dopo? servono almeno 2 messaggi successivi (di chiunque)
        following = msgs[i + 1:]
        if len(following) < 2:
            continue
        # se Genesi ha già parlato dopo la domanda, considerala gestita
        if any((f.get("first_name") or f.get("name") or "").lower() == "genesi" for f in following):
            continue
        # non riproporre la domanda di chi sta scrivendo proprio ora
        if current_sender and name.lower() == current_sender.lower():
            continue
        # già gestita da Genesi? salta (evita di rispondere in loop)
        if group_id is not None and _question_handled(group_id, text):
            continue
        return {"name": name, "text": text[:200]}
    return None
