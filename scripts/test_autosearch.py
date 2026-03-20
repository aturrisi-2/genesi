#!/usr/bin/env python3
"""
Test autonomo per la funzionalità di ricerca web automatica.
Verifica che Genesia cerchi online autonomamente quando non ha la risposta.
Utente: alfio.turrisi@gmail.com / ZOEennio0810
"""
import asyncio
import aiohttp
import json
import time
import sys
import os

# Fix Windows encoding per caratteri speciali (°, à, è, ecc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "https://genesi.lucadigitale.eu"
EMAIL = "alfio.turrisi@gmail.com"
PASSWORD = "ZOEennio0810"

ANSI_GREEN  = "\033[92m"
ANSI_RED    = "\033[91m"
ANSI_YELLOW = "\033[93m"
ANSI_CYAN   = "\033[96m"
ANSI_RESET  = "\033[0m"
ANSI_BOLD   = "\033[1m"

def ok(msg): print(f"{ANSI_GREEN}[OK]{ANSI_RESET} {msg}")
def fail(msg): print(f"{ANSI_RED}[FAIL]{ANSI_RESET} {msg}")
def info(msg): print(f"{ANSI_CYAN}[INFO]{ANSI_RESET} {msg}")
def warn(msg): print(f"{ANSI_YELLOW}[WARN]{ANSI_RESET} {msg}")
def header(msg): print(f"\n{ANSI_BOLD}{ANSI_CYAN}{'='*60}{ANSI_RESET}\n{ANSI_BOLD}{msg}{ANSI_RESET}\n{'='*60}")


async def login(session) -> str:
    async with session.post(f"{BASE_URL}/auth/login",
                            json={"email": EMAIL, "password": PASSWORD}) as r:
        data = await r.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            raise RuntimeError(f"Login fallito: {data}")
        info(f"Login OK — token: {token[:20]}...")
        return token


async def send_message(session, token: str, message: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    async with session.post(
        f"{BASE_URL}/api/chat",
        json={"message": message},
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=45)
    ) as r:
        data = await r.json()
        return data


# Frasi di rifiuto — se presenti = auto_search non ha funzionato
REFUSAL_PHRASES = [
    "non posso cercare sul web",
    "non ho accesso a internet",
    "ti consiglio di cercare",
    "ti consiglio di verificare su",
    "non ho informazioni in tempo reale",
    "non ho accesso alle ultime notizie",
    "non posso fare ricerche online",
    "puoi controllare su",
    "non sono in grado di cercare",
    "non ho informazioni aggiornate",
    "non riesco ad accedere",
    "al momento non riesco",
    "ti suggerisco di consultare",
    "ti consiglio di controllare",
    "ti consiglio di consultare",
    "non ho dati aggiornati",
    "non ho informazioni recenti",
    "suggerisco di verificare",
]

# Segnali che indicano una risposta REALE con dati trovati online
# Questi NON devono essere parole che appaiono nella domanda stessa
REAL_ANSWER_SIGNALS = [
    "secondo", "fonte", "riportato", "ho trovato", "stando a",
    "d'accordo con", "risulta che", "emerge che", "si apprende che",
    "news", "articolo", "aggiornamento recente",
]

# Test cases: (label, messaggio, segnali_che_indicano_risposta_reale_opzionali)
TEST_CASES = [
    (
        "T1 - Notizie guerra (topic corrente)",
        "Quali sono le ultime notizie sulla guerra?",
        # Segnali reali: attributions oppure named entities specifici di notizie correnti
        REAL_ANSWER_SIGNALS + [
            "ucraina", "russia", "nato", "usa", "trump", "zelensky", "putin",
            "missili", "bombardament", "cessate il fuoco", "accordo", "offensive",
            "gaza", "israele", "hamas", "medio oriente", "cisgiordania",
            "soldati", "truppe", "forze armate", "attacco",
        ],
    ),
    (
        "T2 - Formula 1 questo weekend",
        "dove corrono la formula uno questo weekend?",
        REAL_ANSWER_SIGNALS,
    ),
    (
        "T3 - Meteo Melbourne (tool weather o auto_search)",
        "che tempo fa a Melbourne adesso?",
        # Il weather tool usa dati reali → temperature/condizioni specifiche
        ["gradi", "temperatura", "temperature", "°", "pioggia", "nuvoloso", "sole",
         "vento", "celsius", "km/h", "mm", "caldo", "fresco", "freddo", "umido",
         "sereno", "coperto", "temporale"] + REAL_ANSWER_SIGNALS,
    ),
    (
        "T4 - Borsa italiana oggi",
        "come va la borsa italiana oggi?",
        REAL_ANSWER_SIGNALS,
    ),
    (
        "T5 - Champions League (evento recente)",
        "chi ha vinto la Champions League quest'anno?",
        # Se trova info reale: nome squadra vincitrice o "secondo fonte..."
        ["real madrid", "manchester", "psg", "inter", "milan", "chelsea",
         "liverpool", "barcelona", "atletico", "dortmund", "arsenal",
         "city", "finale", "trofeo", "titolo"] + REAL_ANSWER_SIGNALS,
    ),
    (
        "T6 - Cerca sul web (richiesta esplicita)",
        "cerca sul web le ultime notizie sull'Inter",
        # Deve trovare news reali, non suggerire siti
        ["serie a", "gol", "partita", "allenatore", "mercato", "nerazzurri",
         "stadio", "risultato", "classifica"] + REAL_ANSWER_SIGNALS,
    ),
    (
        "T7 - Novità Claude/Anthropic (tech recente)",
        "quali sono le ultime novità su Claude di Anthropic?",
        # Deve trovare info su Claude — NB: "anthropic" è nella domanda, usiamo altri segnali
        ["modello", "versione", "lanciato", "rilasciato", "aggiornamento",
         "prestazioni", "capacità", "api", "sonnet", "opus", "haiku",
         "intelligenza artificiale", "llm"] + REAL_ANSWER_SIGNALS,
    ),
]


def check_response(label: str, message: str, response: str,
                   must_contain_any: list) -> bool:
    resp_lower = response.lower() if response else ""

    # CRITERIO 1: non deve contenere frasi di rifiuto
    for phrase in REFUSAL_PHRASES:
        if phrase.lower() in resp_lower:
            fail(f"{label}: rifiuto non intercettato: '{phrase}'")
            fail(f"  Risposta: {response[:250]}")
            return False

    # CRITERIO 2: deve contenere almeno un segnale reale
    # (escludi parole che appaiono già nella domanda)
    msg_lower = message.lower()
    valid_signals = [kw for kw in must_contain_any if kw.lower() not in msg_lower]
    if valid_signals and not any(kw.lower() in resp_lower for kw in valid_signals):
        fail(f"{label}: nessun segnale di risposta reale")
        fail(f"  Segnali attesi (non nella domanda): {valid_signals[:8]}")
        fail(f"  Risposta: {response[:250]}")
        return False

    ok(f"{label}")
    info(f"  Risposta: {response[:300]}")
    return True


async def run_tests():
    header("TEST RICERCA WEB AUTONOMA — GENESI")
    info(f"Target: {BASE_URL}")
    info(f"Utente: {EMAIL}")
    print()

    passed = 0
    failed = 0
    results = []

    async with aiohttp.ClientSession() as session:
        try:
            token = await login(session)
        except Exception as e:
            fail(f"Login fallito: {e}")
            return 0, len(TEST_CASES)

        print()

        for label, message, signals in TEST_CASES:
            header(label)
            info(f"Messaggio: '{message}'")
            try:
                t0 = time.time()
                data = await send_message(session, token, message)
                elapsed = time.time() - t0
                response = data.get("response") or data.get("message") or ""
                intent = data.get("intent", "?")
                info(f"Intent: {intent} | Tempo: {elapsed:.1f}s")

                success = check_response(label, message, response, signals)
                if success:
                    passed += 1
                    results.append((label, True, response[:120]))
                else:
                    failed += 1
                    results.append((label, False, response[:120]))

            except Exception as e:
                fail(f"Errore HTTP: {e}")
                failed += 1
                results.append((label, False, str(e)))

            await asyncio.sleep(3)

    header("RIEPILOGO")
    for label, success, snippet in results:
        status = f"{ANSI_GREEN}PASS{ANSI_RESET}" if success else f"{ANSI_RED}FAIL{ANSI_RESET}"
        print(f"  [{status}] {label}")

    total = passed + failed
    print(f"\n{ANSI_BOLD}Score: {passed}/{total}{ANSI_RESET}")
    return passed, total


if __name__ == "__main__":
    passed, total = asyncio.run(run_tests())
    sys.exit(0 if passed == total else 1)
