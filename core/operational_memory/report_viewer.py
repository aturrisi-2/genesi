"""FASE 7b — Report Viewer (accessory print/download page).

Render a stored operational report (Markdown) as a light, self-contained,
print-friendly HTML page. This is a technical crutch only: open the report from
a phone, read it, download it, print it. NOT a dashboard — no charts, no admin,
no framework, no client storage.

Dependency-free: a tiny Markdown subset renderer covers exactly what the
briefing/report produces (headings, tables, lists, bold, paragraphs)."""

from __future__ import annotations

import html
import os
import re

from core.operational_memory.models import StoredReport


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

# Heading text prefix → HTML id for deep-linking from Telegram.
_HEADING_FOCUS_MAP: dict[str, str] = {
    "Task aperti": "tasks-open",
    "Task completati": "tasks-completed",
    "Problemi aperti": "issues-open",
    "Problemi risolti": "issues-resolved",
    "Problemi riaperti": "issues-reopened",
    "Decisioni attive": "decisions-active",
    "Decisioni superate": "decisions-superseded",
    "Domande aperte": "questions-open",
    "Domande risposte": "questions-answered",
    "Elementi stale": "stale",
    "Elementi superati": "superseded",
    "Cambiamenti": "snapshot-changes",
    "Priorita": "attention",
    "Quadro sintetico": "overview",
    "Sintesi": "synthesis",
    "Dettaglio": "detail",
}


def _inline(text: str) -> str:
    escaped = html.escape(text)
    return _BOLD_RE.sub(r"<strong>\1</strong>", escaped)


def _heading_id(text: str) -> str:
    """Map a heading's text to a focus ID using the prefix table."""
    for prefix, focus_id in _HEADING_FOCUS_MAP.items():
        if text.startswith(prefix):
            return focus_id
    return ""


def _is_table_sep(line: str) -> bool:
    return bool(re.match(r"^\s*\|?[\s:|-]+\|?\s*$", line)) and "-" in line


def _split_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [cell.strip() for cell in cells]


def markdown_to_html(markdown: str) -> str:
    """Render the supported Markdown subset to HTML. Generic, no domain logic."""
    lines = (markdown or "").splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    list_open = False

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            close_list()
            i += 1
            continue

        # Table: header row followed by a separator row.
        if stripped.startswith("|") and i + 1 < n and _is_table_sep(lines[i + 1]):
            close_list()
            header = _split_row(lines[i])
            out.append('<div class="table-wrap"><table><thead><tr>')
            out.extend(f"<th>{_inline(cell)}</th>" for cell in header)
            out.append("</tr></thead><tbody>")
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                row = _split_row(lines[i])
                out.append("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>")
                i += 1
            out.append("</tbody></table></div>")
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            close_list()
            level = len(heading.group(1))
            h_text = heading.group(2)
            h_id = _heading_id(h_text)
            id_attr = f' id="{h_id}"' if h_id else ""
            out.append(f"<h{level}{id_attr}>{_inline(h_text)}</h{level}>")
            i += 1
            continue

        if stripped.startswith("- "):
            if not list_open:
                out.append("<ul>")
                list_open = True
            out.append(f"<li>{_inline(stripped[2:])}</li>")
            i += 1
            continue

        close_list()
        out.append(f"<p>{_inline(stripped)}</p>")
        i += 1

    close_list()
    return "\n".join(out)


_PAGE_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5; margin: 0; padding: 1rem; max-width: 820px; margin-inline: auto;
  color: #1a1a1a; background: #fff;
}
h1 { font-size: 1.5rem; } h2 { font-size: 1.2rem; margin-top: 1.6rem; }
h3 { font-size: 1.05rem; margin-top: 1.2rem; }
.meta { color: #666; font-size: 0.85rem; margin-bottom: 1rem; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; font-size: 0.95rem; }
th, td { border: 1px solid #ccc; padding: 0.35rem 0.5rem; text-align: left; }
th { background: #f3f3f3; }
ul { padding-left: 1.2rem; } li { margin: 0.15rem 0; }
.actions { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
.actions a, .actions button {
  font: inherit; padding: 0.5rem 0.9rem; border: 1px solid #888; border-radius: 6px;
  background: #f7f7f7; color: #1a1a1a; text-decoration: none; cursor: pointer;
}
.focused-section {
  outline: 2px solid rgba(59, 130, 246, 0.5); border-radius: 8px;
  background: rgba(59, 130, 246, 0.06); padding: 0.4rem; margin: -0.4rem;
}
@media (prefers-color-scheme: dark) {
  .focused-section { outline-color: rgba(96, 165, 250, 0.5); background: rgba(96, 165, 250, 0.1); }
}
@media print {
  .no-print { display: none !important; }
  .focused-section { outline: none; background: none; padding: 0; margin: 0; }
  body { max-width: none; padding: 0; }
  th { background: #eee !important; -webkit-print-color-adjust: exact; }
}
""".strip()


_FOCUS_JS = """
<script>
(function(){
  var p = new URLSearchParams(window.location.search).get("focus");
  if (!p) return;
  var el = document.getElementById(p);
  if (!el) return;
  el.classList.add("focused-section");
  setTimeout(function(){ el.scrollIntoView({behavior:"smooth",block:"start"}); }, 120);
})();
</script>"""


def render_report_page(report: StoredReport, download_url: str) -> str:
    """Full standalone HTML page for a stored report (print/download buttons)."""
    body_html = markdown_to_html(report.markdown)
    title = html.escape(f"Report operativo — {report.project_id}")
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="actions no-print">
  <a href="{html.escape(download_url)}" download>Scarica Markdown</a>
  <button type="button" onclick="window.print()">Stampa</button>
</div>
<div class="meta">Progetto: {html.escape(report.project_id)} · Report: {html.escape(report.report_id)} · Generato: {html.escape(report.generated_at)}</div>
<article>
{body_html}
</article>
{_FOCUS_JS}
</body>
</html>"""


def render_daily_report_html(report, json_url: str = "") -> str:
    """Standalone, print-friendly HTML page for a DailyReport. Renders its
    `markdown` via the dependency-free subset renderer. Read-only; no store
    access. `json_url` links back to the raw JSON endpoint when provided."""
    body_html = markdown_to_html(getattr(report, "markdown", "") or "")
    project_id = getattr(report, "project_id", "") or ""
    rtitle = getattr(report, "title", "") or "Aggiornamento giornaliero"
    date = getattr(report, "date", "") or ""
    title = html.escape(f"Aggiornamento giornaliero - {project_id}")
    json_link = (
        f'<a href="{html.escape(json_url)}">JSON</a>' if json_url else ""
    )
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="actions no-print">
  <button type="button" onclick="window.print()">Stampa</button>
  {json_link}
</div>
<h1>{html.escape(rtitle)}</h1>
<div class="meta">Progetto: {html.escape(project_id)}{(' · ' + html.escape(date)) if date else ''}</div>
<article>
{body_html}
</article>
</body>
</html>"""


# --------------------------------------------------------------------------- #
# Report Viewer V2 — structured cards + media thumbnails + internal diary page
# --------------------------------------------------------------------------- #

_V2_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  line-height: 1.45; margin: 0; padding: 1rem; max-width: 900px; margin-inline: auto;
  color: #1a1a1a; background: #fff; }
h1 { font-size: 1.5rem; margin: .2rem 0; } h2 { font-size: 1.15rem; margin: 1.4rem 0 .6rem; border-bottom: 2px solid #e3e3e3; padding-bottom: .2rem; }
.meta-top { color:#666; font-size:.85rem; margin-bottom:1rem; }
.summary { display:flex; flex-wrap:wrap; gap:.6rem; margin:1rem 0; }
.summary .kpi { background:#f4f6f8; border:1px solid #e0e4e8; border-radius:8px; padding:.5rem .8rem; min-width:120px; }
.summary .kpi b { display:block; font-size:1.4rem; }
.summary .kpi span { font-size:.78rem; color:#555; }
.card { border:1px solid #dfe3e8; border-left-width:5px; border-radius:8px; padding:.7rem .9rem; margin:.7rem 0; background:#fff; page-break-inside: avoid; }
.card.issue { border-left-color:#c0392b; } .card.task { border-left-color:#2563c9; }
.card.decision { border-left-color:#7a5; } .card.question { border-left-color:#b8860b; } .card.media { border-left-color:#6a4 caf; border-left-color:#6a4caf; }
.badge { display:inline-block; font-size:.7rem; font-weight:700; letter-spacing:.04em; padding:.1rem .4rem; border-radius:4px; background:#eee; color:#333; vertical-align:middle; }
.card.issue .badge { background:#fde8e6; color:#c0392b; } .card.task .badge { background:#e6effc; color:#2563c9; }
.card.decision .badge { background:#eef6e9; color:#5a8a3c; } .card.question .badge { background:#fcf3e0; color:#b8860b; } .card.media .badge { background:#efe9fb; color:#6a4caf; }
.card h3 { margin:.3rem 0; font-size:1.05rem; }
.card .metablock { margin:.3rem 0 .3rem 1rem; padding-left:.6rem; border-left:2px dotted #ccc; font-style:italic; color:#555; font-size:.85rem; }
.card .metablock div { margin:.1rem 0; }
.card .action { margin-top:.4rem; padding:.35rem .55rem; background:#fff7d6; border:1px solid #ecdf9c; border-radius:6px; font-weight:600; }
.card .todo { background:#fde8e6; color:#c0392b; border-color:#f3c0ba; }
.mediacard { display:flex; gap:.9rem; align-items:flex-start; }
.mediacard img { max-width:240px; max-height:240px; border-radius:6px; border:1px solid #ddd; }
.mediacard .ph { width:200px; height:130px; display:flex; align-items:center; justify-content:center; background:#f0f0f0; color:#888; border:1px dashed #bbb; border-radius:6px; font-size:.8rem; text-align:center; }
.mediacard .mref { color:#999; font-size:.72rem; margin-top:.4rem; }
.empty { color:#888; font-style:italic; font-size:.85rem; }
.actions.no-print button, .actions.no-print a { margin-right:.6rem; }
/* Internal diary page */
.diary { page-break-before: always; margin-top:2rem; border-top:3px double #999; padding-top:1rem; background:#f8f9fa; }
.diary h1 { color:#555; }
.diary, .diary * { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.diary h2 { font-size:1rem; }
.diary ul { margin:.2rem 0 .8rem 1.1rem; padding:0; } .diary li { font-size:.82rem; color:#444; }
@media print { body { padding:0; } .no-print { display:none; } @page { size:A4; margin:14mm; } .card { break-inside: avoid; } }
"""


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _item_title(text: str) -> str:
    """First clause/line as a strong operational title (kept short)."""
    t = (text or "").strip().splitlines()[0] if (text or "").strip() else "(senza testo)"
    return t[:120]


def _meta_lines(item, extra: list[tuple[str, str]] | None = None) -> str:
    rows = []
    def add(label, val):
        if val:
            rows.append(f"<div><b>{_esc(label)}:</b> {_esc(val)}</div>")
    add("Origine", getattr(item, "source", None))
    add("Data", getattr(item, "source_timestamp", None))
    add("Da", getattr(item, "source_sender", None))
    if extra:
        for lbl, val in extra:
            add(lbl, val)
    add("Intent", getattr(item, "intent", None))
    ctx = " · ".join(getattr(item, "context_tags", []) or [])
    add("Contesto", ctx)
    add("Estratto", getattr(item, "source_excerpt", None))
    return "\n".join(rows)


def _card(badge: str, cls: str, title: str, metablock: str, action_html: str) -> str:
    return (f'<article class="card {cls}"><span class="badge">[{_esc(badge)}]</span>'
            f'<h3>{_esc(title)}</h3>'
            f'<div class="metablock">{metablock}</div>'
            f'{action_html}</article>')


def _status_of(item, fallback="open") -> str:
    lc = getattr(item, "lifecycle", None)
    return (getattr(lc, "current_status", None) if lc else None) or getattr(item, "status", None) or fallback


def render_operational_report_v2(state, daily_report, events, project_id: str,
                                 json_url: str = "", thumb_url_fn=None) -> str:
    """Structured, print-friendly operational report (cards + media thumbnails) +
    a separate internal 'diary' page. Reads OperationalState items and media events;
    does not mutate anything. `thumb_url_fn(media_id)` returns a thumbnail URL."""
    thumb_url_fn = thumb_url_fn or (lambda mid: "")
    date = getattr(daily_report, "date", "") or ""
    open_issues = [i for i in state.issues if _status_of(i, "open") in ("open", "reopened", "mitigated", "blocked")]
    open_tasks = [t for t in state.tasks if _status_of(t, "open") in ("open", "in_progress", "blocked", "reopened")]
    media_events = [e for e in events if "image" in str(getattr(e, "attachment_type", "") or getattr(e, "type", "")).lower() and getattr(e, "attachment_path", None)]
    review = list(getattr(state, "review_queue", []) or [])

    # ---- Summary KPIs
    kpis = [
        (len(open_issues), "Criticità aperte"),
        (len(open_tasks), "Task aperti"),
        (len(media_events), "Media analizzati"),
        (len(state.decisions), "Decisioni"),
        (len(review), "Elementi filtrati / dubbi"),
    ]
    summary = "".join(f'<div class="kpi"><b>{n}</b><span>{_esc(lbl)}</span></div>' for n, lbl in kpis)

    # ---- Issues
    issue_cards = []
    for it in open_issues:
        action = f'<div class="action">Problema: {_esc(_item_title(it.text))}</div>'
        issue_cards.append(_card("ISSUE", "issue", _item_title(it.text), _meta_lines(it), action))
    issues_html = "".join(issue_cards) or '<p class="empty">Nessuna criticità aperta.</p>'

    # ---- Tasks
    task_cards = []
    for it in open_tasks:
        owner = getattr(it, "owner", None); due = getattr(it, "due", None)
        extra = [("Owner", owner), ("Scadenza", due)]
        miss = []
        if not owner: miss.append("owner")
        if not due: miss.append("scadenza")
        action = f'<div class="action">Azione richiesta: {_esc(_item_title(it.text))}</div>'
        if miss:
            action += f'<div class="action todo">Da definire: {_esc("/".join(miss))}</div>'
        task_cards.append(_card("TASK", "task", _item_title(it.text), _meta_lines(it, extra), action))
    tasks_html = "".join(task_cards) or '<p class="empty">Nessun task aperto.</p>'

    # ---- Decisions
    dec_cards = [_card("DECISIONE", "decision", _item_title(d.text), _meta_lines(d),
                       f'<div class="action">Decisione: {_esc(_item_title(d.text))}</div>') for d in state.decisions]
    dec_html = "".join(dec_cards) or '<p class="empty">Nessuna decisione registrata.</p>'

    # ---- Questions
    q_cards = [_card("DOMANDA", "question", _item_title(q.text), _meta_lines(q),
                     f'<div class="action">Domanda aperta: {_esc(_item_title(q.text))}</div>')
               for q in state.open_questions if _status_of(q, "open") in ("open", "partially_answered")]
    q_html = "".join(q_cards) or '<p class="empty">Nessuna domanda aperta.</p>'

    # ---- Media cards (real thumbnail)
    media_cards = []
    for e in media_events:
        mid = os.path.basename(getattr(e, "attachment_path", "") or "")
        url = thumb_url_fn(mid)
        ocr = (getattr(e, "extracted_text", "") or "").strip()
        desc = (getattr(e, "media_description", "") or "").strip()
        img = f'<img src="{_esc(url)}" alt="miniatura media">' if url else '<div class="ph">Miniatura non disponibile</div>'
        body = []
        if desc: body.append(f"<div><b>Tema:</b> <i>{_esc(desc)}</i></div>")
        if ocr: body.append(f"<div><b>OCR:</b> <i>{_esc(ocr[:400])}</i></div>")
        body.append(f'<div class="mref">rif. media: {_esc(mid)}</div>')
        media_cards.append(
            f'<article class="card media"><span class="badge">[MEDIA]</span>'
            f'<div class="mediacard">{img}<div>{"".join(body)}</div></div></article>')
    media_html = "".join(media_cards) or '<p class="empty">Nessun media rilevante.</p>'

    # ---- Media transparency (counts + declared hidden/unsupported media)
    transp = getattr(daily_report, "media_transparency", {}) or {}
    transp_counts = transp.get("counts", {}) if isinstance(transp, dict) else {}
    if transp_counts:
        rows = [
            f"Ricevuti: {transp_counts.get('media_received_total', 0)} "
            f"(immagini {transp_counts.get('images_received', 0)}, video {transp_counts.get('videos_received', 0)}, "
            f"documenti {transp_counts.get('documents_received', 0)}, audio {transp_counts.get('audio_received', 0)})",
            f"Analizzati con contenuto: {transp_counts.get('media_analyzed_with_content', 0)} · "
            f"senza contenuto: {transp_counts.get('media_without_content', 0)} · "
            f"non supportati: {transp_counts.get('media_unsupported', 0)}",
            f"Visibili nel report: {transp_counts.get('media_visible_in_report', 0)} · "
            f"analizzati ma non promossi: {transp_counts.get('media_hidden_by_filter', 0)}",
        ]
        rows += [str(n) for n in transp.get("diagnostic_notes", [])]
        transp_html = "<ul>" + "".join(f"<li>{_esc(r)}</li>" for r in rows) + "</ul>"
    else:
        transp_html = '<p class="empty">Nessun media ricevuto.</p>'

    # ---- Next actions (from daily report strings)
    next_actions = getattr(daily_report, "next_actions", []) or []
    na_html = ("<ul>" + "".join(f"<li>{_esc(a)}</li>" for a in next_actions) + "</ul>") if next_actions else '<p class="empty">—</p>'

    # ---- Internal diary (separate page)
    def _diary_block(label, items):
        items = items or []
        if not items:
            return ""
        lis = "".join(f"<li>{_esc(x)}</li>" for x in items[:50])
        return f"<h2>{_esc(label)}</h2><ul>{lis}</ul>"
    review_lines = [f"{r.proposed_type} · {r.reason} · {r.snippet[:120]}" for r in review]
    diary = "".join([
        _diary_block("Eventi / statistiche impatto", getattr(daily_report, "impact_statistics", [])),
        _diary_block("Macro-thread", getattr(daily_report, "operational_macro_threads", [])),
        _diary_block("Thread operativi", getattr(daily_report, "operational_threads", [])),
        _diary_block("Relazioni candidate", getattr(daily_report, "thread_relation_candidates", [])),
        _diary_block("Rumore conversazionale filtrato", getattr(daily_report, "conversational_noise_filtered", [])),
        _diary_block("Elementi da revisione (review_queue)", review_lines),
        _diary_block("Da verificare", getattr(daily_report, "items_to_verify", [])),
        _diary_block("Cambiamenti dallo snapshot", getattr(daily_report, "lifecycle_changes", [])),
        _diary_block("Stato corrente lifecycle", getattr(daily_report, "lifecycle_current_state", [])),
    ]) or '<p class="empty">Nessuna annotazione di processo.</p>'

    json_link = f'<a href="{_esc(json_url)}">JSON</a>' if json_url else ""
    title = _esc(f"Aggiornamento operativo - {project_id} - {date}")
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_V2_CSS}</style>
</head>
<body>
<div class="actions no-print">
  <button type="button" onclick="window.print()">Stampa</button>
  {json_link}
</div>
<h1>Aggiornamento operativo — {_esc(project_id)}{(' — ' + _esc(date)) if date else ''}</h1>
<div class="summary">{summary}</div>

<h2>1. Criticità / Problemi aperti</h2>
{issues_html}
<h2>2. Task aperti</h2>
{tasks_html}
<h2>3. Decisioni</h2>
{dec_html}
<h2>4. Domande aperte</h2>
{q_html}
<h2>5. Media rilevanti</h2>
{media_html}
<h2>5b. Affidabilità media e allegati</h2>
{transp_html}
<h2>6. Prossime azioni</h2>
{na_html}

<section class="diary">
<h1>Diario di bordo Genesi — processo interno</h1>
<div class="meta-top">Tracciabilità del ragionamento (thread, relazioni, filtri, lifecycle). Non è il report operativo.</div>
{diary}
</section>
</body>
</html>"""
