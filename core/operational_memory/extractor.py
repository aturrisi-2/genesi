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
    OperationalQuestion,
    OperationalState,
    OperationalTask,
)


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


def _as_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalize_items(
    raw_items: list[dict[str, Any]],
    model,
    prefix: str,
) -> list[Any]:
    normalized: list[Any] = []
    seen: set[tuple[str, str]] = set()

    for raw in raw_items:
        text = str(raw.get("text") or "").strip()
        source = str(raw.get("source") or "").strip()
        if not text or not source:
            continue

        data = dict(raw)
        data["text"] = text
        data["source"] = source
        data["id"] = str(raw.get("id") or "").strip() or _stable_id(prefix, text, source)

        key = (text.lower(), source.lower())
        if key in seen:
            continue
        seen.add(key)
        normalized.append(model(**data))

    return normalized


def _parse_state(raw_response: str) -> OperationalState:
    try:
        payload = json.loads(_strip_json_fences(raw_response))
    except json.JSONDecodeError as exc:
        raise OperationalMemoryExtractionError(f"Invalid JSON from extractor: {exc}") from exc

    if not isinstance(payload, dict):
        raise OperationalMemoryExtractionError("Extractor response must be a JSON object")

    return OperationalState(
        decisions=_normalize_items(_as_list(payload, "decisions"), Decision, "dec"),
        tasks=_normalize_items(_as_list(payload, "tasks"), OperationalTask, "task"),
        issues=_normalize_items(_as_list(payload, "issues"), Issue, "issue"),
        information=_normalize_items(_as_list(payload, "information"), Information, "info"),
        open_questions=_normalize_items(_as_list(payload, "open_questions"), OperationalQuestion, "question"),
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
- Se un campo non e' esplicito, usa null o ometti l'elemento.
- Le categorie sono:
  decisions: decisioni gia' prese.
  tasks: cose da fare, con owner/due solo se esplicitati.
  issues: problemi, blocchi, rischi aperti.
  information: fatti rilevanti o aggiornamenti.
  open_questions: domande o punti da chiarire.

Formato obbligatorio:
{
  "decisions": [{"text": "...", "source": "msg N"}],
  "tasks": [{"text": "...", "owner": null, "due": null, "status": "open", "source": "msg N"}],
  "issues": [{"text": "...", "source": "msg N"}],
  "information": [{"text": "...", "source": "msg N"}],
  "open_questions": [{"text": "...", "source": "msg N"}]
}
""".strip()
    user_message = f"Messaggi:\n{numbered}"
    return system_prompt, user_message


async def extract_state(messages: list[str]) -> OperationalState:
    clean_messages = [m.strip() for m in messages if isinstance(m, str) and m.strip()]
    if not clean_messages:
        return OperationalState()

    prompt, user_message = _build_prompt(clean_messages)
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

    state = _parse_state(raw)
    log(
        "OPERATIONAL_MEMORY_EXTRACT_OK",
        decisions=len(state.decisions),
        tasks=len(state.tasks),
        issues=len(state.issues),
        information=len(state.information),
        open_questions=len(state.open_questions),
    )
    return state
