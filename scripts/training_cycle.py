#!/usr/bin/env python3
"""
GENESI TRAINING CYCLE
=====================
Esegue conversazioni di calibrazione con l'utente test, valuta le risposte
e crea correzioni/lessons nell'engine di training.

Le lessons attivate vengono iniettate nel contesto LLM per TUTTI gli utenti.

Uso:
    python3 scripts/training_cycle.py [--email EMAIL] [--password PWD] [--auto-lesson] [--dry-run]

Flag:
    --auto-lesson   Attiva automaticamente le corrections come lesson se la risposta
                    manca di elementi critici (non solo errata, ma migliorabile)
    --dry-run       Mostra cosa farebbe senza chiamare le API admin
"""

import argparse
import json
import sys
import os
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://localhost:8000"
DEFAULT_EMAIL    = "alfio.turrisi@gmail.com"
DEFAULT_PASSWORD = "ZOEennio0810"

# ════════════════════════════════════════════════════════════════
#  CASI DI CALIBRAZIONE
#  Struttura:
#    category     → una delle categorie del training engine
#    message      → messaggio inviato da utente
#    must_contain → keyword che la risposta DEVE contenere (AND logic)
#    must_not     → keyword che NON devono comparire
#    correct      → risposta modello da usare come correct_response in correction
#    admin_note   → nota per l'admin (spiega il comportamento atteso)
#    auto_lesson  → se True, attiva subito come lesson se correction creata
# ════════════════════════════════════════════════════════════════

CALIBRATION_CASES = [

    # ── STILE ────────────────────────────────────────────────────────────────
    {
        "category": "stile",
        "message": "come stai?",
        "must_contain": [],
        "must_not": ["capisco"],
        "correct": "Bene, grazie! E tu come stai oggi?",
        "admin_note": "Risposta al saluto: diretta, senza 'capisco'. Tono caldo ma conciso.",
        "auto_lesson": True,
    },
    {
        "category": "stile",
        "message": "sei davvero utile",
        "must_contain": [],
        "must_not": ["capisco", "mi dispiace"],
        "correct": "Sono qui per questo! Se hai altro di cui hai bisogno, dimmi pure.",
        "admin_note": "Complimento ricevuto: risposta positiva e propositiva, senza eccessive umiltà.",
        "auto_lesson": False,
    },

    # ── IDENTITÀ UTENTE ───────────────────────────────────────────────────────
    {
        "category": "identita",
        "message": "come mi chiamo?",
        "must_contain": ["alfio"],
        "must_not": ["non so", "non ricordo", "non conosco"],
        "correct": "Ti chiami Alfio.",
        # NON auto_lesson: la risposta contiene il nome specifico dell'utente test,
        # non può diventare una lesson globale (andrebbe iniettata per tutti gli utenti).
        "admin_note": "Deve sempre ricordare il nome dell'utente dal profilo. NOTA: non attivare come lesson globale — contiene nome specifico.",
        "auto_lesson": False,
    },
    {
        "category": "identita",
        "message": "dove vivo?",
        "must_contain": [],
        "must_not": ["non so", "non ricordo"],
        "correct": "Vivi a Catania, stando a quello che mi hai detto.",
        "admin_note": "Deve rispondere con la città dal profilo, se disponibile. NOTA: non attivare come lesson globale — contiene dati specifici.",
        "auto_lesson": False,
    },

    # ── MEMORIA / EPISODI ─────────────────────────────────────────────────────
    {
        "category": "memoria",
        "message": "ricordi qualcosa di importante che ti ho detto?",
        "must_contain": [],
        "must_not": ["non ho memoria", "non ricordo nulla", "non posso ricordare"],
        "correct": (
            "Sì, ho alcune cose in memoria: quello che mi hai raccontato nel tempo "
            "è conservato nei miei episodi personali. Se vuoi possiamo ripercorrerli."
        ),
        "admin_note": "Non deve negare di avere memoria. Deve confermare che i ricordi esistono.",
        "auto_lesson": True,
    },
    {
        "category": "memoria",
        "message": "cosa sai di me?",
        "must_contain": [],
        "must_not": ["non so nulla di te", "non ho informazioni"],
        "correct": (
            "Ho alcune cose in memoria: nel tempo hai condiviso con me abitudini, "
            "pensieri e momenti importanti. Vuoi che te li ricordi?"
        ),
        "admin_note": "Deve affermare di avere informazioni, anche se scarse. Non negare la memoria.",
        "auto_lesson": True,
    },

    # ── RISPOSTA EMOTIVA ──────────────────────────────────────────────────────
    {
        "category": "emozione",
        "message": "sono molto stressato oggi",
        "must_contain": [],
        "must_not": ["capisco", "mi dispiace sentirti"],
        "correct": (
            "Sento che è una giornata pesante. Cosa sta succedendo? "
            "A volte aiuta anche solo condividere."
        ),
        "admin_note": "Risposta emotiva: empatica, senza 'capisco'. Invita a raccontare.",
        "auto_lesson": True,
    },
    {
        "category": "emozione",
        "message": "sono felice oggi!",
        "must_contain": [],
        "must_not": ["capisco"],
        "correct": "Ottimo! Cosa sta andando bene? Raccontami.",
        "admin_note": "Emozione positiva: risposta entusiasta e curiosa, non piatta.",
        "auto_lesson": True,
    },
    {
        "category": "emozione",
        "message": "mia madre sta male, sono preoccupato",
        "must_contain": ["coraggio"],
        "must_not": ["capisco"],
        "correct": (
            "Coraggio. È sempre duro vedere una madre soffrire. "
            "Sono qui se vuoi parlarne."
        ),
        "admin_note": "Crisi familiare: DEVE contenere 'coraggio' + termine familiare (madre/padre ecc.). Non usare 'capisco'.",
        "auto_lesson": True,
    },

    # ── FATTO ERRATO ──────────────────────────────────────────────────────────
    {
        "category": "fatto",
        "message": "quanti giorni ha febbraio in un anno bisestile?",
        "must_contain": ["29"],
        "must_not": ["28"],
        "correct": "Febbraio in un anno bisestile ha 29 giorni.",
        "admin_note": "Fatto preciso: risposta con numero esplicito.",
        "auto_lesson": False,
    },

    # ── INTENT SBAGLIATO ─────────────────────────────────────────────────────
    {
        "category": "intent",
        "message": "dimmi una barzelletta",
        "must_contain": [],
        "must_not": ["non posso", "non sono in grado", "mi dispiace"],
        "correct": (
            "Eccone una: perché i pesci non vanno in palestra? "
            "Perché hanno paura dell'amo degli bilancieri! 😄"
        ),
        "admin_note": "Richiesta creativa: deve rispondere, non rifiutare.",
        "auto_lesson": False,
    },
    {
        "category": "intent",
        "message": "che ore sono?",
        "must_contain": [],
        "must_not": ["non posso", "non ho accesso"],
        "correct": "Non ho un orologio preciso, ma puoi controllare in alto a destra del tuo schermo! 😄",
        "admin_note": "Richiesta orario: ammette il limite con leggerezza, non nega seccamente.",
        "auto_lesson": False,
    },
]


# ════════════════════════════════════════════════════════════════
#  RUNNER
# ════════════════════════════════════════════════════════════════

@dataclass
class CaseResult:
    case: Dict
    response: str
    passed: bool
    issues: List[str] = field(default_factory=list)
    correction_id: Optional[str] = None
    lesson_activated: bool = False
    latency_ms: float = 0.0


class TrainingCycleRunner:
    def __init__(self, email: str, password: str, auto_lesson: bool, dry_run: bool,
                 admin_email: str = "", admin_password: str = ""):
        self.email          = email
        self.password       = password
        self.admin_email    = admin_email or email
        self.admin_password = admin_password or password
        self.auto_lesson    = auto_lesson
        self.dry_run        = dry_run
        self.token:        Optional[str] = None
        self.admin_token:  Optional[str] = None

    # ── HTTP helpers (stdlib only) ────────────────────────────────────────────

    def _request(self, method: str, url: str, payload=None, params=None, token=None):
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode()
                return r.status, body
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    # ── Auth ─────────────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> str:
        status, body = self._request("POST", f"{BASE_URL}/auth/login",
                                     payload={"email": email, "password": password})
        if status != 200:
            raise RuntimeError(f"Login fallito per {email}: HTTP {status}")
        return json.loads(body)["access_token"]

    # ── Chat ─────────────────────────────────────────────────────────────────

    def send_message(self, message: str):
        t0 = time.time()
        status, body = self._request("POST", f"{BASE_URL}/api/chat/",
                                     payload={"message": message}, token=self.token)
        latency = (time.time() - t0) * 1000
        if status != 200:
            raise RuntimeError(f"Chat error HTTP {status}: {body[:200]}")
        data = json.loads(body)
        text = data.get("response") or data.get("message") or data.get("text") or ""
        return text.strip(), latency

    # ── Training API ─────────────────────────────────────────────────────────

    def create_correction(self, input_message, bad_response, correct_response,
                          category, admin_note) -> Optional[str]:
        payload = {
            "input_message":    input_message,
            "bad_response":     bad_response,
            "correct_response": correct_response,
            "category":         category,
            "admin_note":       admin_note,
            "user_id":          self.email,
        }
        status, body = self._request("POST",
                                     f"{BASE_URL}/api/admin/training/corrections",
                                     payload=payload, token=self.admin_token)
        if status != 200:
            raise RuntimeError(f"Correction API error {status}: {body[:200]}")
        return json.loads(body).get("correction", {}).get("id")

    def activate_lesson(self, correction_id: str) -> bool:
        status, _ = self._request(
            "PATCH",
            f"{BASE_URL}/api/admin/training/corrections/{correction_id}/lesson",
            params={"active": "true"}, token=self.admin_token)
        return status == 200

    def save_snapshot(self) -> bool:
        status, _ = self._request("POST",
                                  f"{BASE_URL}/api/admin/training/metrics/snapshot",
                                  token=self.admin_token)
        return status == 200

    # ── Evaluation ───────────────────────────────────────────────────────────

    def evaluate(self, case: Dict, response: str) -> List[str]:
        """Ritorna lista di issue. Lista vuota = risposta OK."""
        issues = []
        resp_lower = response.lower()

        for kw in case.get("must_contain", []):
            if kw.lower() not in resp_lower:
                issues.append(f"MANCANTE: '{kw}'")

        for kw in case.get("must_not", []):
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', resp_lower):
                issues.append(f"VIETATO: '{kw}'")

        return issues

    # ── Main cycle ───────────────────────────────────────────────────────────

    def run(self):
        print(f"\n{'═'*62}")
        print(f"  GENESI TRAINING CYCLE — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"  Utente test : {self.email}")
        print(f"  Auto-lesson : {self.auto_lesson}")
        print(f"  Dry-run     : {self.dry_run}")
        print(f"{'═'*62}\n")

        # Auth utente test
        print("▶ Login utente test…")
        self.token = self.login(self.email, self.password)
        print("  ✓ Token utente ottenuto")

        # Auth admin (credenziali separate se fornite)
        print("▶ Login admin…")
        if self.admin_email != self.email:
            self.admin_token = self.login(self.admin_email, self.admin_password)
            print(f"  ✓ Token admin ottenuto ({self.admin_email})")
        else:
            self.admin_token = self.token
        status, _ = self._request("GET", f"{BASE_URL}/api/admin/training/metrics",
                                  token=self.admin_token)
        if status == 403:
            print("  ✗ Utente non admin. Usa --admin-email e --admin-password con l'account admin.")
            sys.exit(1)
        elif status != 200:
            print(f"  ✗ Admin check failed: HTTP {status}")
            sys.exit(1)
        print("  ✓ Token admin valido\n")

        # Ciclo calibrazione
        results: List[CaseResult] = []
        for i, case in enumerate(CALIBRATION_CASES, 1):
            msg = case["message"]
            cat = case["category"]
            print(f"[{i:02d}/{len(CALIBRATION_CASES):02d}] [{cat.upper():8s}] {msg}")

            try:
                resp_text, latency = self.send_message(msg)
            except Exception as e:
                print(f"         ✗ Errore chat: {e}")
                results.append(CaseResult(case=case, response="", passed=False,
                                          issues=[f"Chat error: {e}"]))
                continue

            issues = self.evaluate(case, resp_text)
            passed = len(issues) == 0
            cr = CaseResult(case=case, response=resp_text,
                            passed=passed, issues=issues, latency_ms=latency)

            if passed:
                print(f"         ✓ OK  ({latency:.0f}ms)")
            else:
                print(f"         ✗ FAIL ({latency:.0f}ms)")
                for iss in issues:
                    print(f"           → {iss}")
                preview = resp_text[:120] + ("…" if len(resp_text) > 120 else "")
                print(f"         Risposta: {preview}")

                if not self.dry_run:
                    try:
                        cid = self.create_correction(
                            input_message=msg,
                            bad_response=resp_text,
                            correct_response=case["correct"],
                            category=cat,
                            admin_note=case["admin_note"],
                        )
                        cr.correction_id = cid
                        print(f"         📝 Correction creata: {cid}")

                        if (self.auto_lesson and case.get("auto_lesson", False)) and cid:
                            ok = self.activate_lesson(cid)
                            cr.lesson_activated = ok
                            if ok:
                                print(f"         🎓 Lesson attivata  → effetto GLOBALE")
                    except Exception as e:
                        print(f"         ✗ Training API error: {e}")
                else:
                    print(f"         [DRY-RUN] avrebbe creato correction in '{cat}'")
                    if self.auto_lesson and case.get("auto_lesson"):
                        print(f"         [DRY-RUN] avrebbe attivato come lesson globale")

            results.append(cr)
            time.sleep(0.8)

        # Snapshot metriche
        if not self.dry_run:
            print("\n▶ Salvataggio snapshot metriche…")
            ok = self.save_snapshot()
            print("  ✓ Snapshot salvato" if ok else "  ✗ Snapshot fallito")

        self._print_report(results)

    def _print_report(self, results: List[CaseResult]):
        total     = len(results)
        passed    = sum(1 for r in results if r.passed)
        failed    = total - passed
        n_corr    = sum(1 for r in results if r.correction_id)
        n_lessons = sum(1 for r in results if r.lesson_activated)

        avg_lat = (
            sum(r.latency_ms for r in results if r.latency_ms > 0)
            / max(1, sum(1 for r in results if r.latency_ms > 0))
        )

        print(f"\n{'═'*62}")
        print(f"  REPORT TRAINING CYCLE")
        print(f"{'─'*62}")
        print(f"  Casi totali   : {total}")
        print(f"  ✓ Superati    : {passed}  ({100*passed//max(total,1)}%)")
        print(f"  ✗ Falliti     : {failed}")
        print(f"  📝 Corrections: {n_corr}")
        print(f"  🎓 Lessons    : {n_lessons}  (attive → effetto globale)")
        print(f"  ⏱  Latenza avg: {avg_lat:.0f}ms")

        if failed > 0:
            print(f"\n  Casi da migliorare:")
            for r in results:
                if not r.passed:
                    cat = r.case["category"].upper()
                    msg = r.case["message"][:45]
                    print(f"    [{cat:8s}] {msg}")
                    for iss in r.issues:
                        print(f"              → {iss}")

        score_pct = int(100 * passed / max(total, 1))
        if score_pct == 100:
            verdict = "🟢 OTTIMO — Genesi risponde correttamente a tutti i criteri"
        elif score_pct >= 75:
            verdict = "🟡 BUONO — Alcune aree da migliorare, lessons create"
        elif score_pct >= 50:
            verdict = "🟠 SUFFICIENTE — Molte corrections necessarie"
        else:
            verdict = "🔴 CRITICO — Richiede intervento sul prompt/sistema"

        print(f"\n  {verdict}")
        print(f"{'═'*62}\n")

        if not self.dry_run and score_pct < 100:
            print(f"  ℹ  Apri /training-admin per gestire corrections e lessons.\n")


# ════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Genesi Training Cycle")
    parser.add_argument("--email",          default=DEFAULT_EMAIL,    help="Email utente test (chat)")
    parser.add_argument("--password",       default=DEFAULT_PASSWORD, help="Password utente test")
    parser.add_argument("--admin-email",    default="",               help="Email account admin (se diverso da --email)")
    parser.add_argument("--admin-password", default="",               help="Password account admin")
    parser.add_argument("--auto-lesson",    action="store_true",
                        help="Attiva automaticamente lessons per i casi falliti con auto_lesson=True")
    parser.add_argument("--dry-run",        action="store_true",
                        help="Non chiama API admin, mostra solo cosa farebbe")
    args = parser.parse_args()

    runner = TrainingCycleRunner(
        email=args.email,
        password=args.password,
        admin_email=args.admin_email,
        admin_password=args.admin_password,
        auto_lesson=args.auto_lesson,
        dry_run=args.dry_run,
    )
    runner.run()


if __name__ == "__main__":
    main()
