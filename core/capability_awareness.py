"""
CAPABILITY AWARENESS — Genesi
Consente a Genesi di conoscere le proprie capacità e di rilevare/loggare i gap.

Funzionalità:
- Carica capability_map.json (struttura statica, descrizione capacità)
- Rileva gap (richieste che Genesi non può soddisfare) in modo euristico
- Logga i gap in memory/admin/capability_gaps.json (taccuino virtuale)
- Genera proposte di integrazione tramite LLM su richiesta admin
- Inietta contesto capacità nel prompt quando l'utente fa domande meta

Fail-silent su ogni errore — non impatta mai il flusso chat principale.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("genesi")

# ── Percorsi ───────────────────────────────────────────────────────────────────
_CAPABILITY_MAP_PATH = Path("memory/capability_map.json")
_GAPS_PATH           = Path("memory/admin/capability_gaps.json")
_MAX_GAPS            = 500   # rolling window

# ── Pattern meta-query (domande su Genesi stessa) ──────────────────────────────
_META_PATTERNS = [
    r"\bsai fare\b",
    r"\bpuoi fare\b",
    r"\bcosa (sai|riesci|puoi|sei capace|sei in grado)\b",
    r"\bsei capace\b",
    r"\bsei in grado\b",
    r"\bcapacità\b",
    r"\bfunzionalità\b",
    r"\bintegrazione\b",
    r"\bcomandi\b",
    r"\bcomando\b",
    r"\bhai accesso\b",
    r"\briesci a\b",
    r"\bpuoi (leggere|scrivere|inviare|accedere|connetterti|gestire|controllare)\b",
    r"\bconnessa a\b",
    r"\bcollegata a\b",
    r"\bcosa non (sai|puoi|riesci)\b",
    r"\blimiti\b",
    r"\blimitazioni\b",
    r"\bcome funzioni\b",
    r"\bcome sei fatta\b",
    r"\bcosa sei\b",
]
_META_RE = re.compile("|".join(_META_PATTERNS), re.IGNORECASE)

# ── Indicatori di gap nella risposta ──────────────────────────────────────────
_GAP_RESPONSE_PATTERNS = [
    r"\bnon (sono|riesco|posso|ho|ho accesso)\b",
    r"\bnon (ho la possibilità|ho modo|ho strumenti)\b",
    r"\bpurtroppo non\b",
    r"\bmi dispiace.*non\b",
    r"\bnon (è disponibile|è integrata?|è collegata?|è supportata?)\b",
    r"\bnon (rientra|fa parte)\b",
    r"\bnon (dispongo|gestisco|controllo|accedo)\b",
    r"\bfuori dalla mia portata\b",
    r"\bnon (ho accesso|gestisco) (a |al |alla |agli |alle |ai )\b",
    r"\bnon integra(ta|to)?\b",
    r"\bnon è una (mia |delle mie )\b",
    r"\bsenza accesso\b",
    r"\bnon (è possibile|posso) per ora\b",
    r"\bfunzionalità non (disponibile|attiva)\b",
    r"\bnon (mi è possibile|è in mio potere)\b",
    r"\bnon (gestisco|monitoraggio|controllo) notifich\b",
]
_GAP_RE = re.compile("|".join(_GAP_RESPONSE_PATTERNS), re.IGNORECASE)

# ── Keyword che suggeriscono richiesta di capacità assente ────────────────────
_GAP_REQUEST_PATTERNS = [
    r"\bOutlook\b", r"\bYahoo\b", r"\bLibero\b",
    r"\bInstagram\b", r"\bFacebook\b", r"\bTikTok\b",
    r"\bNotifiche\b.*\bapp\b",
    r"\bchiama(mi|re|)\b.*\btelefono\b",
    r"\bchiama(mi|re)\b",
    r"\btelefonami\b",
    r"\baccendi\b.*\bluc[ei]\b",
    r"\btermostato\b",
    r"\bsmart home\b",
    r"\bcasa intelligente\b",
    r"\bAmazon\b.*\bprima\b",
    r"\bNetflix\b",
    r"\bSpotify\b",
    r"\bApple Music\b",
    r"\bpaga\b.*\bcarta\b",
    r"\btransazione\b",
    r"\bbonifico\b",
    r"\bLinkedIn\b.*\b(messaggio|contatto|post)\b",
    r"\bTwitter\b.*\b(tweet|post|messaggio)\b",
    r"\bX\.com\b",
]
_GAP_REQ_RE = re.compile("|".join(_GAP_REQUEST_PATTERNS), re.IGNORECASE)


# ── API pubblica ───────────────────────────────────────────────────────────────

def load_capability_map() -> dict:
    """Carica la capability map statica. Ritorna {} se non trovata."""
    try:
        if _CAPABILITY_MAP_PATH.exists():
            return json.loads(_CAPABILITY_MAP_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("CAPABILITY_MAP_LOAD_ERROR err=%s", e)
    return {}


def is_meta_query(user_message: str) -> bool:
    """Ritorna True se il messaggio è una domanda sulle capacità di Genesi."""
    try:
        return bool(_META_RE.search(user_message))
    except Exception:
        return False


def build_capability_context_block(capability_map: dict) -> str:
    """
    Costruisce un blocco di testo da iniettare nel contesto LLM.
    Compatto (< 2KB) — solo le info essenziali.
    """
    try:
        if not capability_map:
            return ""

        intents   = capability_map.get("supported_intents", {})
        tools     = capability_map.get("active_tools", {})
        platforms = capability_map.get("platforms", {})
        limits    = capability_map.get("explicit_limits", [])

        lines = ["[CAPACITÀ DI GENESI — Riferimento interno]"]

        if intents:
            intent_list = ", ".join(
                k for k, v in intents.items()
                if not isinstance(v, str) or "conditional" not in v.lower()
            )
            lines.append(f"Intent supportati: {intent_list}")

        active_tools = [k for k, v in tools.items() if v is True]
        conditional_tools = [k for k, v in tools.items() if isinstance(v, str) and "conditional" in v]
        if active_tools:
            lines.append(f"Tool attivi: {', '.join(active_tools)}")
        if conditional_tools:
            lines.append(f"Tool condizionali (richiedono config): {', '.join(conditional_tools)}")

        if platforms:
            lines.append(f"Piattaforme: {', '.join(platforms.keys())}")

        if limits:
            lines.append("Limiti espliciti:")
            for lim in limits:
                lines.append(f"  • {lim}")

        return "\n".join(lines)
    except Exception as e:
        logger.debug("CAPABILITY_CONTEXT_BUILD_ERROR err=%s", e)
        return ""


def detect_gap(
    user_message: str,
    response: str,
    intent: str,
) -> Tuple[bool, Optional[str]]:
    """
    Rileva se c'è un gap di capacità.
    Ritorna (is_gap, gap_type) — puro, nessun I/O.

    gap_type: "missing_integration" | "feature_requested" | "explicit_limit"
    """
    try:
        # 1. La risposta contiene espliciti "non posso/non ho accesso"
        if _GAP_RE.search(response):
            # Distingue: richiesta di funzione assente vs limite noto
            if _GAP_REQ_RE.search(user_message):
                return True, "explicit_limit"
            return True, "missing_integration"

        # 2. Il messaggio richiede una capacità assente
        if _GAP_REQ_RE.search(user_message):
            return True, "feature_requested"

        # 3. Intent "general" su messaggi lunghi con negazione in risposta
        if intent in ("general", "general_llm") and len(user_message) > 60:
            if re.search(r"\bnon (ho|posso|riesco|sono in grado)\b", response, re.IGNORECASE):
                return True, "missing_integration"

        return False, None
    except Exception:
        return False, None


async def log_gap(
    user_message: str,
    response: str,
    intent: str,
    platform: str,
    gap_type: str,
    user_id: str = "",
) -> None:
    """
    Scrive il gap nel taccuino virtuale (memory/admin/capability_gaps.json).
    Fail-silent.
    """
    try:
        _GAPS_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Carica gaps esistenti
        try:
            gaps_data = json.loads(_GAPS_PATH.read_text(encoding="utf-8")) if _GAPS_PATH.exists() else {"gaps": []}
        except Exception:
            gaps_data = {"gaps": []}

        gaps = gaps_data.get("gaps", [])

        # Deduplication soft: se stesso gap_type + stessa keyword negli ultimi 10 entry → skip
        recent_msgs = [g.get("user_message_snippet", "") for g in gaps[-10:]]
        snippet = user_message[:80]
        if any(snippet[:40] in m for m in recent_msgs):
            return

        gaps.append({
            "ts":                    datetime.utcnow().isoformat(),
            "gap_type":              gap_type,
            "intent":                intent,
            "platform":              platform,
            "user_id":               user_id[:20] if user_id else "",
            "user_message_snippet":  snippet,
            "response_snippet":      response[:120],
        })

        gaps_data["gaps"] = gaps[-_MAX_GAPS:]
        gaps_data["updated_at"] = datetime.utcnow().isoformat()
        gaps_data["total"] = len(gaps_data["gaps"])

        _GAPS_PATH.write_text(json.dumps(gaps_data, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("CAPABILITY_GAP_LOGGED gap_type=%s intent=%s platform=%s",
                    gap_type, intent, platform)
    except Exception as e:
        logger.debug("CAPABILITY_GAP_LOG_ERROR err=%s", e)


async def get_gaps_summary() -> dict:
    """Legge e aggrega il taccuino dei gap. Ritorna {} se vuoto."""
    try:
        if not _GAPS_PATH.exists():
            return {"total": 0, "gaps": [], "by_type": {}, "by_intent": {}}

        gaps_data = json.loads(_GAPS_PATH.read_text(encoding="utf-8"))
        gaps = gaps_data.get("gaps", [])

        by_type: dict = {}
        by_intent: dict = {}
        for g in gaps:
            t = g.get("gap_type", "unknown")
            i = g.get("intent", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
            by_intent[i] = by_intent.get(i, 0) + 1

        return {
            "total":      len(gaps),
            "by_type":    by_type,
            "by_intent":  by_intent,
            "recent":     gaps[-20:],
            "updated_at": gaps_data.get("updated_at"),
        }
    except Exception as e:
        logger.debug("CAPABILITY_GAPS_SUMMARY_ERROR err=%s", e)
        return {"total": 0, "gaps": [], "by_type": {}, "by_intent": {}}


async def generate_proposals(llm_service) -> dict:
    """
    Chiama il LLM per generare proposte di integrazione basate sui gap.
    Ritorna {"proposals": [...], "generated_at": "..."}.
    Fail-silent.
    """
    try:
        summary = await get_gaps_summary()
        if summary["total"] == 0:
            return {"proposals": [], "generated_at": datetime.utcnow().isoformat(), "note": "Nessun gap registrato"}

        cap_map = load_capability_map()
        limits  = cap_map.get("explicit_limits", [])

        # Prepara testo richieste ricorrenti
        by_type   = summary.get("by_type", {})
        recent    = summary.get("recent", [])
        snippets  = "\n".join(
            f"- [{g['gap_type']}] {g['user_message_snippet']}"
            for g in recent[-30:]
        )

        prompt_system = (
            "Sei un consulente tecnico che analizza i gap di un assistente AI e propone integrazioni prioritarie. "
            "Ragioni in modo pratico e specifico — non in modo generico. "
            "Sei breve e preciso. Rispondi SOLO in JSON valido."
        )

        prompt_user = (
            f"Analisi gap registrati:\n"
            f"Totale: {summary['total']} gap\n"
            f"Per tipo: {json.dumps(by_type, ensure_ascii=False)}\n\n"
            f"Esempi recenti (ultimi 30):\n{snippets}\n\n"
            f"Limiti attuali dell'assistente:\n" +
            "\n".join(f"- {l}" for l in limits) +
            "\n\nGenera una lista di massimo 5 proposte di integrazione ad alta priorità.\n"
            "Formato JSON richiesto:\n"
            "{\n"
            '  "proposals": [\n'
            '    {\n'
            '      "title": "Nome integrazione",\n'
            '      "rationale": "Perché è utile (basato sui gap)",\n'
            '      "gap_count": 3,\n'
            '      "complexity": "bassa|media|alta",\n'
            '      "example_request": "Esempio di richiesta utente"\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            prompt_system,
            prompt_user,
            user_id="admin",
            route="memory",
        )

        # Estrai JSON dalla risposta
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            parsed["generated_at"] = datetime.utcnow().isoformat()
            parsed["gaps_analyzed"] = summary["total"]
            return parsed

        return {"proposals": [], "generated_at": datetime.utcnow().isoformat(), "error": "parse_failed"}

    except Exception as e:
        logger.debug("CAPABILITY_PROPOSALS_ERROR err=%s", e)
        return {"proposals": [], "generated_at": datetime.utcnow().isoformat(), "error": str(e)}
