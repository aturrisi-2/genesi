from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from core.llm_service import LLM_DEFAULT_MODEL, llm_service
from core.log import log
from core.operational_memory.models import (
    Decision,
    Information,
    Issue,
    OperationalEvent,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
)
from core.operational_memory.context_extractor import extract_context
from core.operational_memory.lifecycle_engine import is_conditional_decision
from core.operational_memory.quality import is_noise_text, is_non_operational_note


class OperationalMemoryExtractionError(RuntimeError):
    pass


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    cleaned = _JSON_FENCE_RE.sub("", cleaned).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
    return cleaned


def _stable_id(prefix: str, text: str, source: str) -> str:
    digest = hashlib.sha1(f"{prefix}|{text}|{source}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


# ── Normalizzazione scadenze ("due") ─────────────────────────────────────────
# Il contratto del campo "due" è ISO (YYYY-MM-DD o YYYY-MM-DDTHH:MM): è ciò che
# rende ordinabile la vista agenda. L'LLM è istruito a normalizzare, ma se
# restituisce una data relativa italiana la risolviamo qui in modo
# deterministico rispetto al timestamp del messaggio sorgente; se il valore non
# è risolvibile con certezza, il campo torna null (mai testo libero in "due").

_DUE_ISO_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2})(?::\d{2})?)?")

_DUE_TIME_RE = re.compile(r"\balle?\s+(\d{1,2})(?:[:.](\d{2}))?\b", re.IGNORECASE)

_DUE_DMY_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")

_WEEKDAYS_IT = {
    "lunedi": 0, "lunedì": 0, "martedi": 1, "martedì": 1,
    "mercoledi": 2, "mercoledì": 2, "giovedi": 3, "giovedì": 3,
    "venerdi": 4, "venerdì": 4, "sabato": 5, "domenica": 6,
}


def _normalize_due(value: Any, reference_ts: Any = None) -> str | None:
    """Porta "due" al contratto ISO o a None. Deterministico, nessun LLM."""
    from datetime import datetime, timedelta

    raw = str(value or "").strip()
    if not raw or raw.lower() in {"null", "none", "n/a", "-"}:
        return None

    m = _DUE_ISO_RE.match(raw)
    if m:
        return f"{m.group(1)}T{m.group(2)}" if m.group(2) else m.group(1)

    try:
        ref = datetime.fromisoformat(str(reference_ts)) if reference_ts else datetime.now()
    except (TypeError, ValueError):
        ref = datetime.now()

    low = raw.lower()
    # Prefissi di scadenza ("entro venerdì", "per domani") non cambiano il giorno.
    low = re.sub(r"^\s*(entro|per|entro\s+il|entro\s+la)\s+", "", low)

    tm = _DUE_TIME_RE.search(low)
    time_part = ""
    if tm:
        hh = int(tm.group(1))
        if 0 <= hh <= 23:
            time_part = f"T{hh:02d}:{int(tm.group(2) or 0):02d}"

    day = None
    if re.search(r"\bdopodomani\b", low):
        day = ref.date() + timedelta(days=2)
    elif re.search(r"\bdomani\b", low):
        day = ref.date() + timedelta(days=1)
    elif re.search(r"\b(oggi|stasera|stamattina|stanotte|(nel\s+)?pomeriggio)\b", low):
        day = ref.date()
    else:
        for name, wd in _WEEKDAYS_IT.items():
            if re.search(rf"\b{name}\b", low):
                ahead = (wd - ref.weekday()) % 7 or 7  # prossima occorrenza
                day = ref.date() + timedelta(days=ahead)
                break
    if day is None:
        dm = _DUE_DMY_RE.search(low)
        if dm:
            d, mo = int(dm.group(1)), int(dm.group(2))
            yr = dm.group(3)
            year = int(yr) + (2000 if yr and len(yr) == 2 else 0) if yr else ref.year
            try:
                from datetime import date as _date
                day = _date(year, mo, d)
                if not yr and day < ref.date():
                    day = _date(year + 1, mo, d)
            except ValueError:
                day = None

    if day is None:
        return None
    return f"{day.isoformat()}{time_part}"


def _as_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _intent_for(prefix: str, text: str) -> str:
    low = text.lower()
    if prefix == "issue":
        if any(marker in low for marker in ("non parte", "non alimentata", "manca", "mancano", "guasto", "blocco")):
            return "segnalazione blocco tecnico"
        return "segnalazione problema"
    if prefix == "task":
        return "azione richiesta"
    if prefix == "dec":
        return "decisione operativa"
    if prefix == "question":
        return "chiarimento richiesto"
    return "informazione tecnica"


def _source_excerpt(messages: list[str], source_event: OperationalEvent | None) -> str:
    raw = source_event.content if source_event is not None else " ".join(messages)
    return re.sub(r"\s+", " ", raw or "").strip()[:240]


def _source_metadata(
    messages: list[str],
    source_event: OperationalEvent | None,
    nearby_messages: list[str] | None,
) -> dict[str, Any]:
    excerpt = _source_excerpt(messages, source_event)
    context = extract_context(excerpt or " ".join(messages), nearby_messages or [])
    return {
        "source_event_id": source_event.event_id if source_event is not None else None,
        "source_timestamp": source_event.timestamp if source_event is not None else None,
        "source_sender": source_event.sender if source_event is not None else None,
        "source_excerpt": excerpt,
        "context_area": context.context_area,
        "context_system": context.context_system,
        "context_level": context.context_level,
        "context_location": context.context_location,
        "context_tags": context.context_tags,
    }


def _normalize_items(
    raw_items: list[dict[str, Any]],
    model,
    prefix: str,
    source_meta: dict[str, Any] | None = None,
) -> list[Any]:
    normalized: list[Any] = []
    seen: set[tuple[str, str]] = set()

    for raw in raw_items:
        text = str(raw.get("text") or "").strip()
        source = str(raw.get("source") or "").strip()
        if not text or not source:
            continue
        if is_noise_text(text):
            continue

        data = dict(raw)
        data["text"] = text
        data["source"] = source
        data["id"] = str(raw.get("id") or "").strip() or _stable_id(prefix, text, source)
        confidence = str(raw.get("confidence") or "medium").strip().lower()
        data["confidence"] = confidence if confidence in {"high", "medium", "low"} else "medium"
        if source_meta:
            for key, value in source_meta.items():
                if raw.get(key) in (None, "", []):
                    data[key] = value
        if not data.get("intent"):
            data["intent"] = _intent_for(prefix, text)
        if prefix == "task":
            data["due"] = _normalize_due(
                data.get("due"), (source_meta or {}).get("source_timestamp"))
            owner = str(data.get("owner") or "").strip()
            data["owner"] = owner or None

        key = (text.lower(), source.lower())
        if key in seen:
            continue
        seen.add(key)
        normalized.append(model(**data))

    return normalized


def _parse_state(raw_response: str, source_meta: dict[str, Any] | None = None) -> OperationalState:
    try:
        payload = json.loads(_strip_json_fences(raw_response))
    except json.JSONDecodeError as exc:
        raise OperationalMemoryExtractionError(f"Invalid JSON from extractor: {exc}") from exc

    if not isinstance(payload, dict):
        raise OperationalMemoryExtractionError("Extractor response must be a JSON object")

    return OperationalState(
        decisions=_normalize_items(_as_list(payload, "decisions"), Decision, "dec", source_meta),
        tasks=_normalize_items(_as_list(payload, "tasks"), OperationalTask, "task", source_meta),
        issues=_normalize_items(_as_list(payload, "issues"), Issue, "issue", source_meta),
        information=_normalize_items(_as_list(payload, "information"), Information, "info", source_meta),
        open_questions=_normalize_items(_as_list(payload, "open_questions"), OperationalQuestion, "question", source_meta),
    )


def _build_prompt(messages: list[str]) -> tuple[str, str]:
    numbered = "\n".join(f"{idx + 1}. {message}" for idx, message in enumerate(messages))
    system_prompt = """
Sei un estrattore di stato operativo.

Obiettivo: trasformare messaggi non strutturati in uno stato operativo minimo.

Regole:
- Rispondi SOLO con JSON valido.
- Non inventare nulla: estrai solo elementi supportati dai messaggi.
- Ogni elemento deve avere una fonte nel campo "source", usando "msg N" o una breve citazione.
- Ogni elemento deve avere "confidence": "high", "medium" o "low".
- Quando presenti nel messaggio, includi contesto tecnico: area, sistema, livello, location, tag e intent.
- Se un campo non e' esplicito, usa null o ometti l'elemento.
- Ignora conferme isolate, saluti, ringraziamenti, messaggi sociali e placeholder media.
- Non trasformare "si", "ok", "no", "grazie", "perfetto", "top" in decisioni o informazioni se sono isolati.
- Non estrarre "sticker non incluso", "immagine omessa", "video omesso", "audio omesso" o "messaggio eliminato".
- Usa confidence "high" solo per elementi espliciti e operativi.
- Usa confidence "medium" per elementi operativi plausibili ma incompleti.
- Usa confidence "low" per elementi vaghi, sociali o poco verificabili.
- Le categorie sono:
  decisions: decisioni gia' prese, INCLUSE le decisioni condizionali
    (es. "se X non e' pronto entro Y, si rimanda a Z", "si procede solo se ...",
    "altrimenti si sposta a ..."). Una decisione condizionale resta una decisione.
  tasks: cose da fare, con owner/due solo se supportati dal testo.
- Campo "due" dei task: se il messaggio esprime una scadenza o un momento previsto,
  anche in forma relativa ("domani", "entro venerdi'", "stasera", "alle 14",
  "la prossima settimana"), convertilo in data assoluta ISO (YYYY-MM-DD oppure
  YYYY-MM-DDTHH:MM) usando come riferimento il timestamp del messaggio quando
  presente nel testo (prefisso "[...]"). Se il momento non e' calcolabile con
  certezza, lascia null: MAI testo libero in "due".
- Campo "owner" dei task: valorizzalo con il nome quando il compito e' chiaramente
  assegnato a una persona ("Marco deve...", "ci pensa Luca", "lo fa il tecnico X")
  oppure auto-assegnato dall'autore ("lo faccio io", "ci penso io" -> owner = nome
  del mittente se ricavabile dal prefisso del messaggio). Altrimenti null.
  issues: problemi, blocchi, rischi aperti.
  information: fatti rilevanti o aggiornamenti.
  open_questions: domande o punti da chiarire.
- Ignora note esplicitamente non operative o personali (es. marcate "nota non
  operativa", "fuori contesto", promemoria personali/domestici): non trasformarle
  in task o decisioni operative.

Formato obbligatorio:
{
  "decisions": [{"text": "...", "source": "msg N", "confidence": "high", "intent": "...", "context_tags": []}],
  "tasks": [{"text": "...", "owner": null, "due": null, "status": "open", "source": "msg N", "confidence": "high", "intent": "...", "context_tags": []}],
  "issues": [{"text": "...", "source": "msg N", "confidence": "high", "intent": "...", "context_tags": []}],
  "information": [{"text": "...", "source": "msg N", "confidence": "medium", "intent": "...", "context_tags": []}],
  "open_questions": [{"text": "...", "source": "msg N", "confidence": "medium", "intent": "...", "context_tags": []}]
}
""".strip()
    user_message = f"Messaggi:\n{numbered}"
    return system_prompt, user_message


_AUG_TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]+", re.IGNORECASE)


def _aug_tokens(text: str) -> set[str]:
    return {t for t in _AUG_TOKEN_RE.findall((text or "").lower()) if len(t) >= 3}


def _augment_conditional_decisions(
    state: OperationalState,
    messages: list[str],
    source_meta: dict[str, Any] | None,
    project_id: str = "",
) -> None:
    """Deterministic safety net: ensure conditional operational decisions present
    in the raw messages are captured even if the LLM missed them. Generic and
    conservative — only fires on an explicit conditional-decision pattern, skips
    questions and non-operational notes, and de-duplicates against what already
    exists. Mutates `state.decisions` in place."""
    existing_tokens = [_aug_tokens(d.text) for d in state.decisions]
    for message in messages:
        # Drop a leading "[timestamp] sender:" prefix added by the live event
        # formatter, so the decision text stays clean. No-op for bare messages.
        text = re.sub(r"^\[[^\]]*\]\s*[^:]{0,40}:\s*", "", message).strip()
        if not text or not is_conditional_decision(text):
            continue
        if text.endswith("?"):
            log("OPERATIONAL_CONDITIONAL_DECISION_SKIPPED", project_id=project_id, reason="question")
            continue
        if is_non_operational_note(text):
            log("OPERATIONAL_CONDITIONAL_DECISION_SKIPPED", project_id=project_id, reason="non_operational")
            continue
        tokens = _aug_tokens(text)
        if not tokens:
            continue
        # Skip if a decision with strong overlap already exists (LLM already got it).
        if any(len(tokens & ex) >= max(2, len(tokens) // 2) for ex in existing_tokens):
            log("OPERATIONAL_CONDITIONAL_DECISION_SKIPPED", project_id=project_id, reason="duplicate")
            continue
        decision_id = _stable_id("dec", text, text[:120])
        data: dict[str, Any] = {
            "text": text,
            "source": text[:120],
            "id": decision_id,
            "confidence": "medium",
            "intent": "decisione condizionale",
        }
        if source_meta:
            for key, value in source_meta.items():
                data.setdefault(key, value)
        state.decisions.append(Decision(**data))
        existing_tokens.append(tokens)
        log(
            "OPERATIONAL_CONDITIONAL_DECISION_CREATED",
            project_id=project_id,
            decision_id=decision_id,
            source="safety_net",
        )


async def extract_state(
    messages: list[str],
    source_event: OperationalEvent | None = None,
    nearby_messages: list[str] | None = None,
) -> OperationalState:
    clean_messages = [
        m.strip()
        for m in messages
        if isinstance(m, str) and m.strip() and not is_noise_text(m)
    ]
    if not clean_messages:
        return OperationalState()

    prompt, user_message = _build_prompt(clean_messages)
    source_meta = _source_metadata(clean_messages, source_event, nearby_messages)
    log("OPERATIONAL_MEMORY_EXTRACT_START", messages=len(clean_messages))
    raw = await llm_service._call_model(
        LLM_DEFAULT_MODEL,
        prompt,
        user_message,
        user_id="operational-memory",
        route="operational_memory",
    )
    if not raw:
        raise OperationalMemoryExtractionError("Extractor returned an empty response")

    state = _parse_state(raw, source_meta)
    project_id = source_event.project_id if source_event is not None else ""
    _augment_conditional_decisions(state, clean_messages, source_meta, project_id=project_id)
    log(
        "OPERATIONAL_MEMORY_EXTRACT_OK",
        decisions=len(state.decisions),
        tasks=len(state.tasks),
        issues=len(state.issues),
        information=len(state.information),
        open_questions=len(state.open_questions),
    )
    return state
