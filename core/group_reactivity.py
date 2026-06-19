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
"""
from __future__ import annotations

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
