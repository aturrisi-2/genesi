"""FASE 5 — Query & Retrieval Layer.

Answer operational questions over the lifecycle state with structured,
deterministic queries (no generative AI). Every answer item carries its
evidence_event_ids and a reason, so results stay explainable and traceable.

Domain-agnostic: queries operate on generic lifecycle statuses and item
metadata only — no profession/site/platform vocabulary, no hardcoded tokens.
The natural-language layer is a thin keyword/regex intent router (IT + EN) that
dispatches to the structured queries; it never invents content."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Callable

from core.operational_memory.context_extractor import expand_level_range, extract_context, normalize_context_token
from core.operational_memory.lifecycle_engine import initial_status, is_active_status
from core.operational_memory.quality import is_low_value_task, is_non_operational_note
from core.operational_memory.models import (
    BriefingRow,
    LifecycleCategory,
    OperationalBriefing,
    OperationalDigest,
    OperationalItem,
    OperationalState,
    OperationalTask,
    QueryAnswerItem,
    QueryResult,
    utc_now_iso,
)


_CATEGORY_FIELDS: list[tuple[LifecycleCategory, str]] = [
    ("task", "tasks"),
    ("issue", "issues"),
    ("decision", "decisions"),
    ("question", "open_questions"),
    ("information", "information"),
]


def _status_of(item: OperationalItem, category: LifecycleCategory) -> str:
    if item.lifecycle is not None:
        return item.lifecycle.current_status
    return initial_status(category, item.text)


def _answer_item(item: OperationalItem, category: LifecycleCategory) -> QueryAnswerItem:
    lifecycle = item.lifecycle
    status = _status_of(item, category)
    evidence = list(lifecycle.evidence_event_ids) if lifecycle else (
        [item.source_event_id] if item.source_event_id else []
    )
    reason = lifecycle.status_reason if lifecycle and lifecycle.status_reason else "stato corrente"
    owner = item.owner if isinstance(item, OperationalTask) else None
    due = item.due if isinstance(item, OperationalTask) else None
    return QueryAnswerItem(
        item_id=item.id,
        category=category,
        status=status,
        text=item.text,
        confidence=lifecycle.confidence if lifecycle else item.confidence,
        evidence_event_ids=evidence,
        reason=reason,
        owner=owner,
        due=due,
        context_area=item.context_area,
        context_system=item.context_system,
        context_level=item.context_level,
        context_location=item.context_location,
        context_tags=list(item.context_tags or []),
    )


def _collect(state: OperationalState, category: LifecycleCategory, predicate: Callable[[str], bool]) -> list[QueryAnswerItem]:
    field_name = dict(_CATEGORY_FIELDS)[category]
    out: list[QueryAnswerItem] = []
    for item in getattr(state, field_name):
        if predicate(_status_of(item, category)):
            out.append(_answer_item(item, category))
    return out


def _operational_only(items: list[QueryAnswerItem]) -> list[QueryAnswerItem]:
    """Drop items explicitly framed as non-operational/personal so they never
    surface as active work nor inflate the active counts."""
    return [it for it in items if not is_non_operational_note(it.text)]


# --------------------------------------------------------------------------- #
# Structured queries
# --------------------------------------------------------------------------- #


def list_items(
    state: OperationalState,
    category: str | None = None,
    status: str | None = None,
) -> list[QueryAnswerItem]:
    """Flat, filterable view of every operational item with its lifecycle
    status + evidence. Generic: filters are plain category/status strings."""
    out: list[QueryAnswerItem] = []
    for cat, _field in _CATEGORY_FIELDS:
        if category and cat != category:
            continue
        for answer in _collect(state, cat, lambda s: True):
            if status and answer.status != status:
                continue
            out.append(answer)
    return out


def open_tasks(state: OperationalState) -> list[QueryAnswerItem]:
    raw = _operational_only(_collect(state, "task", lambda s: is_active_status("task", s)))
    return [it for it in raw if not is_low_value_task(it.text)]


def agenda_tasks(state: OperationalState) -> list[QueryAnswerItem]:
    """Vista agenda: task attivi ordinati per scadenza ("due" ISO) crescente;
    i task senza scadenza in coda, in ordine stabile. Serve alle domande di
    pianificazione ("impegni di oggi", "cosa dobbiamo fare domani") dove
    l'ordine temporale conta più dello stato."""
    return sorted(
        open_tasks(state),
        key=lambda it: (it.due is None, it.due or "", (it.text or "").lower()),
    )


def open_issues(state: OperationalState) -> list[QueryAnswerItem]:
    return _operational_only(_collect(state, "issue", lambda s: is_active_status("issue", s)))


def resolved_issues(state: OperationalState) -> list[QueryAnswerItem]:
    return _collect(state, "issue", lambda s: s == "resolved")


def active_decisions(state: OperationalState) -> list[QueryAnswerItem]:
    return _operational_only(_collect(state, "decision", lambda s: is_active_status("decision", s)))


def unanswered_questions(state: OperationalState) -> list[QueryAnswerItem]:
    return _operational_only(_collect(state, "question", lambda s: s in {"open", "partially_answered"}))


def remaining_open(state: OperationalState) -> list[QueryAnswerItem]:
    """Specific list of what is still open: active issues, then active tasks,
    then unanswered questions. Generic, status-driven, non-operational notes
    already excluded. This is what 'cosa resta aperto?' answers — not a count."""
    out: list[QueryAnswerItem] = []
    out.extend(open_issues(state))
    out.extend(open_tasks(state))
    out.extend(unanswered_questions(state))
    return out


def superseded_items(state: OperationalState) -> list[QueryAnswerItem]:
    out: list[QueryAnswerItem] = []
    for category, _field in _CATEGORY_FIELDS:
        out.extend(_collect(state, category, lambda s: s in {"superseded", "revoked", "cancelled", "expired"}))
    return out


def _attention_rank(it: QueryAnswerItem) -> tuple:
    """Deterministic priority order for attention/team_brief lists (B9 contract):
    reopened > items with a due date (earliest first) > high-confidence open
    issues > tasks without an owner > everything else. No LLM, no domain
    vocabulary."""
    if it.status == "reopened":
        rank = 0
    elif it.due:
        rank = 1
    elif it.category == "issue" and it.confidence == "high":
        rank = 2
    elif it.category == "task" and not it.owner:
        rank = 3
    else:
        rank = 4
    return (rank, it.due or "9999-12-31", it.text)


def attention_items(state: OperationalState) -> list[QueryAnswerItem]:
    """Active items that warrant attention: reopened, mitigated-but-open, or
    high-confidence active issues; plus aging items flagged by the snapshot.
    Sorted by operational priority (reopened > due > critical > rest)."""
    out: list[QueryAnswerItem] = []
    aging_texts: set[str] = set()
    snapshot = state.lifecycle_snapshot
    if snapshot and snapshot.snapshot_delta:
        for label in snapshot.snapshot_delta.aging_attention_items:
            aging_texts.add(label)
    for category, field_name in _CATEGORY_FIELDS:
        for item in getattr(state, field_name):
            status = _status_of(item, category)
            if not is_active_status(category, status):
                continue
            flag = (
                status in {"reopened", "mitigated", "blocked", "partially_answered"}
                or (category == "issue" and item.confidence == "high")
                or f"[{category}] {item.text}" in aging_texts
            )
            if flag:
                out.append(_answer_item(item, category))
    return sorted(_operational_only(out), key=_attention_rank)


def changed_since(state: OperationalState) -> list[QueryAnswerItem]:
    snapshot = state.lifecycle_snapshot
    if snapshot is None or snapshot.snapshot_delta is None:
        return []
    delta = snapshot.snapshot_delta
    out: list[QueryAnswerItem] = []
    seen: set[str] = set()

    def _add(label: str, status: str) -> None:
        if label in seen:
            return
        seen.add(label)
        out.append(QueryAnswerItem(text=label, status=status, reason=f"cambiato dallo snapshot precedente ({status})"))

    for label in delta.newly_completed:
        _add(label, "completed")
    for label in delta.newly_resolved:
        _add(label, "resolved")
    for label in delta.newly_superseded:
        _add(label, "superseded")
    for label in delta.reopened_items:
        _add(label, "reopened")
    for label in delta.newly_opened:
        _add(label, "opened")
    for label in delta.newly_stale:
        _add(label, "stale")
    return out


def build_digest(state: OperationalState) -> OperationalDigest:
    ot = open_tasks(state)
    oi = open_issues(state)
    ri = resolved_issues(state)
    ad = active_decisions(state)
    uq = unanswered_questions(state)
    att = attention_items(state)
    changes = [item.text for item in changed_since(state)]
    headline = (
        f"{len(ot)} task aperti, {len(oi)} problemi aperti, {len(ri)} risolti, "
        f"{len(ad)} decisioni attive, {len(uq)} domande aperte, {len(att)} elementi da attenzionare"
    )
    return OperationalDigest(
        project_id=state.project_id or "",
        generated_at=utc_now_iso(),
        headline=headline,
        open_tasks=ot,
        open_issues=oi,
        resolved_issues=ri,
        active_decisions=ad,
        unanswered_questions=uq,
        attention_items=att,
        recent_changes=changes[:50],
    )


def completed_tasks(state: OperationalState) -> list[QueryAnswerItem]:
    return _collect(state, "task", lambda s: s in {"completed", "verified"})


def answered_questions(state: OperationalState) -> list[QueryAnswerItem]:
    return _collect(state, "question", lambda s: s == "answered")


def reopened_issues(state: OperationalState) -> list[QueryAnswerItem]:
    return _collect(state, "issue", lambda s: s == "reopened")


def superseded_decisions(state: OperationalState) -> list[QueryAnswerItem]:
    return _collect(state, "decision", lambda s: s in {"superseded", "revoked", "expired"})


def stale_items(state: OperationalState) -> list[QueryAnswerItem]:
    out: list[QueryAnswerItem] = []
    for category, _field in _CATEGORY_FIELDS:
        out.extend(_collect(state, category, lambda s: s == "stale"))
    return out


# --------------------------------------------------------------------------- #
# General Operational Briefing (3 levels: table data, synthesis, markdown)
# --------------------------------------------------------------------------- #


def build_briefing(state: OperationalState) -> OperationalBriefing:
    """Structured, generic, adaptive briefing. Separates DATA (rows + synthesis)
    from RENDERING (markdown). Active vs closed are kept apart so resolved /
    superseded items are never reported as active."""
    ot, ct = open_tasks(state), completed_tasks(state)
    oi, ri, repi = open_issues(state), resolved_issues(state), reopened_issues(state)
    ad, sd = active_decisions(state), superseded_decisions(state)
    uq, aq = unanswered_questions(state), answered_questions(state)
    stale, sup, att = stale_items(state), superseded_items(state), attention_items(state)
    changes = [item.text for item in changed_since(state)]

    rows = [
        BriefingRow(key="open_tasks", label="Task aperti", count=len(ot), active=True, items=ot),
        BriefingRow(key="completed_tasks", label="Task completati", count=len(ct), active=False, items=ct),
        BriefingRow(key="open_issues", label="Problemi aperti", count=len(oi), active=True, items=oi),
        BriefingRow(key="resolved_issues", label="Problemi risolti", count=len(ri), active=False, items=ri),
        BriefingRow(key="reopened_issues", label="Problemi riaperti", count=len(repi), active=True, items=repi),
        BriefingRow(key="active_decisions", label="Decisioni attive", count=len(ad), active=True, items=ad),
        BriefingRow(key="superseded_decisions", label="Decisioni superate", count=len(sd), active=False, items=sd),
        BriefingRow(key="open_questions", label="Domande aperte", count=len(uq), active=True, items=uq),
        BriefingRow(key="answered_questions", label="Domande risposte", count=len(aq), active=False, items=aq),
        BriefingRow(key="stale_items", label="Elementi stale/aging", count=len(stale), active=False, items=stale),
        BriefingRow(key="superseded_items", label="Elementi superati (non piu attivi)", count=len(sup), active=False, items=sup),
        BriefingRow(key="changes", label="Cambiamenti dallo snapshot precedente", count=len(changes), active=True,
                    note="; ".join(changes[:5])),
        BriefingRow(key="attention", label="Priorita/Attenzione", count=len(att), active=True, items=att),
    ]

    headline = (
        f"{len(ot)} task aperti, {len(oi)} problemi aperti ({len(repi)} riaperti), "
        f"{len(ri)} risolti, {len(ad)} decisioni attive, {len(uq)} domande aperte, "
        f"{len(att)} da attenzionare"
    )

    risk_bits = []
    if repi:
        risk_bits.append(f"{len(repi)} problemi riaperti")
    if oi:
        risk_bits.append(f"{len(oi)} problemi ancora aperti")
    if att:
        risk_bits.append(f"{len(att)} elementi da attenzionare")
    risks = ", ".join(risk_bits) if risk_bits else "nessun rischio operativo evidente"
    change_phrase = (
        f"Dallo snapshot precedente: {len(changes)} cambiamenti." if changes else "Nessun cambiamento dallo snapshot precedente."
    )
    not_active = (
        f"{len(ri)} problemi risolti e {len(sup)} elementi superati non vanno piu considerati attivi."
        if (ri or sup) else "Nessun elemento risolto o superato da escludere."
    )
    synthesis = (
        f"Stato operativo: {len(ot)} task e {len(oi)} problemi aperti, {len(ad)} decisioni attive. "
        f"Attenzioni principali: {risks}. {change_phrase} {not_active}"
    )

    if repi:
        recommended = ("Affrontare prima il problema riaperto." if len(repi) == 1
                       else f"Affrontare prima i {len(repi)} problemi riaperti.")
    elif att:
        recommended = ("Verificare l'elemento che richiede attenzione." if len(att) == 1
                       else f"Verificare i {len(att)} elementi che richiedono attenzione.")
    elif oi:
        recommended = ("Pianificare la risoluzione del problema aperto." if len(oi) == 1
                       else f"Pianificare la risoluzione dei {len(oi)} problemi aperti.")
    elif ot:
        recommended = ("Avanzare sul task aperto." if len(ot) == 1
                       else f"Avanzare sui {len(ot)} task aperti.")
    else:
        recommended = "Monitorare il prossimo aggiornamento operativo."

    briefing = OperationalBriefing(
        project_id=state.project_id or "",
        generated_at=utc_now_iso(),
        headline=headline,
        rows=rows,
        synthesis=synthesis,
        recommended_action=recommended,
        changes_since_previous=changes[:50],
    )
    briefing.markdown = render_briefing_markdown(briefing)
    return briefing


def _evidence_suffix(item: QueryAnswerItem) -> str:
    return f" [evidenza: {', '.join(item.evidence_event_ids)}]" if item.evidence_event_ids else ""


def _primary_context_parts(it: QueryAnswerItem) -> list[str]:
    """Primary spatial context of an item as ordered, normalised, deduped parts
    [location, system, level]. Stored fields win; when ALL are empty the item
    text is re-scanned (legacy items). Empty result → undetermined context —
    never invented."""
    loc, sys_, lvl = it.context_location, it.context_system, it.context_level
    if not (loc and sys_ and lvl):
        # Fill the MISSING fields from a fresh text scan — stored values (from
        # ingest-time nearby context) always win; the text only completes gaps
        # (legacy items extracted before the extractor learned scala/ranges).
        fresh = extract_context(it.text or "")
        loc = loc or fresh.context_location
        sys_ = sys_ or fresh.context_system
        lvl = fresh.context_level or lvl  # fresh level may carry the full range
    parts: list[str] = []
    seen: set[str] = set()
    for v in (loc, sys_, lvl):
        if not v:
            continue
        canon = normalize_context_token(v)
        if canon and canon not in seen:
            seen.add(canon)
            parts.append(canon)
    return parts


_UNDETERMINED_CTX = "Contesto non determinato"


def group_items_by_context(
    items: list[QueryAnswerItem], max_groups: int = 5,
) -> tuple[list[tuple[str, list[QueryAnswerItem]]], list[QueryAnswerItem]]:
    """Group items by their primary context header ("SCALA 2 / T2 / L3-L7").
    Each item lands in exactly ONE group (its primary context). Returns the
    top `max_groups` groups (largest first, undetermined always last) plus the
    overflow items collapsed by the caller."""
    buckets: dict[str, list[QueryAnswerItem]] = {}
    for it in items:
        parts = _primary_context_parts(it)
        header = " / ".join(parts) if parts else _UNDETERMINED_CTX
        buckets.setdefault(header, []).append(it)
    ordered = sorted(
        buckets.items(),
        key=lambda kv: (
            kv[0] == _UNDETERMINED_CTX,                                # undetermined last
            not any(it.status == "reopened" for it in kv[1]),          # reopened groups first
            -len(kv[1]),
            kv[0],
        ),
    )
    return ordered[:max_groups], [it for _, grp in ordered[max_groups:] for it in grp]


def _render_context_criticalities(briefing: OperationalBriefing) -> list[str]:
    """'## Criticità per contesto' section: ACTIVE issues grouped by primary
    spatial context. Skipped entirely when there are no active issues."""
    by_key = {r.key: r for r in briefing.rows}
    row = by_key.get("open_issues")
    items = list(row.items) if row and row.items else []
    if not items:
        return []
    groups, overflow = group_items_by_context(items)
    lines = ["## Criticità per contesto", ""]
    for header, grp in groups:
        lines.append(f"### {header}")
        for it in grp[:10]:
            flag = " [riaperto]" if it.status == "reopened" else ""
            extra_tags = [
                normalize_context_token(t) for t in (it.context_tags or [])
            ]
            primary = set(_primary_context_parts(it))
            detail = [t for t in dict.fromkeys(extra_tags) if t and t not in primary][:2]
            suffix = f" (anche: {', '.join(detail)})" if detail else ""
            lines.append(f"- {it.text}{flag}{suffix}")
        lines.append("")
    if overflow:
        lines.append(f"Altri contesti: {len(overflow)} elementi.")
        lines.append("")
    return lines


def render_briefing_markdown(briefing: OperationalBriefing) -> str:
    """Pure renderer: turn briefing DATA into an exportable Markdown report."""
    lines = [
        f"# Briefing operativo — {briefing.project_id}",
        "",
        f"Generato: {briefing.generated_at}",
        "",
        "## Quadro sintetico",
        "",
        "| Categoria | N |",
        "| --- | ---: |",
    ]
    for row in briefing.rows:
        lines.append(f"| {row.label} | {row.count} |")
    lines.extend([
        "",
        "## Sintesi",
        "",
        briefing.synthesis,
        "",
        f"**Azione consigliata:** {briefing.recommended_action}",
        "",
    ])
    lines.extend(_render_context_criticalities(briefing))
    lines.extend([
        "## Dettaglio",
        "",
    ])
    for row in briefing.rows:
        if not row.items and not row.note:
            continue
        tag = "ATTIVO" if row.active else "CHIUSO/NON ATTIVO"
        lines.append(f"### {row.label} ({row.count}) — {tag}")
        if row.note:
            lines.append(f"- {row.note}")
        for item in row.items[:30]:
            status = f" ({item.status})" if item.status else ""
            lines.append(f"- {item.text}{status}{_evidence_suffix(item)}")
        lines.append("")
    return "\n".join(lines).strip()


# --------------------------------------------------------------------------- #
# Natural-language intent routing (keyword/regex, no LLM)
# --------------------------------------------------------------------------- #

# Ordered: more specific intents first. Patterns are generic IT + EN.
_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    # B10.1 decision guard — MUST be first: opinion/decision requests ("secondo
    # te", "conviene", "possiamo decidere/chiudere", "che ne dici") would
    # otherwise be captured by lexical task/issue patterns (e.g. "attività").
    # Genesi never decides for the team; the reply states the limit and offers
    # the relevant read-only views.
    ("decision_guard", re.compile(
        r"secondo\s+te|conviene\b|possiamo\s+decid\w*|possiamo\s+chiuder\w*|che\s+ne\s+dici",
        re.IGNORECASE)),
    # Technical command shortcuts — exact-anchored single tokens (the invocation
    # router has already stripped the "@genesi"/name prefix). Highest precedence
    # so the bare command words win over the natural-language patterns; the exact
    # anchoring means natural phrasing ("stato del progetto", "fammi il report")
    # still falls through to digest/briefing and is unaffected.
    ("cmd_stato", re.compile(r"^\s*stato\s*$", re.IGNORECASE)),
    ("cmd_aperti", re.compile(r"^\s*aperti\s*$", re.IGNORECASE)),
    ("cmd_report", re.compile(
        r"^\s*report(\s+operativ\w*)?\s*[?!.]?\s*$"
        r"|\b(manda\w*|invia\w*)\s+(il\s+|un\s+)?report\b",
        re.IGNORECASE)),
    # Conversational read-only questions that need structured data beyond the
    # generic issue list. Keep these before open_issues so the nouns "problemi"
    # and "foto" do not collapse to the old list intent.
    ("issue_media", re.compile(
        r"\b(foto|immagin\w*|media|allegat\w*)\b.*\b(problem\w*|critic\w*|guast\w*|anomal\w*)\b"
        r"|\b(problem\w*|critic\w*|guast\w*|anomal\w*)\b.*\b(foto|immagin\w*|media|allegat\w*)\b",
        re.IGNORECASE)),
    ("reporter_stats", re.compile(
        r"\b(chi|quale\s+(utente|persona|collega)|quali\s+(utenti|persone|colleghi))\b"
        r".*\b(segnalat\w*|riportat\w*|apert\w*|inserit\w*)\b.*\b(problem\w*|critic\w*|guast\w*|anomal\w*)\b"
        r"|\b(problem\w*|critic\w*|guast\w*|anomal\w*)\b.*\b(segnalat\w*|riportat\w*)\b.*\b(chi|utente|persona)\b",
        re.IGNORECASE)),
    ("assistant_identity", re.compile(
        r"^\s*(chi\s+sei|tu\s+chi\s+sei|come\s+ti\s+chiami|"
        r"qual[e']?\s+[eè]\s+il\s+tuo\s+nome|cosa\s+sei)\s*[?!.]*\s*$",
        re.IGNORECASE)),
    ("weather", re.compile(
        r"\b(meteo|temperatura|piov\w*|nevic\w*|prevision\w*)\b"
        r"|\b(che|com'?[eè]|come\s+[eè])\s+(il\s+)?tempo\b"
        r"|\btempo\s+(oggi|domani|fuori|a\b|in\b)"
        r"|\b(c'?[eè]|ci\s+sar[aà])\s+(il\s+)?sole\b",
        re.IGNORECASE)),
    # Natural-language status/update invocations → same concise inline status as
    # the bare 'stato' command (pure read-only, never ingested, no link/emoji
    # fallback). Placed before briefing/digest so status phrasing resolves to the
    # inline summary. Does NOT match the working query intents (problemi aperti /
    # cosa manca / decisioni prese / fammi il report).
    ("cmd_stato", re.compile(
        r"(qual[e'\s]*\s*[eè]\s+(lo\s+)?stato"
        r"|che\s+stato\b"
        r"|\bstato\s+(attuale|lavori|attivit[aà])\b"
        r"|a\s+che\s+punto\s+(siamo|stiamo|stanno)"
        r"|come\s+(va|siamo\s+messi|procede|stiamo)\b"
        r"|aggiorna(mi)?\s+(lo\s+|sullo\s+|su\s+)?stato\b"
        r"|dammi\s+(lo\s+)?stato\b"
        r"|qual[e'\s]*\s*[eè]\s+la\s+situazione)",
        re.IGNORECASE)),
    # Specific "what is still open" → focused item list, NOT the aggregate briefing.
    # Must precede the briefing pattern so it wins on "cosa resta aperto?".
    ("remaining_open", re.compile(
        r"(cosa\s+resta\s+apert\w*|cosa\s+rimane\s+apert\w*|cosa\s+(c'?[eè]\s+)?ancora\s+apert\w*|"
        r"cosa\s+[eè]\s+(ancora\s+)?apert\w*|punti\s+apert\w*|element\w*\s+apert\w*|"
        r"quali\s+punti\s+(sono\s+)?apert\w*|resta\s+qualcosa\s+(di\s+)?apert\w*|"
        r"what'?s\s+still\s+open|what\s+(remains|is\s+still)\s+open|still\s+open|open\s+items)",
        re.IGNORECASE)),
    # Team-oriented draft request → compact operational draft (no emoji, never
    # auto-sent). Must precede briefing/digest so team phrasing wins.
    ("team_brief", re.compile(
        r"(capocantiere|cosa\s+diresti\s+al\s+(team|gruppo|squadra)|"
        r"messaggio\s+operativ\w*|preparami\s+un\s+messaggi\w*|"
        r"sintesi\s+da\s+(mandare|inviare|girare)|da\s+mandare\s+in\s+chat|"
        r"spiegamel\w*|come\s+lo\s+diresti|da\s+girare\s+al\s+(team|gruppo))",
        re.IGNORECASE)),
    # Persone del gruppo → chi scrive qui, dai mittenti reali degli eventi.
    ("group_members", re.compile(
        r"(chi\s+sono\s+i\s+(componenti|membri|partecipanti)|"
        r"(componenti|membri|partecipanti)\s+del\s+gruppo|"
        r"chi\s+(c'?[eè]|fa\s+parte)\s+(nel|del)\s+gruppo|"
        r"chi\s+scrive\s+(qui|nel\s+gruppo)|"
        r"dimmi\s+i\s+nomi\s+(dei|del|delle)\s+(componenti|membri|partecipanti|gruppo))",
        re.IGNORECASE)),
    # Attività di una persona → orari dei suoi messaggi in chat (mai presenze
    # fisiche: quelle non sono tracciate e la risposta lo dichiara).
    ("person_activity", re.compile(
        r"(a\s+che\s+ora\s+(è\s+|e'\s+)?arrivat\w+|"
        r"quando\s+(ha\s+scritto|è\s+arrivat\w+|e'\s+arrivat\w+|si\s+è\s+fatt\w+\s+viv\w+)|"
        r"(l'?ultima|prima)\s+volta\s+che\s+ha\s+scritto|"
        r"a\s+che\s+ora\s+ha\s+scritto)",
        re.IGNORECASE)),
    # Agenda/pianificazione → task attivi ordinati per scadenza. Prima di
    # briefing e open_tasks così "impegni di oggi" / "cosa dobbiamo fare
    # domani" ricevono la vista temporale e non la lista generica.
    ("agenda", re.compile(
        r"(\bagenda\b|\bimpegni\b|in\s+programma|"
        r"programm\w*\s+(di\s+|della\s+|per\s+)?(oggi|domani|dopodomani|settiman\w*)|"
        r"(cosa|che)\s+(dobbiamo|devo|si\s+deve|c'?[eè]\s+da)\s+fare\s+(oggi|domani|dopodomani|questa\s+settimana)|"
        r"da\s+fare\s+(oggi|domani|dopodomani)|"
        r"pianific\w*\s+(di\s+|per\s+)?(oggi|domani|settiman\w*))",
        re.IGNORECASE)),
    ("briefing", re.compile(
        r"(fammi\s+il\s+punto|punto\s+della\s+situazione|riassumi\s+la\s+situazione|"
        r"cosa\s+c'?[eè]\s+da\s+sapere|fammi\s+il\s+report|com'?[eè]\s+messa|quadro\s+operativo|"
        r"quadro\s+della\s+situazione|fammi\s+(il\s+)?quadro|"
        r"fammi\s+capire|cosa\s+sta\s+succedendo|che\s+sta\s+succedendo|"
        r"briefing|fammi\s+un?\s+report|"
        r"operational\s+briefing|how\s+are\s+(we|things)\s+doing|give\s+me\s+the\s+(picture|briefing))",
        re.IGNORECASE)),
    ("digest", re.compile(r"\b(digest|riass\w*|riepilog\w*|sommario|panoramica|summary|overview|stato\s+(del\s+)?(progetto|chat|lavori)|status)\b", re.IGNORECASE)),
    ("changed", re.compile(r"\b(cambiat\w*|cambia|da\s+ieri|novit[aà]|aggiornament\w*|changed|since\s+yesterday|what'?s\s+new|differenz\w*)\b", re.IGNORECASE)),
    ("resolved_issues", re.compile(r"\b(risolt\w*|resolved|fixed|chius\w*\s+problem\w*|problem\w*\s+chius\w*)\b", re.IGNORECASE)),
    ("superseded", re.compile(r"\b(superat\w*|sostituit\w*|superseded|revocat\w*|obsolet\w*|annullat\w*)\b", re.IGNORECASE)),
    ("unanswered", re.compile(r"\b(domand\w*|question\w*|senza\s+risposta|unanswered|da\s+rispondere|open\s+question\w*|rispost\w*\s+manc\w*|quali\s+rispost\w*)\b", re.IGNORECASE)),
    ("attention", re.compile(r"\b(attenzion\w*|attention|urgent\w*|critic\w*|priorit\w*|richiede\w*|da\s+attenzionare|bloccant\w*|bloccar\w*|scoper\w*|rischi\w*\s+di\s+bloccar\w*|scadenz\w*|in\s+scadenza|cosa\s+scad\w*|devo\s+control\w*|da\s+control\w*|devo\s+verifica\w*|da\s+verifica\w*|attenzionar\w*|devo\s+guardar\w*|da\s+guardar\w*|cosa\s+guard\w*|(mi|ci)\s+(devo|dobbiamo)\s+concentr\w*|su\s+cosa\s+concentr\w*|cosa\s+concentr\w*)\b", re.IGNORECASE)),
    ("active_decisions", re.compile(r"\b(decision\w*|decis\w*|deciso|decided)\b", re.IGNORECASE)),
    ("open_issues", re.compile(r"\b(problem\w*\s+apert\w*|issue\w*\s+apert\w*|open\s+issue\w*|problem\w*|guast\w*|anomal\w*|bug)\b", re.IGNORECASE)),
    ("open_tasks", re.compile(r"\b(da\s+fare|resta\w*|riman\w*|to\s*do|todo|task|attivit[aà]|pending|cosa\s+manca|cosa\s+resta|material\w*\s+manc\w*|manc\w*\s+come\s+material\w*|cosa\s+serv\w*|per\s+responsabile|chi\s+deve\s+fare|assegnat\w*\s+a\s+chi|dati\s+manc\w*|chi\s+(si\s+)?deve\s+muover\w*|chi\s+deve\s+intervenir\w*|cosa\s+ci\s+manca|manca\s+per\s+chiuder\w*)\b", re.IGNORECASE)),
]

_INTENT_DISPATCH: dict[str, Callable[[OperationalState], list[QueryAnswerItem]]] = {
    "remaining_open": remaining_open,
    "agenda": agenda_tasks,
    "open_tasks": open_tasks,
    "open_issues": open_issues,
    "resolved_issues": resolved_issues,
    "active_decisions": active_decisions,
    "unanswered": unanswered_questions,
    "superseded": superseded_items,
    "attention": attention_items,
    "changed": changed_since,
    # Draft composer: same priority items as attention, rendered as a draft.
    "team_brief": attention_items,
}

_INTENT_SUMMARY = {
    "remaining_open": "punti ancora aperti",
    "agenda": "impegni in agenda (ordinati per scadenza)",
    "open_tasks": "task ancora aperti",
    "open_issues": "problemi ancora aperti",
    "resolved_issues": "problemi risolti",
    "active_decisions": "decisioni attive",
    "unanswered": "domande senza risposta",
    "superseded": "elementi superati o sostituiti",
    "attention": "elementi che richiedono attenzione",
    "changed": "cambiamenti dallo snapshot precedente",
    "team_brief": "elementi per la bozza operativa",
}


def classify_query_intent(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "unknown"
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(cleaned):
            return intent
    return "unknown"


# Recognised read-only query intents: asking about the state, not adding to it.
_PURE_QUERY_INTENTS = {
    "agenda",
    "briefing", "digest", "remaining_open", "active_decisions",
    "open_tasks", "open_issues", "resolved_issues", "unanswered",
    "superseded", "attention", "changed", "team_brief", "decision_guard",
    # Technical command shortcuts: read-only, never stored as project items.
    "cmd_stato", "cmd_aperti", "cmd_report",
    "issue_media", "reporter_stats", "weather", "assistant_identity",
    "group_members", "person_activity",
}

# Explicit declarative operational-update signals (generic verbs/markers, never
# domain objects): an invocation that also records a new fact/update. Used to
# decide whether the invocation text itself should be stored as operational
# content. Interrogative phrasing ("quali problemi risolti?") does not match.
_STRONG_UPDATE_RE = re.compile(
    r"\b(aggiorna|segna|annota|nota|record|update|note)\b\s*:"
    r"|\b(segna|annota|confermo|conferma|ricorda|registra)\s+che\b"
    r"|\btieni\s+(aperto|presente|conto)\b"
    r"|\bha\s+(mandato|inviato|consegnat\w*|spedit\w*|liberat\w*|risposto|chiesto|confermat\w*)\b"
    r"|\bhanno\s+\w+at[oi]\b"
    r"|\b(è|e')\s+stat[oaie]\b",
    re.IGNORECASE,
)


def is_pure_operational_invocation(query: str) -> bool:
    """True when the invocation text is only a query about the state and carries
    no new operational content — so it must NOT be stored as a project item.

    Generic and domain-agnostic: decision is driven by query intent + explicit
    update signals, never by domain vocabulary. Conservative on the ingest side:
    anything not recognised as a pure query (unknown / content-bearing) returns
    False so real operational data is never dropped."""
    q = (query or "").strip()
    if not q:
        return True  # bare invocation (e.g. "Genesi") → defaults to a briefing query
    intent = classify_query_intent(q)
    if intent not in _PURE_QUERY_INTENTS:
        return False  # unknown or content-bearing → ingest, never lose data
    if intent == "decision_guard":
        return True  # a yes/no decision request is always read-only, never an update
    return not _STRONG_UPDATE_RE.search(q)  # recognised query → pure unless explicit update


def command_status_line(state: OperationalState) -> str:
    """Compact deterministic one-line status (no LLM): active counts per category
    plus the last update timestamp when available. Backs the '@genesi stato'
    technical command. Domain-agnostic, status-driven."""
    ot = len(open_tasks(state))
    oi = len(open_issues(state))
    ri = len(resolved_issues(state))
    ad = len(active_decisions(state))
    info = len(state.information)
    uq = len(unanswered_questions(state))
    line = (
        f"Task {ot} aperti · Problemi {oi} aperti ({ri} risolti) · "
        f"Decisioni attive {ad} · Info {info} · Domande aperte {uq}"
    )
    review = len(getattr(state, "review_queue", []) or [])
    if review:
        line += f" · dubbi {review}"
    if state.updated_at:
        line += f" · agg. {_fmt_updated_at(state.updated_at)}"
    return line


def _fmt_updated_at(iso_ts: str) -> str:
    """Human-readable D/M HH:MM from an ISO timestamp — never the raw ISO string
    in a chat reply. Falls back to the original value if unparsable."""
    try:
        from datetime import datetime
        d = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return d.strftime("%-d/%-m %H:%M")
    except Exception:
        return iso_ts



# --------------------------------------------------------------------------- #
# B11 — spatial/context query filter
# --------------------------------------------------------------------------- #

# Spatial references inside a natural query. Word-based forms (torre/piano/
# livello/scala N, CED, centrale X, …) match anywhere; bare codes (T2, L5)
# only after a preposition so ordinary words are never misread as context.
_QUERY_CONTEXT_RE = re.compile(
    r"\b(?:(?:in|nel|nella|della|del|dello|di|alla|al|su|sulla)\s+)?"
    r"(torre\s*\d{1,3}|piano\s*\d{1,2}|livello\s*\d{1,2}|scala\s*\d{1,2}|"
    r"CED|centrale\s+[A-Za-z]\w*|locale\s+tecnico|copertura|garage|cavedio)\b"
    r"|\b(?:in|nel|nella|su|sulla|alla|al)\s+(T\d{1,3}|L\d{1,2}|SC\d{1,2})\b",
    re.IGNORECASE,
)


def extract_query_context(text: str) -> list[str]:
    """Normalised spatial tokens referenced by the query ('in torre 2'→['T2']).
    Empty list → no context filter. Never invents: only explicit references."""
    tokens: list[str] = []
    seen: set[str] = set()
    for m in _QUERY_CONTEXT_RE.finditer(text or ""):
        raw = (m.group(1) or m.group(2) or "").strip()
        if not raw:
            continue
        canon = normalize_context_token(raw)
        if canon and canon not in seen:
            seen.add(canon)
            tokens.append(canon)
    return tokens


def _item_context_keys(it: QueryAnswerItem) -> set[str]:
    keys: set[str] = set()
    for v in (it.context_area, it.context_system, it.context_level, it.context_location):
        if v:
            canon = normalize_context_token(v)
            keys.add(canon)
            keys.update(expand_level_range(canon))
    for t in it.context_tags or []:
        canon = normalize_context_token(t)
        keys.add(canon)
        keys.update(expand_level_range(canon))
    # Fallback: re-scan the item text at query time so items stored before the
    # extractor learned a token (e.g. "SCALA 2") remain matchable without a
    # state re-extraction pass.
    fresh = extract_context(it.text or "")
    for v in (fresh.context_area, fresh.context_system, fresh.context_level,
              fresh.context_location, *(fresh.context_tags or [])):
        if v:
            canon = normalize_context_token(v)
            keys.add(canon)
            keys.update(expand_level_range(canon))
    return keys


def filter_items_by_context(items: list[QueryAnswerItem], tokens: list[str]) -> list[QueryAnswerItem]:
    """Keep items whose normalised context matches ALL query tokens. Items with
    no context never match a context-scoped query (excluded, never invented)."""
    if not tokens:
        return items
    out: list[QueryAnswerItem] = []
    for it in items:
        keys = _item_context_keys(it)
        if all(tok in keys for tok in tokens):
            out.append(it)
    return out


_DECISION_GUARD_REPLY = (
    "Non posso decidere al posto del team. Posso però mostrarti stato, "
    "priorità e punti aperti utili per decidere."
)


def _reporter_stats_summary(state: OperationalState) -> str:
    """Natural, explainable count of active issues by their recorded sender."""
    counts = Counter(
        (item.source_sender or "").strip()
        for item in state.issues
        if is_active_status("issue", _status_of(item, "issue"))
        and (item.source_sender or "").strip()
    )
    if not counts:
        return (
            "Non ho abbastanza dati affidabili per attribuire le segnalazioni "
            "dei problemi ancora aperti."
        )
    ranked = counts.most_common(3)
    leader, leader_count = ranked[0]
    known_total = sum(counts.values())
    answer = (
        f"Al momento è {leader}: gli sono attribuite {leader_count} delle "
        f"{known_total} segnalazioni aperte con autore identificato."
    )
    if len(ranked) > 1:
        others = ", ".join(f"{name} {count}" for name, count in ranked[1:])
        answer += f" Seguono {others}."
    return answer + " È un conteggio delle fonti registrate, non delle responsabilità."


def answer_query(state: OperationalState, text: str) -> QueryResult:
    intent = classify_query_intent(text)
    if intent == "decision_guard":
        return QueryResult(query=text, intent="decision_guard",
                           summary=_DECISION_GUARD_REPLY, count=0, items=[])
    if intent == "cmd_stato":
        return QueryResult(query=text, intent="cmd_stato", summary=command_status_line(state), count=0, items=[])
    if intent == "reporter_stats":
        return QueryResult(query=text, intent=intent,
                           summary=_reporter_stats_summary(state), count=0, items=[])
    if intent == "issue_media":
        return QueryResult(query=text, intent=intent,
                           summary="Cerco le immagini collegate ai problemi ancora aperti.", count=0, items=[])
    if intent == "group_members":
        return QueryResult(query=text, intent=intent,
                           summary="Guardo chi ha scritto finora nel gruppo.", count=0, items=[])
    if intent == "person_activity":
        return QueryResult(query=text, intent=intent,
                           summary="Controllo l'attività in chat della persona indicata.", count=0, items=[])
    if intent == "weather":
        return QueryResult(query=text, intent=intent,
                           summary="Controllo il meteo senza confonderlo con lo stato operativo.", count=0, items=[])
    if intent == "assistant_identity":
        return QueryResult(query=text, intent=intent,
                           summary="Sono Genesi, il collega digitale del gruppo.", count=0, items=[])
    ctx_tokens = extract_query_context(text)
    ctx_label = " / ".join(ctx_tokens)
    if intent == "cmd_aperti":
        items = filter_items_by_context(remaining_open(state), ctx_tokens)
        summary = f"{len(items)} elementi aperti" if items else "Nessun elemento aperto."
        if ctx_tokens:
            summary += f" ({ctx_label})" if items else f" in {ctx_label}."
        return QueryResult(query=text, intent="cmd_aperti", summary=summary, count=len(items), items=items)
    if intent == "cmd_report":
        return QueryResult(query=text, intent="cmd_report", summary="Report operativo disponibile.", count=0, items=[])
    if intent in {"briefing", "digest"} and ctx_tokens:
        # Context-scoped "fammi il punto del piano 5" → focused open view for
        # that context, never the global card.
        items = filter_items_by_context(remaining_open(state), ctx_tokens)
        summary = (f"Punto {ctx_label}: {len(items)} elementi aperti" if items
                   else f"Nessun elemento aperto in {ctx_label}.")
        return QueryResult(query=text, intent="remaining_open", summary=summary,
                           count=len(items), items=items)
    if intent == "briefing":
        briefing = build_briefing(state)
        return QueryResult(
            query=text,
            intent="briefing",
            summary=f"{briefing.headline}. {briefing.synthesis}",
            count=len(briefing.rows),
            items=briefing.rows and [item for row in briefing.rows if row.active for item in row.items] or [],
        )
    if intent == "remaining_open":
        items = filter_items_by_context(remaining_open(state), ctx_tokens)
        summary = (
            f"{len(items)} punti ancora aperti" if items
            else "Non risultano punti aperti rilevanti."
        )
        if ctx_tokens:
            summary += f" ({ctx_label})" if items else f" Contesto: {ctx_label}."
        return QueryResult(query=text, intent="remaining_open", summary=summary, count=len(items), items=items)
    if intent == "digest":
        digest = build_digest(state)
        return QueryResult(query=text, intent="digest", summary=digest.headline, count=0, items=[])
    if intent == "unknown" or intent not in _INTENT_DISPATCH:
        return QueryResult(
            query=text,
            intent="unknown",
            summary="Domanda non riconosciuta: non ho ancora una lettura affidabile per questa richiesta.",
            count=0,
            items=[],
        )
    items = filter_items_by_context(_INTENT_DISPATCH[intent](state), ctx_tokens)
    summary = f"{len(items)} {_INTENT_SUMMARY.get(intent, intent)}"
    if ctx_tokens:
        summary += f" ({ctx_label})" if items else f" in {ctx_label}"
    return QueryResult(
        query=text,
        intent=intent,
        summary=summary,
        count=len(items),
        items=items,
    )
