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

BASE_URL = "https://genesi.turrisi.cloud"
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
    async with session.post(f"{BASE_URL}/api/auth/login",
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


def check_response(label: str, response: str, must_not_contain: list, must_contain_any: list = None) -> bool:
    resp_lower = response.lower() if response else ""
    # Deve NON contenere frasi di rifiuto
    for phrase in must_not_contain:
        if phrase.lower() in resp_lower:
            fail(f"{label}: contiene frase di rifiuto: '{phrase}'")
            fail(f"  Risposta: {response[:200]}")
            return False
    # Deve contenere almeno uno dei segnali di risposta reale
    if must_contain_any:
        if not any(kw.lower() in resp_lower for kw in must_contain_any):
            fail(f"{label}: nessun segnale atteso in risposta")
            fail(f"  Atteso uno di: {must_contain_any}")
            fail(f"  Risposta: {response[:200]}")
            return False
    ok(f"{label}")
    info(f"  Risposta: {response[:250]}")
    return True


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
]

# Test cases: (label, messaggio, segnali_attesi_opzionali)
# I segnali attesi sono parole/frasi che indicano che è stata trovata info reale
TEST_CASES = [
    (
        "T1 - Notizie guerra (topic corrente)",
        "Quali sono le ultime notizie sulla guerra?",
        ["secondo", "fonte", "riportato", "notizie", "aggiornamento",
         "conflitto", "ucraina", "russia", "gaza", "medio oriente",
         "ho trovato", "online"],
    ),
    (
        "T2 - Formula 1 questo weekend",
        "dove corrono la formula uno questo weekend?",
        ["gran premio", "australia", "melbourne", "gara", "circuito",
         "secondo", "fonte", "formula", "piloti", "stagione"],
    ),
    (
        "T3 - Meteo reale Melbourne (info specifica)",
        "che tempo fa a Melbourne adesso?",
        ["gradi", "celsius", "temperatura", "meteo", "melbourne",
         "pioggia", "sole", "nuvoloso", "vento", "secondo"],
    ),
    (
        "T4 - Notizie economia",
        "come va la borsa italiana oggi?",
        ["indice", "borsa", "ftse", "mib", "punti", "mercato",
         "secondo", "fonte", "azioni", "performance", "ho trovato"],
    ),
    (
        "T5 - Evento specifico recente",
        "chi ha vinto la Champions League quest'anno?",
        ["campioni", "finale", "vinto", "champions", "coppa",
         "secondo", "fonte", "squadra", "trofeo", "ho trovato"],
    ),
    (
        "T6 - Cerca sul web (richiesta esplicita)",
        "cerca sul web le ultime notizie sull'Inter",
        ["inter", "milan", "serie a", "partita", "gol", "secondo",
         "fonte", "calcio", "nerazzurri", "ho trovato"],
    ),
    (
        "T7 - Informazione tecnica recente",
        "quali sono le ultime novità su Claude di Anthropic?",
        ["anthropic", "claude", "modello", "ai", "versione",
         "secondo", "fonte", "intelligenza", "ho trovato", "lanciato"],
    ),
]


async def run_tests():
    header("TEST RICERCA WEB AUTONOMA — GENESI")
    info(f"Target: {BASE_URL}")
    info(f"Utente: {EMAIL}")
    print()

    passed = 0
    failed = 0
    results = []

    async with aiohttp.ClientSession() as session:
        # Login
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

                success = check_response(label, response, REFUSAL_PHRASES, signals)
                if success:
                    passed += 1
                    results.append((label, True, response[:150]))
                else:
                    failed += 1
                    results.append((label, False, response[:150]))

            except Exception as e:
                fail(f"Errore HTTP: {e}")
                failed += 1
                results.append((label, False, str(e)))

            await asyncio.sleep(3)  # Rate limiting

    # Summary
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
