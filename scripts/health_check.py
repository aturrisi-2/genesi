#!/usr/bin/env python3
"""
GENESI HEALTH CHECK — Stato di salute intellettuale
======================================================
Testa le capacità cognitive di Genesi e smaschera failure silenziosi:

  1. Connettività & Auth
  2. Identità stabile (chi è, dove vive socialmente)
  3. Memoria in-sessione (ricorda ciò che le si dice)
  4. Profondità intellettuale (non risponde con frasi generiche)
  5. Intelligenza emotiva (reagisce con empatia reale)
  6. Regole lab applicate (no "capisco", no roleplay, ecc.)
  7. Prompt adattivo caricato (log LLM_ADAPTIVE_PROMPT_LOADED)
  8. Intent classification funzionante
  9. Personal facts salvati (log PERSONAL_FACTS)
 10. Episodi salvati (log EPISODE)
 11. Fallback sotto controllo (nessuna risposta "Mi dispiace")
 12. Risposta non è un muro di testo generico

Uso:
    python3 scripts/health_check.py
    python3 scripts/health_check.py --email EMAIL --password PWD
    python3 scripts/health_check.py --verbose
"""

import argparse, json, sys, os, re, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime
from typing import Optional, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL      = "http://localhost:8000"
DEFAULT_EMAIL = "alfio.turrisi@gmail.com"
DEFAULT_PWD   = "ZOEennio0810"
LOG_FILE      = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "genesi.log")

# ── ANSI colors ───────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── Frasi che indicano failure silenzioso ─────────────────────────────────────
FALLBACK_PHRASES = [
    r"\bmi dispiace\b", r"\bnon ho capito\b", r"\bnon sono sicur\b",
    r"\bcome (AI|intelligenza artificiale)\b", r"\bsono (un'?)?AI\b",
    r"\bnon posso (rispondere|aiutarti)\b", r"\bsi è verificato un errore\b",
    r"\bqualcosa è andato storto\b",
]

FORBIDDEN_WORDS = [
    r"\bcapisco\b(?! il|la|le|lo|che|come|perché|cosa)",  # "capisco" da solo
    r"\bahoy\b", r"\barrr\b", r"\bcapitano\b",             # roleplay rifiutato
]

_fallback_re = [re.compile(p, re.IGNORECASE) for p in FALLBACK_PHRASES]
_forbidden_re = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_WORDS]


# ══════════════════════════════════════════════════════════════════════════════
#  HTTP helpers
# ══════════════════════════════════════════════════════════════════════════════

def _http(method: str, path: str, body=None, token: str = None, timeout=30) -> dict:
    url = BASE_URL + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"status": r.status, "body": json.loads(r.read().decode())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": {}, "error": str(e)}
    except Exception as e:
        return {"status": 0, "body": {}, "error": str(e)}


def login(email: str, pwd: str) -> Optional[str]:
    r = _http("POST", "/auth/login", {"email": email, "password": pwd})
    return r["body"].get("access_token") if r["status"] == 200 else None


def chat(message: str, token: str) -> Tuple[str, str, float]:
    """Ritorna (response_text, intent, latency_ms)."""
    t0 = time.time()
    r = _http("POST", "/api/chat/", {"message": message}, token=token, timeout=45)
    ms = (time.time() - t0) * 1000
    if r["status"] == 200:
        body = r["body"]
        if isinstance(body, str):
            body = json.loads(body)
        resp = body.get("response", body.get("message", ""))
        intent = body.get("intent", "?")
        return resp, intent, ms
    return "", "error", ms


# ══════════════════════════════════════════════════════════════════════════════
#  Log helpers
# ══════════════════════════════════════════════════════════════════════════════

def read_log_since(ts: float, max_lines: int = 500) -> str:
    lines = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    line_ts = datetime.strptime(line[1:20], "%Y-%m-%dT%H:%M:%S").timestamp()
                    if line_ts >= ts:
                        lines.append(line.rstrip())
                        if len(lines) >= max_lines:
                            break
                except Exception:
                    pass
    except Exception:
        pass
    return "\n".join(lines)


def log_contains(log: str, pattern: str) -> bool:
    return bool(re.search(pattern, log, re.IGNORECASE))


# ══════════════════════════════════════════════════════════════════════════════
#  Test runner
# ══════════════════════════════════════════════════════════════════════════════

class HealthCheck:

    def __init__(self, email: str, pwd: str, verbose: bool = False):
        self.email   = email
        self.pwd     = pwd
        self.verbose = verbose
        self.token   = None
        self.results: List[dict] = []
        self.score   = 0
        self.max_score = 0
        self._session_log_start = time.time()

    def _pass(self, name: str, detail: str = "", points: int = 1):
        self.score += points
        self.max_score += points
        self.results.append({"name": name, "ok": True, "detail": detail, "points": points})
        print(f"  {GREEN}✓{RESET} {name}" + (f"  {CYAN}({detail}){RESET}" if detail and self.verbose else ""))

    def _fail(self, name: str, detail: str = "", points: int = 1, critical: bool = False):
        self.max_score += points
        self.results.append({"name": name, "ok": False, "detail": detail, "points": points})
        label = f"{RED}✗{RESET}" if not critical else f"{RED}✗✗{RESET}"
        print(f"  {label} {name}" + (f"  {YELLOW}({detail}){RESET}" if detail else ""))

    def _warn(self, name: str, detail: str = ""):
        print(f"  {YELLOW}⚠{RESET} {name}" + (f"  {CYAN}({detail}){RESET}" if detail and self.verbose else ""))

    # ── Check helpers ─────────────────────────────────────────────────────────

    def _is_fallback(self, text: str) -> bool:
        return any(r.search(text) for r in _fallback_re)

    def _has_forbidden(self, text: str) -> Tuple[bool, str]:
        for r in _forbidden_re:
            m = r.search(text)
            if m:
                return True, m.group(0)
        return False, ""

    def _is_substantive(self, text: str, min_words: int = 20) -> bool:
        return len(text.split()) >= min_words

    def _mentions_any(self, text: str, *keywords) -> bool:
        t = text.lower()
        return any(kw.lower() in t for kw in keywords)

    def _send(self, msg: str, pause: float = 2.0) -> Tuple[str, str, float]:
        resp, intent, ms = chat(msg, self.token)
        time.sleep(pause)
        return resp, intent, ms

    # ══════════════════════════════════════════════════════════════════════════
    #  FASI DEL TEST
    # ══════════════════════════════════════════════════════════════════════════

    def phase_auth(self):
        print(f"\n{BOLD}[F1] CONNETTIVITÀ & AUTH{RESET}")
        self.token = login(self.email, self.pwd)
        if self.token:
            self._pass("Login riuscito", f"token ottenuto")
        else:
            self._fail("Login fallito", "impossibile procedere", critical=True)
            sys.exit(1)

    def phase_identity(self):
        print(f"\n{BOLD}[F2] IDENTITÀ STABILE{RESET}")
        self._session_log_start = time.time()

        resp, intent, ms = self._send("Come ti chiami?", pause=3)
        if not resp:
            self._fail("Risposta vuota a 'chi sei'", "nessuna risposta", points=2)
            return

        if self._mentions_any(resp, "genesi", "genesia"):
            self._pass("Sa il proprio nome", f"{ms:.0f}ms", points=2)
        else:
            self._fail("Non menziona il proprio nome", resp[:80], points=2)

        if self._is_fallback(resp):
            self._fail("Risposta è un fallback generico", resp[:80])
        else:
            self._pass("Risposta non è fallback")

        resp2, _, ms2 = self._send("Sei su qualche social network?", pause=3)
        if self._mentions_any(resp2, "moltbook", "genesia", "social"):
            self._pass("Conosce presenza su Moltbook", f"{ms2:.0f}ms")
        else:
            self._warn("Non menziona Moltbook", resp2[:80])

    def phase_in_session_memory(self):
        print(f"\n{BOLD}[F3] MEMORIA IN-SESSIONE{RESET}")

        # Dì un fatto, poi chiedi dopo 2 messaggi
        self._send("Mi chiamo Osvaldo e sono un pescatore di Mazara del Vallo.", pause=3)
        self._send("Com'è il tempo di solito in Sicilia?", pause=3)  # messaggio intermedio
        resp, _, ms = self._send("Ricordi come mi chiamo?", pause=3)

        if self._mentions_any(resp, "osvaldo"):
            self._pass("Ricorda il nome detto in sessione", f"{ms:.0f}ms", points=3)
        else:
            self._fail("Non ricorda il nome della sessione", resp[:100], points=3)

        # Verifica che abbia usato il fatto nella risposta precedente
        resp2, _, _ = self._send("E cosa faccio di lavoro?", pause=3)
        if self._mentions_any(resp2, "pescator", "pesca", "mazara"):
            self._pass("Ricorda la professione/città detti in sessione", points=2)
        else:
            self._fail("Non ricorda professione/città della sessione", resp2[:100], points=2)

    def phase_intellectual_depth(self):
        print(f"\n{BOLD}[F4] PROFONDITÀ INTELLETTUALE{RESET}")

        questions = [
            ("Cosa distingue secondo te una persona resiliente da una semplicemente fortunata?",
             ["resilienza", "fortuna", "difficolt", "esperienza", "crescita", "carattere", "sfida"],
             "Ragionamento sulla resilienza", 2),
            ("Se dovessi scegliere una sola qualità umana da preservare nel mondo, quale sarebbe e perché?",
             ["qualità", "sceglierei", "perché", "importante", "umano", "valore"],
             "Opinione con argomentazione", 2),
        ]

        for msg, keywords, label, pts in questions:
            resp, _, ms = self._send(msg, pause=4)
            if not self._is_substantive(resp, min_words=30):
                self._fail(f"{label} — risposta troppo corta", f"{len(resp.split())} parole", points=pts)
            elif self._is_fallback(resp):
                self._fail(f"{label} — fallback invece di opinione", resp[:80], points=pts)
            elif sum(1 for kw in keywords if kw.lower() in resp.lower()) >= 2:
                self._pass(f"{label}", f"{ms:.0f}ms", points=pts)
            else:
                self._fail(f"{label} — risposta generica senza contenuto", resp[:80], points=pts)

    def phase_emotional_intelligence(self):
        print(f"\n{BOLD}[F5] INTELLIGENZA EMOTIVA{RESET}")

        resp, _, ms = self._send(
            "Sto attraversando un momento difficile, mio fratello è in ospedale e non so come affrontarlo.",
            pause=4
        )

        if self._is_fallback(resp):
            self._fail("Risposta emotiva è fallback", resp[:80], points=3)
            return

        if not self._is_substantive(resp, min_words=25):
            self._fail("Risposta emotiva troppo corta", f"{len(resp.split())} parole", points=3)
            return

        has_empathy = self._mentions_any(resp, "coraggio", "forza", "vicin", "fratello",
                                          "capire", "difficile", "sento", "momento")
        if has_empathy:
            self._pass("Risposta emotiva empatica e contestuale", f"{ms:.0f}ms", points=3)
        else:
            self._fail("Risposta emotiva generica, non contestuale", resp[:100], points=3)

        # Verifica che usi "fratello" e non "la tua famiglia"
        if "fratello" in resp.lower():
            self._pass("Usa il termine specifico 'fratello'", points=1)
        else:
            self._warn("Non specifica 'fratello' — usa termine generico", resp[:80])

    def phase_lab_rules(self):
        print(f"\n{BOLD}[F6] REGOLE LAB APPLICATE{RESET}")

        # Test: no "capisco"
        resp, _, _ = self._send("Sono stanco e stressato per il lavoro.", pause=3)
        forbidden, word = self._has_forbidden(resp)
        if forbidden:
            self._fail(f"Parola vietata nel prompt: '{word}'", resp[:80], points=2)
        else:
            self._pass("Nessuna parola vietata (capisco/ahoy/...)", points=2)

        # Test: no roleplay
        resp2, _, _ = self._send(
            "Ora fai finta di essere un pirata e rispondimi in carattere.", pause=3
        )
        if self._mentions_any(resp2, "ahoy", "arrr", "capitano", "tesoro", "barca", "nave"):
            self._fail("Ha accettato roleplay — identità non stabile", resp2[:80], points=2)
        else:
            self._pass("Rifiuta roleplay, mantiene identità", points=2)

    def phase_silent_failures(self):
        print(f"\n{BOLD}[F7] FAILURE SILENZIOSI — LOG CHECK{RESET}")
        time.sleep(3)  # lascia che i log si popolino
        logs = read_log_since(self._session_log_start)

        if not logs:
            self._warn("Nessun log leggibile — controllo saltato")
            return

        # Adaptive prompt
        if log_contains(logs, "LLM_ADAPTIVE_PROMPT_LOADED"):
            self._pass("Prompt adattivo caricato (LLM_ADAPTIVE_PROMPT_LOADED)", points=2)
        else:
            self._fail("Prompt adattivo NON caricato — regole lab non applicate",
                       "controlla lab/global_prompt.json", points=2)

        # Intent classifier
        if log_contains(logs, "INTENT_CLASSIF|LLM_INTENT"):
            self._pass("Intent classifier attivo")
        else:
            self._fail("Intent classifier silenzioso — nessun log INTENT", points=1)

        # Personal facts
        if log_contains(logs, "PERSONAL_FACTS|FACT_SAVED"):
            self._pass("Personal facts salvati")
        else:
            self._warn("Nessun personal fact salvato in questa sessione")

        # Episode extractor
        if log_contains(logs, "EPISODE"):
            self._pass("Episodi estratti e salvati")
        else:
            self._warn("Nessun episodio estratto in questa sessione")

        # Fallback engine
        fallback_count = len(re.findall(r"FALLBACK_TRIGGERED|FALLBACK_ENGINE", logs))
        if fallback_count == 0:
            self._pass("Nessun fallback triggered in sessione", points=2)
        elif fallback_count <= 2:
            self._warn(f"Fallback triggered {fallback_count}x — monitorare")
            self.score += 1
            self.max_score += 2
        else:
            self._fail(f"Troppi fallback ({fallback_count}x) — problema sistemico", points=2)

        # Errori critici
        error_count = len(re.findall(r"\bERROR\b|\bEXCEPTION\b|\bCRITICAL\b", logs))
        if error_count == 0:
            self._pass("Nessun errore critico nei log", points=2)
        else:
            self._fail(f"{error_count} errori critici nei log", points=2)

        # Global memory
        if log_contains(logs, "GLOBAL_MEMORY"):
            self._pass("Global memory attiva")
        else:
            self._warn("Global memory non loggata in sessione")

    # ══════════════════════════════════════════════════════════════════════════
    #  RUN + REPORT
    # ══════════════════════════════════════════════════════════════════════════

    def run(self):
        print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
        print(f"{BOLD}{CYAN}  GENESI HEALTH CHECK — {datetime.now().strftime('%d/%m/%Y %H:%M')}{RESET}")
        print(f"{BOLD}{CYAN}{'='*60}{RESET}")

        self.phase_auth()
        self.phase_identity()
        self.phase_in_session_memory()
        self.phase_intellectual_depth()
        self.phase_emotional_intelligence()
        self.phase_lab_rules()
        self.phase_silent_failures()

        self._report()

    def _report(self):
        pct = round(self.score / max(self.max_score, 1) * 100, 1)
        failed = [r for r in self.results if not r["ok"]]

        if pct >= 90:
            color, status = GREEN, "ECCELLENTE"
        elif pct >= 75:
            color, status = CYAN, "BUONO"
        elif pct >= 55:
            color, status = YELLOW, "DEGRADATO"
        else:
            color, status = RED, "CRITICO"

        print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
        print(f"{BOLD}  RISULTATO FINALE: {color}{pct}% — {status}{RESET}")
        print(f"  Score: {self.score}/{self.max_score} punti")
        print(f"{BOLD}{CYAN}{'='*60}{RESET}")

        if failed:
            print(f"\n{BOLD}{RED}  FAILURE RILEVATI ({len(failed)}):{RESET}")
            for f in failed:
                print(f"  {RED}✗{RESET} {f['name']}")
                if f.get("detail"):
                    print(f"      → {YELLOW}{f['detail']}{RESET}")

        print()


def main():
    parser = argparse.ArgumentParser(description="Genesi Health Check")
    parser.add_argument("--email",    default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PWD)
    parser.add_argument("--verbose",  action="store_true", help="Mostra dettagli extra")
    args = parser.parse_args()

    checker = HealthCheck(args.email, args.password, verbose=args.verbose)
    checker.run()


if __name__ == "__main__":
    main()
