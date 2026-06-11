#!/usr/bin/env python3
"""
Genesi Monitor — Analizzatore di log automatico tramite OpenClaw (no browser)

Gira come cron job indipendente sul VPS, NON dipende da Genesi.
OpenClaw legge i log e genera un report strutturato senza aprire il browser.

Setup cron (ogni 30 minuti):
  */30 * * * * /home/luca/genesi/venv/bin/python /home/luca/genesi/scripts/genesi_monitor.py >> /home/luca/genesi/monitor.log 2>&1

Setup cron (ogni ora):
  0 * * * * /home/luca/genesi/venv/bin/python /home/luca/genesi/scripts/genesi_monitor.py >> /home/luca/genesi/monitor.log 2>&1
"""

import os
import sys
import subprocess
import re
from datetime import datetime

# ─── Percorsi ────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE    = os.path.join(BASE_DIR, "genesi.log")
REPORT_FILE = os.path.join(BASE_DIR, "GENESI_AUDIT_REPORT.md")
LASTRUN_FILE = os.path.join(BASE_DIR, "monitor_lastrun.txt")

OPENCLAW_BIN = "/home/luca/.npm-global/bin/openclaw"

# Quante righe di log analizzare per audit
LOG_LINES = 600

# Soglia minima di nuove righe dal last run per attivare l'analisi
MIN_NEW_LINES = 100


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _tail(path: str, n: int) -> str:
    """Legge le ultime N righe del file."""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return "".join(lines[-n:])

def _line_count(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)

def _read_lastrun() -> int:
    """Ritorna il numero di righe al momento dell'ultimo run."""
    if not os.path.exists(LASTRUN_FILE):
        return 0
    try:
        with open(LASTRUN_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0

def _write_lastrun(count: int):
    with open(LASTRUN_FILE, "w") as f:
        f.write(str(count))

def _should_run() -> tuple[bool, str]:
    """
    Decide se eseguire l'audit.
    Ritorna (bool, motivo).
    """
    current = _line_count(LOG_FILE)
    last = _read_lastrun()
    new_lines = current - last

    if new_lines < MIN_NEW_LINES:
        return False, f"Solo {new_lines} nuove righe (soglia: {MIN_NEW_LINES})"

    return True, f"{new_lines} nuove righe da analizzare"


# ─── Core ────────────────────────────────────────────────────────────────────

def build_prompt(log_snippet: str, timestamp: str) -> str:
    return f"""Sei l'Auditor di Genesi. Il tuo compito è analizzare i log tecnici di un sistema AI e produrre un report per lo sviluppatore.

IMPORTANTE: NON navigare su internet. NON aprire browser. Lavora SOLO sui log qui sotto.

LOG DA ANALIZZARE ({LOG_LINES} righe recenti — formato: [TIMESTAMP] TAG key=value):
---
{log_snippet}
---

Scrivi un report in Markdown IN ITALIANO con esattamente queste sezioni:

# GENESI AUDIT — {timestamp}

## ✅ COSA FUNZIONA BENE
(intenti classificati correttamente, tool che rispondono, memoria che si aggiorna, ecc.)

## ❌ COSA NON FUNZIONA
(errori API, classificazioni sbagliate, timeout, loop, fallback inutili)

## 🔧 COSA MIGLIORARE
(pattern regex mancanti, prompt da affinare, intenti ambigui ricorrenti)

## ✨ COSA AGGIUNGERE
(richieste utente non soddisfatte, nuove feature suggerite dai pattern)

## 📊 STATISTICHE RAPIDE
- Conversazioni analizzate: X
- Errori trovati: X
- Intenti più frequenti: X, Y, Z

Sii concreto, tecnico e diretto. Max 600 parole totali."""


def run():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[{timestamp}] [MONITOR] Genesi Monitor avviato")

    # 1. Controlla se serve girare
    should, reason = _should_run()
    if not should:
        print(f"[MONITOR] Skip: {reason}")
        return

    print(f"[MONITOR] Avvio audit: {reason}")

    # 2. Leggi log
    log_snippet = _tail(LOG_FILE, LOG_LINES)
    if not log_snippet.strip():
        print("[MONITOR] Log vuoto, skip.")
        return

    # 3. Costruisci prompt (NO URL, NO browser)
    prompt = build_prompt(log_snippet, timestamp)

    # 4. Chiama OpenClaw in agent mode (senza browser)
    env = os.environ.copy()
    env["PATH"] = f"/home/luca/.npm-global/bin:{env.get('PATH', '')}"

    print(f"[MONITOR] Chiamata OpenClaw agent (no browser)...")
    try:
        result = subprocess.run(
            [
                OPENCLAW_BIN, "agent",
                "--message", prompt,
                "--agent", "main",
                "--session-id", "genesi_monitor_auto",
                "--no-color",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout.strip()

        # Pulisci tag interni (thoughts, system notes)
        output = re.sub(r'<thought>.*?</thought>', '', output, flags=re.DOTALL | re.IGNORECASE)
        output = re.sub(r'\[Thought:.*?\]', '', output, flags=re.DOTALL | re.IGNORECASE)
        output = re.sub(r'\[System note:.*?\]', '', output, flags=re.DOTALL | re.IGNORECASE)
        output = output.strip()

        if result.returncode != 0 or not output:
            print(f"[MONITOR] ⚠️ OpenClaw exit={result.returncode}, uso fallback diretto")
            _fallback_direct(log_snippet, timestamp)
        else:
            # Scrivi report
            with open(REPORT_FILE, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"[MONITOR] ✅ Report OpenClaw salvato: {REPORT_FILE}")

    except FileNotFoundError:
        print(f"[MONITOR] ⚠️ OpenClaw non trovato in {OPENCLAW_BIN}, uso fallback diretto")
        _fallback_direct(log_snippet, timestamp)
    except subprocess.TimeoutExpired:
        print("[MONITOR] ⚠️ Timeout OpenClaw (120s), uso fallback diretto")
        _fallback_direct(log_snippet, timestamp)
    except Exception as e:
        print(f"[MONITOR] ❌ Errore: {e}")
        _fallback_direct(log_snippet, timestamp)

    # 5. Aggiorna contatore last run
    _write_lastrun(_line_count(LOG_FILE))
    print(f"[MONITOR] Contatore aggiornato.")


def _fallback_direct(log_snippet: str, timestamp: str):
    """
    Fallback: chiama l'LLM direttamente via GenesiAuditor
    (richiede che Genesi sia nel PYTHONPATH).
    """
    try:
        # Aggiungi la root di Genesi al path Python
        sys.path.insert(0, BASE_DIR)
        import asyncio
        from core.genesi_auditor import genesi_auditor

        report = asyncio.run(genesi_auditor.generate_report(lines_to_read=LOG_LINES))
        print(f"[MONITOR] ✅ Report fallback (GenesiAuditor) salvato: {REPORT_FILE}")
    except Exception as e:
        # Ultimo fallback: report base con statistiche
        errors = log_snippet.count("ERROR")
        warns  = log_snippet.count("WARN")
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(f"# GENESI AUDIT — {timestamp} (fallback statistico)\n\n")
            f.write(f"- **Errori trovati:** {errors}\n")
            f.write(f"- **Warning trovati:** {warns}\n")
            f.write(f"\n> Report generato senza LLM (errore: {e})\n")
        print(f"[MONITOR] ⚠️ Report statistico salvato (LLM non disponibile): {e}")


if __name__ == "__main__":
    run()
