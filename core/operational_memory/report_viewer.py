"""FASE 7b — Report Viewer (accessory print/download page).

Render a stored operational report (Markdown) as a light, self-contained,
print-friendly HTML page. This is a technical crutch only: open the report from
a phone, read it, download it, print it. NOT a dashboard — no charts, no admin,
no framework, no client storage.

Dependency-free: a tiny Markdown subset renderer covers exactly what the
briefing/report produces (headings, tables, lists, bold, paragraphs)."""

from __future__ import annotations

import html
import re

from core.operational_memory.models import StoredReport


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _inline(text: str) -> str:
    escaped = html.escape(text)
    return _BOLD_RE.sub(r"<strong>\1</strong>", escaped)


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
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
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
@media print {
  .no-print { display: none !important; }
  body { max-width: none; padding: 0; }
  th { background: #eee !important; -webkit-print-color-adjust: exact; }
}
""".strip()


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
</body>
</html>"""
