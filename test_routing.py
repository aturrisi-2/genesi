#!/usr/bin/env python3
"""
test_routing.py — Test conversazionale approfondito di Genesi.

Verifica che il routing sia context-aware e non cada in falsi positivi
da keyword matching. Spremia il sistema alla ricerca di vulnerabilità.

Uso:
    python3 test_routing.py email@example.com password

Eseguire direttamente sul VPS (usa localhost:8000).
"""

import sys
import json
import time
import subprocess
import datetime
import requests
from typing import Optional

# ── CONFIG ─────────────────────────────────────────────────────
BASE_URL = "http://localhost:8000"
EMAIL    = sys.argv[1] if len(sys.argv) > 1 else ""
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else ""
# ───────────────────────────────────────────────────────────────

R = "\033[0m"
G = "\033[92m"
RE = "\033[91m"
Y  = "\033[93m"
B  = "\033[1m"
C  = "\033[96m"
D  = "\033[2m"

results = []


# ── API HELPERS ─────────────────────────────────────────────────

def login() -> str:
    r = requests.post(f"{BASE_URL}/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=10)
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        raise ValueError(f"Token non trovato: {data}")
    return token


def send_message(token: str, message: str) -> tuple[str, str]:
    """Invia messaggio SSE, restituisce (testo_risposta, source)."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
    chunks, source = [], ""
    try:
        with requests.post(f"{BASE_URL}/api/chat",
                           json={"message": message},
                           headers=headers, stream=True, timeout=35) as resp:
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload:
                    continue
                try:
                    obj = json.loads(payload)
                    if obj.get("text"):
                        chunks.append(obj["text"])
                    if obj.get("done"):
                        source = obj.get("source", "")
                except Exception:
                    pass
    except Exception as e:
        return f"[ERRORE: {e}]", "error"
    return "".join(chunks), source


def get_logs(since: datetime.datetime) -> str:
    """Legge log systemd del servizio genesi dal timestamp dato."""
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    try:
        r = subprocess.run(
            ["journalctl", "-u", "genesi.service",
             "--since", since_str, "--no-pager", "-n", "60", "--output=short"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout
    except Exception:
        return ""


def parse_routing(logs: str) -> dict:
    """Estrae intent e routing decision dai log."""
    info = {"route": None, "intent": None, "engine": None, "lines": []}
    for line in logs.splitlines():
        if "ROUTING_DECISION" in line:
            info["lines"].append(line.strip())
            for part in line.split():
                if part.startswith("route="):
                    info["route"] = part.split("=", 1)[1]
        if "INTENT_CLASSIFIED" in line:
            info["lines"].append(line.strip())
            for part in line.split():
                if part.startswith("intent="):
                    info["intent"] = part.split("=", 1)[1]
                if part.startswith("engine="):
                    info["engine"] = part.split("=", 1)[1]
        if "LLM_INTENT_CLASSIFICATION" in line:
            info["lines"].append(line.strip())
    return info


# ── TEST RUNNER ─────────────────────────────────────────────────

def run(token: str, name: str, message: str,
        must_not: list[str] = None, must_be: list[str] = None,
        ctx: list[str] = None, note: str = "") -> dict:
    """
    Esegue un singolo test.
    must_not: lista di route/intent che NON devono comparire.
    must_be:  lista di route/intent di cui ALMENO UNO deve comparire.
    ctx:      messaggi precedenti da inviare per creare contesto.
    """
    # Costruisci contesto conversazionale
    if ctx:
        for cm in ctx:
            send_message(token, cm)
            time.sleep(1.2)

    ts = datetime.datetime.now()
    time.sleep(0.2)

    response, source = send_message(token, message)
    time.sleep(0.8)

    logs = get_logs(ts)
    info = parse_routing(logs)

    actual = info["intent"] or info["route"] or source or "?"

    # Valuta
    passed = True
    fail_reason = ""

    if must_not:
        for bad in must_not:
            if bad in (info["route"] or "") or bad in (info["intent"] or ""):
                passed = False
                fail_reason = f"route '{bad}' NON attesa — trovata"
                break

    if must_be and passed:
        ok = any(
            g in (info["route"] or "") or g in (info["intent"] or "") or g in (source or "")
            for g in must_be
        )
        if not ok:
            passed = False
            fail_reason = f"nessuno di {must_be} trovato — actual={actual}"

    results.append({
        "name": name, "passed": passed, "actual": actual,
        "source": source, "engine": info["engine"],
        "response": response[:150].replace("\n", " "),
        "fail_reason": fail_reason, "note": note
    })

    icon = f"{G}✓{R}" if passed else f"{RE}✗{R}"
    eng = f" [{D}{info['engine']}{R}]" if info["engine"] else ""
    print(f"  {icon} {name}")
    print(f"      MSG : {D}{message[:75]}{R}")
    print(f"      ROUTE: {C}{actual}{R}{eng}")
    if not passed:
        print(f"      {RE}FAIL : {fail_reason}{R}")
        if response and "[ERRORE" not in response:
            print(f"      RESP : {D}{response[:120]}{R}")
    if note:
        print(f"      NOTE : {D}{note}{R}")
    print()

    return results[-1]


def section(title: str):
    print(f"\n{B}{C}{'═'*62}{R}")
    print(f"{B}{C}  {title}{R}")
    print(f"{B}{C}{'═'*62}{R}\n")


# ── TEST SUITE ──────────────────────────────────────────────────

def main():
    if not EMAIL or not PASSWORD:
        print(f"{RE}Uso: python3 test_routing.py email password{R}")
        sys.exit(1)

    print(f"\n{B}Genesi — Test Routing Conversazionale{R}")
    print(f"  VPS: {BASE_URL} | Utente: {EMAIL}\n")

    try:
        token = login()
        print(f"{G}✓ Login OK{R}\n")
    except Exception as e:
        print(f"{RE}✗ Login fallito: {e}{R}")
        sys.exit(1)

    # ────────────────────────────────────────────────────────────
    section("GRUPPO 1 — Falsi positivi identity (regressioni classiche)")
    # ────────────────────────────────────────────────────────────

    run(token, "F1 qualifiche → NON identity",
        "come sono andate le qualifiche di formula 1 ieri?",
        must_not=["identity"],
        note="'come sono' NON deve triggerare identity route")

    run(token, "Piloti griglia → NON identity",
        "chi sono i piloti in griglia oggi?",
        must_not=["identity"],
        note="'chi sono' riferito a terzi ≠ profilo utente")

    run(token, "Previsioni meteo → NON identity",
        "come sono le previsioni per il weekend?",
        must_not=["identity"],
        note="'come sono' + meteo = weather, non identity")

    run(token, "Prezzi supermercato → NON identity",
        "come sono i prezzi al supermercato ultimamente?",
        must_not=["identity"],
        note="domanda economica, non profilo utente")

    run(token, "Governo ultime news → NON identity",
        "come sono messe le cose con il governo?",
        must_not=["identity"],
        note="argomento politico, non dati dell'utente")

    run(token, "Scarpe comprate → NON identity",
        "come sono queste scarpe che ho comprato ieri?",
        must_not=["identity"],
        note="giudizio estetico su oggetto, non profilo")

    run(token, "Personaggi storici → NON identity",
        "chi sono stati i grandi condottieri della storia?",
        must_not=["identity"],
        note="domanda storica, 'chi sono stati' ≠ profilo utente")

    run(token, "Cosa faccio stasera → NON identity",
        "cosa faccio stasera?",
        must_not=["identity"],
        note="domanda sui piani, non su dati del profilo")

    run(token, "Mia cugina chi è → NON identity",
        "lo sai chi è mia cugina? lavora in ospedale",
        must_not=["identity"],
        note="info su terze persone, non su utente")

    # ────────────────────────────────────────────────────────────
    section("GRUPPO 2 — Identity corretta (non deve rompersi)")
    # ────────────────────────────────────────────────────────────

    run(token, "Come mi chiamo → identity",
        "come mi chiamo?",
        must_be=["identity"])

    run(token, "Dove vivo → identity",
        "dove vivo?",
        must_be=["identity"])

    run(token, "Che lavoro faccio → identity",
        "che lavoro faccio?",
        must_be=["identity"])

    run(token, "Cosa sai di me → identity",
        "cosa sai di me?",
        must_be=["identity"])

    run(token, "Ho figli → identity",
        "ho figli?",
        must_be=["identity"])

    run(token, "Quanti anni ho → identity",
        "quanti anni ho?",
        must_be=["identity"])

    run(token, "Come si chiama mia moglie → identity",
        "come si chiama mia moglie?",
        must_be=["identity"])

    # ────────────────────────────────────────────────────────────
    section("GRUPPO 3 — Falsi positivi dove_sono")
    # ────────────────────────────────────────────────────────────

    run(token, "Gare F1 dove → NON dove_sono",
        "dove sono state le gare di F1 quest'anno?",
        must_not=["dove_sono"],
        note="posizione di un evento ≠ posizione dell'utente")

    run(token, "Dove sono andati gli amici → NON dove_sono",
        "dove sono andati tutti i miei amici stasera?",
        must_not=["dove_sono"],
        note="terze persone, non posizione utente")

    run(token, "Dove sono le chiavi → NON dove_sono",
        "dove sono le chiavi di casa?",
        must_not=["dove_sono"],
        note="oggetto fisico, non posizione utente")

    run(token, "Dove siamo col progetto → NON dove_sono",
        "dove siamo con il progetto?",
        must_not=["dove_sono"],
        note="metafora di avanzamento, non GPS")

    run(token, "Dove sono stati miei nonni → NON dove_sono",
        "dove sono stati i miei nonni a vivere?",
        must_not=["dove_sono"],
        note="storia familiare, non posizione attuale utente")

    run(token, "Dove mi trovo → dove_sono (corretto)",
        "dove mi trovo adesso?",
        must_be=["dove_sono"],
        note="esplicita posizione 1a persona = dove_sono")

    # ────────────────────────────────────────────────────────────
    section("GRUPPO 4 — Routing contestuale multi-turno")
    # ────────────────────────────────────────────────────────────

    run(token, "[CTX F1] dimmelo tu → NON news",
        "dimmelo tu",
        must_not=["news"],
        ctx=["sai com'è andata la gara di F1 domenica scorsa?"],
        note="imperativo a Genesi dopo F1 = chat_free, non cercare news")

    run(token, "[CTX F1] chi ha vinto → NON identity",
        "chi ha vinto alla fine?",
        must_not=["identity"],
        ctx=["parliamo di Formula 1, ultima gara"],
        note="follow-up gara, 'chi ha vinto' ≠ chi è l'utente")

    run(token, "[CTX meteo] e domani? → weather",
        "e domani?",
        must_be=["weather"],
        ctx=["che tempo fa oggi a Roma?"],
        note="ellittico weather deve ereditare contesto")

    run(token, "[CTX news sport] e la F1? → NON identity",
        "e la F1?",
        must_not=["identity", "dove_sono"],
        ctx=["dammi le ultime notizie di sport"],
        note="follow-up sport, non identity")

    run(token, "[CTX F1] dove sono state → NON dove_sono",
        "dove sono state quest'anno le gare più belle?",
        must_not=["dove_sono"],
        ctx=["parliamo di Formula 1"],
        note="con contesto F1 = geo eventi, non GPS utente")

    run(token, "[CTX identità] io non ti ho detto → memory_correction",
        "no aspetta, ti ho detto che lavoro in banca non come ingegnere",
        must_be=["memory_correction"],
        ctx=["che lavoro faccio?"],
        note="correzione dopo identity = memory_correction")

    # ────────────────────────────────────────────────────────────
    section("GRUPPO 5 — Memory correction")
    # ────────────────────────────────────────────────────────────

    run(token, "Correzione professione esplicita → memory_correction",
        "in realtà non lavoro come ingegnere, sono un medico",
        must_be=["memory_correction"])

    run(token, "Hai sbagliato nome → memory_correction",
        "hai sbagliato, non mi chiamo così",
        must_be=["memory_correction"])

    run(token, "Non ho un cane → memory_correction",
        "non ho un cane, ho una gatta che si chiama Luna",
        must_be=["memory_correction"])

    run(token, "Non vivo più a → memory_correction",
        "non vivo più a Milano, mi sono trasferito a Bologna",
        must_be=["memory_correction"])

    # ────────────────────────────────────────────────────────────
    section("GRUPPO 6 — Trappole emotive e relazionali")
    # ────────────────────────────────────────────────────────────

    run(token, "Sono stressato → NON identity",
        "sono stressato dal lavoro ultimamente",
        must_not=["identity", "weather", "news"],
        note="contenuto emotivo → relational/emotional")

    run(token, "Mi sento giù → NON identity",
        "mi sento un po' giù oggi, non so perché",
        must_not=["identity"],
        note="stato d'animo → emotional/relational")

    run(token, "Che ne pensi del freddo → NON weather",
        "che ne pensi di questo freddo di questi giorni?",
        must_not=["weather"],
        note="opinione di Genesi, non richiesta dati meteo")

    run(token, "Ti piace il calcio → NON news/sport",
        "ti piace il calcio?",
        must_not=["news", "weather", "identity"],
        note="domanda relazionale/opinione, non tool")

    # ────────────────────────────────────────────────────────────
    section("GRUPPO 7 — Tool routing corretto (baseline)")
    # ────────────────────────────────────────────────────────────

    run(token, "Meteo Milano → weather",
        "che tempo fa a Milano?",
        must_be=["weather"])

    run(token, "Notizie Serie A → news",
        "ultime notizie di calcio serie A",
        must_be=["news"])

    run(token, "Che ore sono → time",
        "che ore sono?",
        must_be=["time"])

    run(token, "Che giorno è → date",
        "che giorno è oggi?",
        must_be=["date"])

    run(token, "Ricordami dentista → reminder_create",
        "ricordami di chiamare il dentista domani mattina",
        must_be=["reminder_create"])

    run(token, "I miei impegni → reminder_list",
        "quali sono i miei impegni di questa settimana?",
        must_be=["reminder_list"])

    # ────────────────────────────────────────────────────────────
    section("GRUPPO 8 — Messaggi brevi e ambigui")
    # ────────────────────────────────────────────────────────────

    run(token, "'ok' → NON tool/identity",
        "ok",
        must_not=["identity", "dove_sono", "news", "weather", "memory_correction"])

    run(token, "'grazie' → chat_free",
        "grazie mille",
        must_not=["identity", "weather", "news"])

    run(token, "'davvero?' → NON tool",
        "davvero?",
        must_not=["identity", "weather", "news", "dove_sono"])

    run(token, "'non ci credo' → NON tool",
        "non ci credo",
        must_not=["identity", "memory_correction", "weather"])

    run(token, "'interessante' → chat_free",
        "interessante",
        must_not=["identity", "weather", "news", "memory_correction"])

    run(token, "'certo' → NON identity",
        "certo, vai avanti",
        must_not=["identity"])

    # ────────────────────────────────────────────────────────────
    section("GRUPPO 9 — Vulnerabilità avanzate")
    # ────────────────────────────────────────────────────────────

    run(token, "Quanti anni ha Ronaldo → NON identity",
        "quanti anni ha Cristiano Ronaldo?",
        must_not=["identity"],
        note="'quanti anni ha' riferito a terzi ≠ profilo utente")

    run(token, "Come si chiama il presidente → NON identity",
        "come si chiama il presidente della Repubblica?",
        must_not=["identity"],
        note="'come si chiama' riferito a figura pubblica")

    run(token, "Dove abita Musk → NON dove_sono",
        "dove abita Elon Musk?",
        must_not=["dove_sono"],
        note="luogo di residenza di terzo = chat_free/tecnica")

    run(token, "Ho comprato qualcosa → NON memory_correction",
        "ho comprato una macchina nuova",
        must_not=["memory_correction"],
        note="info nuova ≠ correzione di dato sbagliato")

    run(token, "Mio figlio ha preso la patente → NON identity",
        "mio figlio ha preso la patente ieri!",
        must_not=["identity"],
        note="notizia familiare = relational/chat_free, non query su profilo")

    run(token, "[CTX: 'ho un problema'] come mi chiamo → identity",
        "come mi chiamo?",
        must_be=["identity"],
        ctx=["ho un problema con il mio laptop"],
        note="identity deve funzionare anche con contesto diverso")

    run(token, "Cosa mi hai detto prima → memory_context",
        "cosa mi hai detto prima riguardo a questo?",
        must_be=["memory_context"],
        note="riferimento esplicito a conversazione precedente")

    run(token, "Ricordi quella cosa → NON weather/news",
        "ti ricordi quella cosa di cui abbiamo parlato ieri?",
        must_not=["weather", "news", "identity"],
        note="riferimento memoria conversazionale")

    # ────────────────────────────────────────────────────────────
    # RIEPILOGO FINALE
    # ────────────────────────────────────────────────────────────
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    print(f"\n{B}{'═'*62}{R}")
    print(f"{B}  RIEPILOGO FINALE{R}")
    print(f"{'═'*62}")
    print(f"  Totale : {total}")
    print(f"  {G}Passati: {passed}{R}")
    print(f"  {RE}Falliti: {failed}{R}")
    print(f"{'═'*62}\n")

    if failed:
        print(f"{B}{RE}TEST FALLITI:{R}")
        for r in results:
            if not r["passed"]:
                print(f"  {RE}✗{R} {r['name']}")
                print(f"      Route effettiva : {C}{r['actual']}{R}")
                print(f"      Motivo fallimento: {r['fail_reason']}")
                if r["note"]:
                    print(f"      Note            : {D}{r['note']}{R}")
                if r["response"] and "[ERRORE" not in r["response"]:
                    print(f"      Risposta        : {D}{r['response'][:120]}{R}")
                print()
    else:
        print(f"{G}{B}  Tutti i test passati! ✓{R}\n")

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
