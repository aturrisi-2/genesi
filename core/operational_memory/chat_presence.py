"""FASE 7 — Silent Chat Presence.

Genesi listens to every message, stores it, and updates the operational memory
— always, silently. It produces a visible chat reply ONLY when explicitly
invoked (see invocation_router). When it does reply, the answer is a compact,
mobile-readable payload (table + short synthesis + actions + a link to the full
downloadable report) — never a wall of text.

Generic and multimodal: text and attachments (image/pdf/document) both feed the
memory. No chat/platform/profession token is hardcoded; no LLM decides when to
speak."""

from __future__ import annotations

import asyncio
import re
from typing import Awaitable, Callable, Optional

from core.log import log
from core.operational_memory.incremental_rebuild import incremental_rebuild
from core.operational_memory.invocation_router import is_invoked
from core.operational_memory.models import (
    ChatMessage,
    ChatReply,
    InvocationConfig,
    OperationalBriefing,
    OperationalEvent,
    OperationalState,
    normalize_event_type,
)
from core.operational_memory.quality import is_non_operational_note
from core.operational_memory.query_engine import (
    answer_query,
    build_briefing,
    classify_query_intent,
    command_status_line,
    open_issues,
)
from core.operational_memory.report_store import save_report
from core.operational_memory.state_store import load_state
from core.operational_memory.watcher_engine import ingest_event, process_pending_events


Updater = Callable[[ChatMessage], Awaitable[None]]
_PROJECT_LOCKS: dict[str, asyncio.Lock] = {}


def _project_lock(project_id: str) -> asyncio.Lock:
    lock = _PROJECT_LOCKS.get(project_id)
    if lock is None:
        lock = asyncio.Lock()
        _PROJECT_LOCKS[project_id] = lock
    return lock


def _weather_period_label(query: str) -> str:
    lowered = (query or "").lower()
    if "dopodomani" in lowered:
        return "dopodomani"
    if "domani" in lowered:
        return "domani"
    if "stasera" in lowered:
        return "stasera"
    if "oggi" in lowered:
        return "oggi"
    return ""


def _naturalize_weather_reply(raw: str, query: str) -> str:
    """Turn the provider's compact forecast table into a colleague-like reply."""
    text = (raw or "").strip()
    if not text.startswith("Previsioni per"):
        return text

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    city_match = re.match(r"Previsioni per\s+(.+?):$", lines[0]) if lines else None
    city = city_match.group(1) if city_match else "la città indicata"
    forecast_lines = lines[1:]
    period = _weather_period_label(query)

    if period in {"oggi", "stasera"} and forecast_lines:
        selected = forecast_lines[0]
    elif period == "domani" and forecast_lines:
        selected = forecast_lines[min(1, len(forecast_lines) - 1)]
    elif period == "dopodomani" and forecast_lines:
        selected = forecast_lines[min(2, len(forecast_lines) - 1)]
    else:
        selected = ""

    detail = re.match(r"^(.+?):\s*(.+?),\s*(-?\d+)°C\s*/\s*(-?\d+)°C$", selected)
    if detail:
        description = detail.group(2).strip().lower()
        low, high = int(detail.group(3)), int(detail.group(4))
        when = period or detail.group(1).strip()
        asks_outdoor_work = bool(re.search(
            r"\b(lavor\w*|attivit[aà]|oper\w*)\b.*\b(sole|aperto|esterno|fuori)\b"
            r"|\b(sole|aperto|esterno|fuori)\b.*\b(lavor\w*|attivit[aà]|oper\w*)\b",
            query,
            re.IGNORECASE,
        ))
        if asks_outdoor_work:
            if any(word in description for word in ("temporale", "pioggia", "neve", "grandine")):
                return (
                    f"Io eviterei di programmare lavoro esposto per {when}: a {city} sono previste "
                    f"{description}, con temperature tra {low} e {high} °C. "
                    "Meglio valutare attività riparate e confermare sul posto secondo le procedure di sicurezza."
                )
            if high >= 32:
                return (
                    f"Si può valutare, ma con prudenza: per {when} a {city} sono previsti {description} "
                    f"e fino a {high} °C. Eviterei le ore più calde e organizzerei ombra, acqua e pause; "
                    "restano comunque valide le procedure di sicurezza dell'attività."
                )
            return (
                f"Direi che il meteo lo permette: per {when} a {city} sono previsti {description}, "
                f"con temperature tra {low} e {high} °C. Per lavorare al sole terrei comunque "
                "acqua, pause e procedure di sicurezza come riferimento."
            )
        temperatures = (
            f"temperature intorno ai {low} °C"
            if low == high
            else f"temperature tra {low} e {high} °C"
        )
        return f"Per {when} a {city}, le previsioni indicano {description}, con {temperatures}."

    # Multi-day requests remain scan-friendly but get a conversational lead-in.
    bullets = "\n".join(f"• {line}" for line in forecast_lines)
    return f"Certo, per {city} la situazione prevista è questa:\n{bullets}" if bullets else text


def _event_from_message(message: ChatMessage) -> OperationalEvent:
    event = OperationalEvent(
        event_id=message.message_id,
        project_id=message.project_id,
        source=message.source or "chat",
        sender=message.sender or "",
        content=message.text or "",
    )
    if message.timestamp:
        event.timestamp = message.timestamp
    if message.attachments:
        attachment = message.attachments[0]
        # Map to a VALID OperationalEvent.type (never 'unknown' → no validation
        # error). The raw type is preserved in attachment_type/metadata.
        event.type = normalize_event_type(attachment.type)
        event.attachment_path = attachment.path
        event.attachment_type = attachment.type
        if attachment.extracted_text:
            event.extracted_text = attachment.extracted_text
        if attachment.metadata:
            event.attachment_metadata = dict(attachment.metadata)
    # Explicit reply/quoted binding (platform-independent). The parent event id is
    # the replied/quoted message id (event_id == message_id). Any inline parent
    # snapshot is kept as a fallback context until/unless the parent event is found.
    if message.reply_to_id:
        event.parent_event_id = message.reply_to_id
        event.reply_relation = "reply_to"
        inline = "\n".join(p for p in (message.parent_text, message.parent_attachment_summary) if (p or "").strip())
        if inline.strip():
            event.parent_context = inline.strip()
    return event


async def _silent_update_unlocked(message: ChatMessage, rebuild: bool = True) -> None:
    """Listen + store + update memory. Never returns anything to the chat."""
    event = _event_from_message(message)
    if event.parent_event_id:
        # Strong binding: replied/quoted parent (explicit). Read-only lookup, never
        # re-ingests the parent, never raises. UNCHANGED behaviour.
        from core.operational_memory.context_binding import resolve_parent_context
        await resolve_parent_context(event, message.project_id)
    else:
        # Secondary, gated strategy (T-A4.1): infer a contextual parent when there
        # is no explicit reply. No-op unless OPERATIONAL_CONTEXT_INFERENCE_ENABLED →
        # with the flag OFF behaviour is identical to today.
        from core.operational_memory.context_binding import infer_parent_context, infer_answer_binding
        await infer_parent_context(event, message.project_id)
        if not event.parent_event_id:
            # Semantic answer binding: a short availability/location reply gets linked
            # to the single recent open issue/media (information/mitigation), without
            # resolving it. Tightly constrained + fail-closed; own flag (default on).
            await infer_answer_binding(event, message.project_id)
    _stored, created = await ingest_event(event)
    log(
        "OPERATIONAL_SILENT_INGEST",
        project_id=message.project_id,
        message_id=message.message_id,
        created=created,
        source=message.source,
    )
    if not created:
        return  # idempotent: already seen, no duplicate processing
    await process_pending_events(message.project_id, rebuild_threads=False)
    if rebuild:
        await incremental_rebuild(
            message.project_id,
            relation_window_days=21,
            relation_max_candidates_per_thread=40,
        )


async def silent_update(message: ChatMessage, rebuild: bool = True) -> None:
    """Serialize a project's read-modify-write pipeline and ACK only on finish."""
    async with _project_lock(message.project_id):
        await _silent_update_unlocked(message, rebuild=rebuild)


async def _flush_project_unlocked(project_id: str, rebuild: bool = True) -> None:
    """Update operational memory from already-ingested events WITHOUT adding a new
    event. Used on pure invocations so the query text itself is never stored as a
    project item, while the reply still reflects the latest rebuilt state."""
    await process_pending_events(project_id, rebuild_threads=False)
    if rebuild:
        await incremental_rebuild(
            project_id,
            relation_window_days=21,
            relation_max_candidates_per_thread=40,
        )


async def flush_project(project_id: str, rebuild: bool = True) -> None:
    async with _project_lock(project_id):
        await _flush_project_unlocked(project_id, rebuild=rebuild)


def _compact_table(state: OperationalState) -> str:
    briefing = build_briefing(state)
    lines = ["| Categoria | N |", "| --- | ---: |"]
    for row in briefing.rows:
        if row.count:
            lines.append(f"| {row.label} | {row.count} |")
    return "\n".join(lines)


def _mobile_card(briefing: OperationalBriefing) -> str:
    """Bullet-list card for Telegram/mobile. Active rows only, no pipe tables."""
    lines = []
    for row in briefing.rows:
        if row.active:
            lines.append(f"• {row.label}: {row.count}")
    return "\n".join(lines)


def _synthesis_lines(briefing: OperationalBriefing) -> list[str]:
    """Structured bullet lines for the synthesis section (mobile-readable)."""
    by_key = {r.key: r for r in briefing.rows}

    ot = (by_key.get("open_tasks") or _zero()).count
    oi = (by_key.get("open_issues") or _zero()).count
    ad = (by_key.get("active_decisions") or _zero()).count
    ri_c = (by_key.get("reopened_issues") or _zero()).count
    att_c = (by_key.get("attention") or _zero()).count
    ch_c = (by_key.get("changes") or _zero()).count
    res_c = (by_key.get("resolved_issues") or _zero()).count
    sup_c = (by_key.get("superseded_items") or _zero()).count

    risk_parts: list[str] = []
    if ri_c:
        risk_parts.append(f"{ri_c} problemi riaperti")
    if oi:
        risk_parts.append(f"{oi} problemi aperti")
    if att_c:
        risk_parts.append(f"{att_c} elementi da attenzionare")

    excl_parts: list[str] = []
    if res_c:
        excl_parts.append(f"{res_c} problemi risolti")
    if sup_c:
        excl_parts.append(f"{sup_c} elementi superati")

    action = briefing.recommended_action
    if action and action[0].isupper():
        action = action[0].lower() + action[1:]

    return [
        f"• Stato: {ot} task aperti, {oi} problemi aperti, {ad} decisioni attive",
        f"• Attenzione: {', '.join(risk_parts) if risk_parts else 'nessun rischio operativo evidente'}",
        f"• Cambiamenti: {ch_c} dal precedente snapshot",
        f"• Esclusioni: {', '.join(excl_parts) + ' esclusi' if excl_parts else 'nessun elemento da escludere'}",
        f"• Azione consigliata: {action}",
    ]


# Category → human label for the focused "what remains open" answer. Generic.
_OPEN_GROUP_LABELS: list[tuple[str, str]] = [
    ("issue", "Problemi aperti"),
    ("task", "Task aperti"),
    ("question", "Domande aperte"),
]


def _grouped_open_lines(items: list) -> list[str]:
    """Group the open items by category into labelled sections so the reply is a
    specific list (problemi / task / domande), not just a number. Generic."""
    lines: list[str] = []
    for category, label in _OPEN_GROUP_LABELS:
        group = [it for it in items if it.category == category]
        if not group:
            continue
        lines.append(f"{label}:")
        for it in group[:5]:
            lines.append(f"- {it.text}")
        if len(group) > 5:
            lines.append(f"- … e altri {len(group) - 5}")
        lines.append("")
    return lines


class _ZeroRow:
    count = 0


def _zero() -> _ZeroRow:
    return _ZeroRow()


def _render_briefing_card(briefing: OperationalBriefing) -> str:
    """The general '📌 Quadro operativo' card — only for briefing/digest.
    NOTE (B9 contract): kept in the legacy shared format because the Telegram
    renderer derives bold headings and focus links from the 📌/🧭/• markers —
    restyling it is a dedicated step (B9.1), not a rendering-only patch."""
    parts = [
        "📌 Quadro operativo",
        "",
        _mobile_card(briefing),
        "",
        "🧭 Sintesi operativa",
        "",
        *_synthesis_lines(briefing),
    ]
    # report_url is NOT included in the text — the Telegram bridge sends it as an
    # inline button so the URL does not clutter the message body.
    return "\n".join(parts).strip()


def _fmt_due(due_iso: str) -> str:
    try:
        from datetime import datetime
        d = datetime.fromisoformat(due_iso[:10])
        return d.strftime("%-d/%-m")
    except Exception:
        return due_iso[:10]


def _render_open_tasks_reply(result) -> tuple[str, list[str]]:
    """Focused, filtered view for 'cosa manca?' — shows owner and due when
    present; suppressed for low-value/media/meta tasks (already filtered by
    open_tasks()). No status clutter, no report link."""
    evidence: list[str] = []
    if not result.items:
        return "Non risultano mancanze operative.", evidence
    lines = ["Da quello che vedo, restano da seguire questi punti:"]
    for i, it in enumerate(result.items[:5], 1):
        parts = [it.text]
        if it.owner:
            parts.append(f"→ {it.owner}")
        if it.due:
            parts.append(f"(entro {_fmt_due(it.due)})")
        lines.append(f"{i}. {' '.join(parts)}")
        evidence.extend(it.evidence_event_ids[:1])
    if result.count > 5:
        lines.append(f"… e altri {result.count - 5}.")
    return "\n".join(lines).strip(), evidence


def _render_focused_reply(result) -> tuple[str, list[str]]:
    """Specific list for a focused query — NEVER the general card."""
    evidence: list[str] = []
    intent = result.intent
    if intent == "open_tasks":
        return _render_open_tasks_reply(result)
    if intent == "attention":
        return _render_attention_reply(result)
    if intent == "open_issues":
        if not result.items:
            return "Nessun problema aperto.", evidence
        items = sorted(result.items, key=lambda it: (it.status != "reopened", it.text))
        lines = ["Problemi aperti:", "Da quello che vedo, questi sono i punti da tenere d'occhio:"]
        for i, it in enumerate(items[:5], 1):
            flag = " [riaperto]" if it.status == "reopened" else ""
            lines.append(f"{i}. {it.text}{flag}")
            evidence.extend(it.evidence_event_ids[:1])
        if result.count > 5:
            lines.append(f"Altri {result.count - 5} in coda.")
        reopened = [it for it in items if it.status == "reopened"]
        if reopened:
            lines.append(f"Azione consigliata: ripartire da {reopened[0].text}.")
            lines.append("Te lo segnalo per primo perché risulta riaperto.")
        return "\n".join(lines).strip(), evidence
    if intent == "remaining_open":
        if not result.items:
            return "Non risultano punti aperti rilevanti.", evidence
        lines = ["Punti ancora aperti", ""]
        lines.extend(_grouped_open_lines(result.items))
        for it in result.items:
            evidence.extend(it.evidence_event_ids[:1])
        return "\n".join(lines).strip(), evidence
    if intent == "active_decisions":
        if not result.items:
            return "Non risultano decisioni attive.", evidence
        lines = ["Decisioni attive", ""]
        for it in result.items[:10]:
            lines.append(f"- {it.text}")
            evidence.extend(it.evidence_event_ids[:1])
        return "\n".join(lines).strip(), evidence
    # Generic focused list (open_issues, unanswered, resolved, …).
    if not result.items:
        return (result.summary or "Nessun elemento."), evidence
    lines = [result.summary, ""] if result.summary else []
    for it in result.items[:5]:
        status = f" ({it.status})" if it.status else ""
        lines.append(f"- {it.text}{status}")
        evidence.extend(it.evidence_event_ids[:1])
    if result.count > 5:
        lines.append(f"- … e altri {result.count - 5}")
    return "\n".join(lines).strip(), evidence


def _render_command_open(result) -> tuple[str, list[str]]:
    """Short technical list for the '@genesi aperti' command — grouped open
    items, already capped per category. Never the general card."""
    if not result.items:
        return "Nessun elemento aperto.", []
    lines = _grouped_open_lines(result.items)
    evidence: list[str] = []
    for it in result.items:
        evidence.extend(it.evidence_event_ids[:1])
    return "\n".join(lines).strip(), evidence[:5]


def _render_command_report(report_url: str) -> str:
    """Short technical report pointer for the '@genesi report' command — the
    link if available, never an inline-generated long report."""
    if report_url:
        return f"Report operativo: {report_url}"
    return "Report operativo disponibile (nessun link configurato)."


def _non_operational_notes(state: OperationalState) -> list[str]:
    """Items explicitly framed as non-operational, kept out of the operational
    picture but surfaceable when the user asks something off-focus. Generic."""
    notes: list[str] = []
    seen: set[str] = set()
    for field_name in ("tasks", "issues", "decisions", "information", "open_questions"):
        for item in getattr(state, field_name):
            if is_non_operational_note(item.text) and item.text not in seen:
                seen.add(item.text)
                notes.append(item.text)
    return notes


def _n(count: int, singular: str, plural: str) -> str:
    """'1 task aperto' / '3 task aperti' — correct singular/plural phrasing."""
    return f"{count} {singular if count == 1 else plural}"


def _render_team_brief(state: OperationalState, briefing: OperationalBriefing, result) -> str:
    """Compact operational draft for 'message to the team' style requests.
    Plain professional text: no emoji, no raw dump. Always labelled as a draft —
    the operational layer NEVER sends messages on its own."""
    by_key = {r.key: r for r in briefing.rows}
    ot = (by_key.get("open_tasks") or _zero()).count
    oi = (by_key.get("open_issues") or _zero()).count
    ad = (by_key.get("active_decisions") or _zero()).count

    lines = [
        "Bozza messaggio operativo (non inviata):",
        "",
        "Situazione: "
        f"{_n(ot, 'task aperto', 'task aperti')}, "
        f"{_n(oi, 'problema aperto', 'problemi aperti')}, "
        f"{_n(ad, 'decisione attiva', 'decisioni attive')}.",
    ]
    if result.items:
        lines.append("Priorità:")
        for it in result.items[:5]:
            flag = " [riaperto]" if it.status == "reopened" else ""
            due = f" (entro {_fmt_due(it.due)})" if it.due else ""
            lines.append(f"- {it.text}{flag}{due}")
        if len(result.items) > 5:
            lines.append(f"- … e altri {len(result.items) - 5}")
    else:
        lines.append("Priorità: nessun elemento critico aperto.")
    action = briefing.recommended_action
    if action:
        lines.append(f"Prossima azione: {action}")
    lines.append("Richiesta operativa: aggiornare lo stato dei punti sopra o segnalare eventuali blocchi.")
    lines.append("Prossimo aggiornamento: al prossimo cambiamento rilevante.")
    return "\n".join(lines).strip()


def _render_attention_reply(result) -> tuple[str, list[str]]:
    """Site-manager style priority list: numbered priorities (max 5, already
    priority-sorted), main risk when something reopened, next check pointer.
    No emoji, no report link, never a long dump."""
    evidence: list[str] = []
    if not result.items:
        return "Nessuna priorità aperta al momento.", evidence
    lines = ["Priorità operative:", "Guardando il quadro, io partirei da questi punti:"]
    for i, it in enumerate(result.items[:5], 1):
        flag = " [riaperto]" if it.status == "reopened" else ""
        due = f" (entro {_fmt_due(it.due)})" if it.due else ""
        lines.append(f"{i}. {it.text}{flag}{due}")
        evidence.extend(it.evidence_event_ids[:1])
    if result.count > 5:
        lines.append(f"Altri {result.count - 5} elementi in coda.")
    reopened = [it for it in result.items if it.status == "reopened"]
    if reopened:
        lines.append(f"Rischio principale: {reopened[0].text} (riaperto).")
    lines.append("Prossima verifica: partire dal punto 1.")
    lines.append("Poi aggiornerei gli altri punti in ordine, così vediamo subito cosa si sblocca.")
    return "\n".join(lines).strip(), evidence


def _render_unknown_reply(state: OperationalState) -> str:
    """Conservative textual fallback for off-focus queries — NEVER the card,
    no empathic/LLM dependency. Distinguishes operational context from side notes."""
    lines = [
        "Su questo non ho ancora una risposta affidabile nei dati disponibili. "
        "Se mi dai un riferimento in più, provo a ricostruirla con te."
    ]
    notes = _non_operational_notes(state)
    if notes:
        lines.append("")
        lines.append("Note non operative registrate (fuori dal quadro di progetto):")
        for text in notes[:5]:
            lines.append(f"- {text}")
    return "\n".join(lines).strip()


def build_chat_reply(
    state: OperationalState,
    query: str,
    report_id: str = "",
    report_url: str = "",
    invoked_by: str = "",
) -> ChatReply:
    """Pure: turn the current state + the asked query into a compact chat reply.

    Rendering is intent-aware:
      * briefing/digest → the general '📌 Quadro operativo' card + synthesis;
      * focused queries (remaining_open, active_decisions, open_*, …) → ONLY the
        specific list of matching items — never the general card;
      * unknown → a conservative textual reply, never the general card.
    """
    briefing = build_briefing(state)
    result = answer_query(state, query)
    intent = result.intent

    evidence: list[str] = []
    if intent == "decision_guard":
        reply_markdown = result.summary
        synthesis = result.summary
    elif intent == "cmd_stato":
        reply_markdown = command_status_line(state)
        synthesis = result.summary
    elif intent == "cmd_aperti":
        reply_markdown, evidence = _render_command_open(result)
        synthesis = result.summary
    elif intent == "cmd_report":
        reply_markdown = _render_command_report(report_url)
        synthesis = result.summary
    elif intent in {"reporter_stats", "weather", "issue_media", "assistant_identity"}:
        reply_markdown = result.summary
        synthesis = result.summary
    elif intent in {"briefing", "digest"}:
        reply_markdown = _render_briefing_card(briefing)
        synthesis = briefing.synthesis
    elif intent == "team_brief":
        reply_markdown = _render_team_brief(state, briefing, result)
        synthesis = briefing.synthesis
        evidence = [eid for it in result.items[:5] for eid in it.evidence_event_ids[:1]]
    elif intent == "unknown":
        reply_markdown = _render_unknown_reply(state)
        synthesis = result.summary
    else:
        reply_markdown, evidence = _render_focused_reply(result)
        synthesis = result.summary or briefing.synthesis

    return ChatReply(
        project_id=state.project_id or "",
        invoked_by=invoked_by,
        intent=intent,
        table_markdown=_compact_table(state),
        synthesis=synthesis,
        actions=[briefing.recommended_action],
        evidence_event_ids=evidence,
        report_id=report_id,
        report_url=report_url,
        reply_markdown=reply_markdown,
    )


def _report_url(project_id: str, report_id: str, base_url: str = "") -> str:
    path = f"/api/operational/projects/{project_id}/reports/{report_id}/view"
    base = (base_url or "").rstrip("/")
    return f"{base}{path}" if base else path


async def build_operational_reply(
    project_id: str,
    query: str,
    report_base_url: str = "",
    invoked_by: str = "",
    save: bool = True,
) -> ChatReply:
    """Service-layer entry point: build the operational chat reply for a query
    over the current state, optionally persisting the full report and linking it.

    Transport bridges (e.g. Telegram) call this instead of re-implementing the
    operational orchestration. No empathic logic, no LLM."""
    state = await load_state(project_id)
    intent = classify_query_intent(query)

    if intent == "issue_media":
        from pathlib import Path
        from core.operational_memory.event_store import list_events

        events = await list_events(project_id)
        event_by_id = {event.event_id: event for event in events}
        found: list[tuple[str, str, str, str]] = []
        seen_media: set[str] = set()
        for item in open_issues(state):
            for event_id in item.evidence_event_ids:
                event = event_by_id.get(event_id)
                media_path = getattr(event, "attachment_path", None) if event else None
                media_type = str(
                    getattr(event, "attachment_type", None)
                    or getattr(event, "type", "")
                    or ""
                ).lower() if event else ""
                if not media_path or "image" not in media_type:
                    continue
                media_id = Path(media_path).name
                if not media_id or media_id in seen_media:
                    continue
                seen_media.add(media_id)
                base = (report_base_url or "").rstrip("/")
                path = f"/operational-report/{project_id}/media/{media_id}/thumbnail"
                found.append((item.text, f"{base}{path}" if base else path, event_id, media_id))
                break
            if len(found) >= 5:
                break

        media_out: list[dict] = []
        if found:
            evidence = [event_id for _t, _u, event_id, _m in found]
            media_out = [
                {"media_id": media_id, "caption": text, "url": url}
                for text, url, _e, media_id in found
            ]
            n = len(found)
            if n == 1:
                body = ("Sì, ce l'ho: per uno dei problemi aperti c'è la foto — "
                        "te la mando qui sotto con il suo contesto.")
            else:
                body = (f"Sì, le ho: per {n} dei problemi aperti c'è una foto — "
                        "te le mando qui sotto, ognuna con il suo problema.")
            body += ("\nPer gli altri punti aperti non ho immagini collegate in modo "
                     "affidabile, quindi preferisco non mostrarti foto fuori contesto.")
        else:
            body = (
                "Ho controllato: al momento non ho foto collegate in modo affidabile "
                "ai problemi ancora aperti. Appena ne arriva una la aggancio e te la faccio vedere."
            )
            evidence = []
        return ChatReply(
            project_id=project_id,
            invoked_by=invoked_by,
            intent=intent,
            synthesis=body,
            reply_markdown=body,
            evidence_event_ids=evidence,
            media=media_out,
        )

    if intent == "weather":
        # Reuse the same real provider as the web app and the ordinary group
        # pipeline. Never assume a city: ask naturally, then let the transport
        # carry the short city answer back as a pure weather follow-up.
        from core.location_resolver import extract_city_from_message
        from core.tool_services import tool_service

        city = extract_city_from_message(query)
        if not city:
            period = _weather_period_label(query)
            period_suffix = f" per {period}" if period else ""
            body = f"Volentieri. Di quale città vuoi sapere il meteo{period_suffix}?"
            return ChatReply(
                project_id=project_id,
                invoked_by=invoked_by,
                intent=intent,
                synthesis=body,
                reply_markdown=body,
            )

        try:
            body = _naturalize_weather_reply(await tool_service.get_weather(query), query)
        except Exception as exc:
            log("OPERATIONAL_WEATHER_TOOL_ERROR", error=str(exc)[:160])
            body = "In questo momento il servizio meteo non risponde. Riproviamo tra poco."
        return ChatReply(
            project_id=project_id,
            invoked_by=invoked_by,
            intent=intent,
            synthesis=body,
            reply_markdown=body,
        )

    if intent == "assistant_identity":
        body = (
            "Sono Genesi, piacere. Nel Canary sono il vostro collega digitale: "
            "seguo il filo della conversazione, consulto TAB in sola lettura e, quando serve, uso strumenti come il meteo."
        )
        return ChatReply(
            project_id=project_id,
            invoked_by=invoked_by,
            intent=intent,
            synthesis=body,
            reply_markdown=body,
        )

    report_id = ""
    report_url = ""
    if save:
        report = save_report(project_id, build_briefing(state).markdown)
        report_id = report.report_id
        report_url = _report_url(project_id, report_id, report_base_url)
    return build_chat_reply(state, query, report_id=report_id, report_url=report_url, invoked_by=invoked_by)


async def handle_incoming(
    message: ChatMessage,
    config: Optional[InvocationConfig] = None,
    updater: Optional[Updater] = None,
    save_report_on_reply: bool = True,
) -> Optional[ChatReply]:
    """Always ingest + update memory silently. Return a ChatReply ONLY when the
    message explicitly invokes Genesi; otherwise return None (stay silent)."""
    config = config or InvocationConfig()
    update = updater or silent_update

    # 1. Silent listen + memory update — always, for every message.
    await update(message)

    # 2. Explicit invocation gate.
    decision = is_invoked(message.text, config, is_dm=message.is_dm)
    if not decision.respond:
        return None

    # 3. Build the reply from the (now updated) operational state.
    state = await load_state(message.project_id)
    report_id = ""
    report_url = ""
    if save_report_on_reply:
        report = save_report(message.project_id, build_briefing(state).markdown)
        report_id = report.report_id
        report_url = f"/api/operational/projects/{message.project_id}/reports/{report_id}/view"
    return build_chat_reply(
        state,
        decision.query,
        report_id=report_id,
        report_url=report_url,
        invoked_by=message.sender,
    )
