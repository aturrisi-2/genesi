#!/usr/bin/env python3
"""
test_predictive_engine.py — Test approfondito del Predictive Processing Engine

Verifica 6 fasi:
  F1 — Generazione predizioni: PREDICTIVE_UPDATED appare nel log
  F2 — Assessment sorpresa: PREDICTIVE_ASSESS appare dal 2° turno in poi
  F3 — Shadow mode: hint NON iniettato nei primi 12 turni
  F4 — Uscita shadow: hint INIETTATO dopo il 13° turno (PREDICTIVE_HINT_INJECTED)
  F5 — Score corretto: bassa sorpresa su topic continuato, alta su cambio topic
  F6 — Storage: file predizione presente e con dati validi

Uso:
  python3 scripts/test_predictive_engine.py [email] [password]

Default: usa credenziali alfio (possono essere passate come argomenti).
Il test crea conversazioni reali — esegui fix_profile_alfio.py dopo se necessario.

ATTENZIONE: questo test dura ~5 minuti (pause per background tasks + 18 messaggi).
"""

import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import os
import re
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL   = "http://localhost:8000"
LOG_PATH   = Path("/opt/genesi/genesi.log")

DEFAULT_EMAIL = "alfio.turrisi@gmail.com"
DEFAULT_PASS  = "ZOEennio0810"

# Pause tra messaggi: abbastanza lunga da far completare il background task
MSG_PAUSE = 5   # secondi tra un messaggio e l'altro
LOG_WAIT  = 3   # attesa extra dopo un gruppo per leggere il log

SHADOW_THRESHOLD = 12  # turni prima dell'attivazione hint

# Colori ANSI
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


# ── HTTP helpers ───────────────────────────────────────────────────────────────
def _req(method: str, path: str, payload=None, token=None):
    url     = BASE_URL + path
    body    = json.dumps(payload).encode() if payload else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def login(email: str, password: str):
    status, data = _req("POST", "/auth/login", {"email": email, "password": password})
    if status != 200:
        print(f"{RED}Login fallito: {status} {data}{RESET}")
        sys.exit(1)
    return data["access_token"]


def send_message(token: str, message: str) -> str:
    _, data = _req("POST", "/api/chat", {"message": message}, token=token)
    return data.get("response", "") or data.get("message", "")


# ── Log helpers ────────────────────────────────────────────────────────────────
def read_log_tail(lines: int = 300) -> str:
    try:
        if not LOG_PATH.exists():
            return ""
        with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except PermissionError:
        # Fallback: leggi solo ultimi N byte
        try:
            with open(LOG_PATH, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 80000))
                raw = f.read()
            text = raw.decode("utf-8", errors="ignore")
            all_lines = text.splitlines(keepends=True)
            return "".join(all_lines[-lines:])
        except Exception:
            return ""
    except Exception:
        return ""


def count_occurrences(tag: str, log: str) -> int:
    return log.count(tag)


def find_last_value(tag: str, field: str, log: str):
    """Cerca l'ultimo valore di un campo in una riga di log con il tag dato."""
    pattern = rf"{re.escape(tag)}[^\n]*{re.escape(field)}=([^\s]+)"
    matches = re.findall(pattern, log)
    return matches[-1] if matches else None


# ── Output helpers ─────────────────────────────────────────────────────────────
def ok(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str):
    print(f"  {RED}✗{RESET} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}⚠{RESET} {msg}")


def info(msg: str):
    print(f"  {CYAN}·{RESET} {msg}")


def phase(n: int, title: str):
    print(f"\n{BOLD}{BLUE}━━━ F{n}: {title} ━━━{RESET}")


# ── Lettura storage locale ─────────────────────────────────────────────────────
def read_prediction_storage(user_id: str) -> dict:
    """Legge il file predizione direttamente dal disco."""
    candidates = [
        Path(f"/opt/genesi/memory/predictions/{user_id}.json"),
        Path(f"memory/predictions/{user_id}.json"),
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def get_user_id_from_log(email: str, log: str) -> str | None:
    """Cerca lo user_id associato all'email nel log recente."""
    # Cerca un pattern come user_id=abc123 nelle righe di AUTH
    # Alternativa: cerca nel profilo
    pattern = rf"user.*?({email})[^\n]*user_id=([^\s]+)"
    m = re.search(pattern, log, re.IGNORECASE)
    if m:
        return m.group(2)
    return None


# ── Test principale ────────────────────────────────────────────────────────────
def main():
    email    = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMAIL
    password = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PASS

    print(f"\n{BOLD}{'═'*60}")
    print(f"  🧠 PREDICTIVE ENGINE — TEST APPROFONDITO")
    print(f"  Utente: {email}")
    print(f"  Shadow threshold: {SHADOW_THRESHOLD} turni")
    print(f"  Ora: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'═'*60}{RESET}\n")

    results = {"passed": 0, "failed": 0, "warned": 0}

    def check(condition: bool, ok_msg: str, fail_msg: str, warning: bool = False):
        if condition:
            ok(ok_msg)
            results["passed"] += 1
        elif warning:
            warn(fail_msg)
            results["warned"] += 1
        else:
            fail(fail_msg)
            results["failed"] += 1
        return condition

    # Login
    print(f"{CYAN}Login...{RESET}")
    token = login(email, password)
    print(f"{GREEN}Token ottenuto{RESET}\n")

    # Snapshot del log PRIMA del test (per isolare i nuovi eventi)
    log_baseline = read_log_tail(500)
    baseline_predict_updated = count_occurrences("PREDICTIVE_UPDATED", log_baseline)
    baseline_predict_assess  = count_occurrences("PREDICTIVE_ASSESS",  log_baseline)
    baseline_hint_injected   = count_occurrences("PREDICTIVE_HINT_INJECTED", log_baseline)

    info(f"Baseline log — UPDATED={baseline_predict_updated} ASSESS={baseline_predict_assess} HINT={baseline_hint_injected}")

    # ─── FASE 1: Primi turni — verifica generazione predizioni ─────────────────
    phase(1, "Generazione predizioni (PREDICTIVE_UPDATED)")

    print(f"\n  Invio 3 messaggi su tema lavoro…")
    WORK_MESSAGES = [
        "Oggi al lavoro è stata una giornata intensa, ho avuto 4 riunioni di fila",
        "Il mio capo ha chiesto di accelerare sul progetto di fine trimestre",
        "I colleghi sono sotto pressione, devo gestire anche le richieste del team",
    ]
    for i, msg in enumerate(WORK_MESSAGES):
        resp = send_message(token, msg)
        info(f"Turno {i+1}: '{msg[:50]}…'")
        info(f"  Risposta: '{resp[:60]}…'")
        time.sleep(MSG_PAUSE)

    time.sleep(LOG_WAIT)
    log_after_3 = read_log_tail(400)
    new_updated = count_occurrences("PREDICTIVE_UPDATED", log_after_3) - baseline_predict_updated

    check(
        new_updated >= 1,
        f"PREDICTIVE_UPDATED trovato {new_updated} volta/e dopo 3 turni",
        f"PREDICTIVE_UPDATED NON trovato nel log (attesi ≥1, trovati {new_updated})"
    )

    new_assess = count_occurrences("PREDICTIVE_ASSESS", log_after_3) - baseline_predict_assess
    check(
        new_assess >= 1,
        f"PREDICTIVE_ASSESS trovato {new_assess} volta/e (assessment attivo dal 2° turno)",
        f"PREDICTIVE_ASSESS NON trovato (attesi ≥1, trovati {new_assess})",
        warning=True  # Potrebbe non esserci al primo turno se prediction non ancora pronta
    )

    # ─── FASE 2: Verifica score sorpresa su topic continuato ──────────────────
    phase(2, "Surprise score — topic continuato (bassa sorpresa attesa)")

    print(f"\n  Invio 3 messaggi COERENTI con il topic lavoro…")
    WORK_CONTINUED = [
        "Il progetto scade venerdì, sto cercando di organizzare le priorità",
        "Ho mandato un aggiornamento al capo, speriamo basti",
        "Finalmente la riunione pomeridiana è andata bene",
    ]
    for i, msg in enumerate(WORK_CONTINUED):
        send_message(token, msg)
        info(f"Turno {4+i}: '{msg[:50]}…'")
        time.sleep(MSG_PAUSE)

    time.sleep(LOG_WAIT)
    log_after_6 = read_log_tail(400)

    # Cerca l'ultimo valore di surprise nel log
    surprises = re.findall(r"PREDICTIVE_ASSESS[^\n]*surprise=([\d.]+)", log_after_6)
    if surprises:
        last_surprises = [float(s) for s in surprises[-4:]]  # ultimi 4
        avg_surprise   = sum(last_surprises) / len(last_surprises)
        info(f"Ultimi 4 surprise scores: {[round(s,2) for s in last_surprises]}")
        info(f"Media: {avg_surprise:.2f}")
        check(
            avg_surprise < 0.75,
            f"Surprise medio {avg_surprise:.2f} < 0.75 (topic continuato = bassa sorpresa)",
            f"Surprise medio {avg_surprise:.2f} troppo alto per topic continuato (atteso < 0.75)",
            warning=True
        )
    else:
        warn("Nessun surprise score trovato nel log — verifica formato log")
        results["warned"] += 1

    # ─── FASE 3: Shadow mode confermato (< 12 turni) ──────────────────────────
    phase(3, "Shadow mode attivo (hint NON iniettato)")

    new_hints = count_occurrences("PREDICTIVE_HINT_INJECTED", log_after_6) - baseline_hint_injected
    check(
        new_hints == 0,
        f"Nessun hint iniettato nei primi 6 turni (shadow mode corretto)",
        f"Hint iniettato troppo presto! ({new_hints} iniezioni nei primi 6 turni)"
    )

    # Verifica shadow=True nel log
    shadow_logs = re.findall(r"PREDICTIVE_ASSESS[^\n]*shadow=(True|False)", log_after_6)
    if shadow_logs:
        last_shadow = shadow_logs[-1]
        check(
            last_shadow == "True",
            f"shadow=True confermato nel log (siamo a <12 turni)",
            f"shadow={last_shadow} — atteso True a 6 turni",
        )

    # ─── FASE 4: Completare la shadow phase (turni 7-13) ──────────────────────
    phase(4, "Completamento shadow phase + attivazione hint")

    print(f"\n  Invio 7 messaggi aggiuntivi per uscire dalla shadow phase…")
    SHADOW_EXIT_MSGS = [
        "Come stai, Genesi?",
        "Che giornata è oggi?",
        "Dimmi qualcosa di interessante sul tema del tempo",
        "Quanti giorni mancano alla fine del mese?",
        "Parlami brevemente della situazione economica italiana",
        "Qual è il tuo argomento preferito di conversazione?",
        "Raccontami una cosa curiosa che sai",
    ]
    for i, msg in enumerate(SHADOW_EXIT_MSGS):
        resp = send_message(token, msg)
        info(f"Turno {7+i}: '{msg[:45]}…'")
        time.sleep(MSG_PAUSE)

    print(f"\n  {YELLOW}Attendo 6s per i background tasks del 13° turno…{RESET}")
    time.sleep(6)

    # ─── FASE 5: Post-shadow — verifica iniezione hint ────────────────────────
    phase(5, "Iniezione hint nel prompt (post-shadow)")

    print(f"\n  Invio 2 messaggi post-shadow per triggerare l'iniezione…")
    POST_SHADOW_MSGS = [
        "Torniamo a parlare del lavoro, come posso gestire meglio lo stress?",
        "Hai qualche consiglio per migliorare la produttività in ufficio?",
    ]
    for msg in POST_SHADOW_MSGS:
        resp = send_message(token, msg)
        info(f"'{msg[:50]}…'")
        info(f"Risposta: '{resp[:70]}…'")
        time.sleep(MSG_PAUSE)

    time.sleep(LOG_WAIT)
    log_after_all = read_log_tail(600)

    new_hints_all = count_occurrences("PREDICTIVE_HINT_INJECTED", log_after_all) - baseline_hint_injected
    check(
        new_hints_all >= 1,
        f"PREDICTIVE_HINT_INJECTED trovato {new_hints_all} volta/e dopo shadow phase",
        f"PREDICTIVE_HINT_INJECTED NON trovato dopo 13+ turni — hint non attivo",
        warning=True  # warning perché dipende dall'accuracy media raggiunta
    )

    # Verifica shadow=False nei turni recenti
    shadow_recent = re.findall(r"PREDICTIVE_ASSESS[^\n]*shadow=(True|False)", log_after_all)
    if shadow_recent:
        last_shadow_recent = shadow_recent[-1]
        check(
            last_shadow_recent == "False",
            f"shadow=False nei turni recenti (fuori shadow phase)",
            f"shadow={last_shadow_recent} — atteso False dopo {SHADOW_THRESHOLD} turni",
            warning=True
        )

    # ─── FASE 6: Cambio topic — alta sorpresa attesa ───────────────────────────
    phase(6, "Cambio topic brusco — alta sorpresa")

    print(f"\n  Invio messaggio COMPLETAMENTE diverso (sport, dopo conversazione lavoro)…")
    resp = send_message(token, "Sai che la Juventus ha perso ieri? Sono deluso")
    info(f"Risposta: '{resp[:70]}…'")
    time.sleep(MSG_PAUSE + 2)

    log_topic_change = read_log_tail(200)
    surprises_all = re.findall(r"PREDICTIVE_ASSESS[^\n]*surprise=([\d.]+)", log_topic_change)
    if surprises_all:
        last_surprise_val = float(surprises_all[-1])
        info(f"Surprise score cambio topic: {last_surprise_val:.2f}")
        check(
            last_surprise_val > 0.40,
            f"Surprise {last_surprise_val:.2f} > 0.40 (cambio topic = alta sorpresa)",
            f"Surprise {last_surprise_val:.2f} troppo basso per un cambio topic brusco",
            warning=True
        )
    else:
        warn("Nessun surprise score trovato per il test cambio topic")
        results["warned"] += 1

    # ─── FASE 7: Verifica storage su disco ────────────────────────────────────
    phase_num = 7
    phase(phase_num, "Storage predizione su disco")

    # Cerca lo user_id: prova più endpoint poi fallback su directory
    user_id = None
    for endpoint in ("/api/users/me", "/api/user/me", "/api/profile"):
        _, me_data = _req("GET", endpoint, token=token)
        user_id = (me_data.get("id") or me_data.get("user_id") or
                   me_data.get("user", {}).get("id") if isinstance(me_data, dict) else None)
        if user_id:
            break

    if not user_id:
        # Fallback: trova il file predictions modificato più di recente
        pred_dir = Path("/opt/genesi/memory/predictions")
        if pred_dir.exists():
            files = sorted(pred_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                user_id = files[0].stem
                info(f"user_id dedotto dal file più recente: {user_id}")

    pred_dir = Path("/opt/genesi/memory/predictions")
    check(
        pred_dir.exists() and any(pred_dir.glob("*.json")),
        f"Directory predictions presente con almeno 1 file",
        f"Directory /opt/genesi/memory/predictions vuota o assente"
    )

    if user_id:
        info(f"user_id: {user_id}")
        pred_data = read_prediction_storage(user_id)
        if pred_data:
            total_ass = pred_data.get("total_assessments", 0)
            history   = pred_data.get("accuracy_history", [])
            last_pred = pred_data.get("next_turn_prediction", "")
            recent    = pred_data.get("recent_turns", [])

            check(total_ass >= 10, f"total_assessments={total_ass} (≥10 atteso)",
                  f"total_assessments={total_ass} troppo basso (atteso ≥10)")
            check(len(history) >= 5, f"accuracy_history ha {len(history)} entry (≥5 atteso)",
                  f"accuracy_history ha solo {len(history)} entry")
            check(bool(last_pred), f"next_turn_prediction presente: '{last_pred[:60]}…'",
                  "next_turn_prediction è vuota!")
            check(len(recent) >= 3, f"recent_turns ha {len(recent)} entry (≥3 atteso)",
                  f"recent_turns ha solo {len(recent)} entry", warning=True)

            if history:
                avg_hist = sum(history) / len(history)
                info(f"Accuratezza media storica: {avg_hist:.2%}")
                info(f"Entries history: {[round(h,2) for h in history[-5:]]}")
        else:
            fail(f"File predizione non trovato per user_id={user_id}")
            results["failed"] += 1
    else:
        warn("Impossibile determinare user_id — skip verifica storage")
        results["warned"] += 1

    # ─── Risultato finale ──────────────────────────────────────────────────────
    total = results["passed"] + results["failed"] + results["warned"]
    print(f"\n{BOLD}{'═'*60}")
    print(f"  RISULTATI PREDICTIVE ENGINE TEST")
    print(f"{'═'*60}{RESET}")
    print(f"  {GREEN}✓ Passati: {results['passed']}{RESET}")
    print(f"  {RED}✗ Falliti: {results['failed']}{RESET}")
    print(f"  {YELLOW}⚠ Warning: {results['warned']}{RESET}")

    score_pct = int(results["passed"] / total * 100) if total > 0 else 0
    color = GREEN if score_pct >= 80 else (YELLOW if score_pct >= 60 else RED)
    print(f"\n  {BOLD}{color}Score: {results['passed']}/{total} ({score_pct}%){RESET}")

    # Interpretazione
    print(f"\n{CYAN}  Interpretazione:{RESET}")
    if results["failed"] == 0:
        print(f"  {GREEN}Predictive Processing attivo e funzionante correttamente.{RESET}")
    elif results["failed"] <= 2:
        print(f"  {YELLOW}PP parzialmente attivo. Verifica log per i check falliti.{RESET}")
    else:
        print(f"  {RED}PP non funzionante. Controlla che il server sia aggiornato e riavviato.{RESET}")

    print(f"\n{CYAN}  Tags da cercare in genesi.log:{RESET}")
    print(f"    PREDICTIVE_UPDATED      — predizione generata dopo ogni turno")
    print(f"    PREDICTIVE_ASSESS       — sorpresa calcolata all'arrivo messaggio")
    print(f"    PREDICTIVE_HINT_INJECTED — hint iniettato nel prompt (post-shadow)")
    print()

    return results["failed"] == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
