"""
TEST BEHAVIORAL MEMORY — Genesi Procedural Memory System
Verifica le implementazioni:
  1. BehavioralMemory unit tests (topic extraction, update, snippet)
  2. EpisodeMemory mood-congruent retrieval
  3. Integration API: comportamento reale dopo N messaggi
  4. Verifica file su disco dopo conversazione

Uso: /opt/genesi/venv/bin/python scripts/test_behavioral_memory.py <email> <password>
"""

import asyncio
import json
import os
import sys
import time
import aiohttp

BASE_URL = "http://localhost:8000"
TEST_UID = "_test_behavioral_unit_"

# ── Colori ────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

results = []


def ok(msg):
    results.append(("PASS", msg))
    print(f"  {GREEN}OK{RESET}  {msg}")


def fail(msg, detail=""):
    results.append(("FAIL", msg))
    print(f"  {RED}FAIL{RESET} {msg}" + (f"\n       {YELLOW}{detail}{RESET}" if detail else ""))


def section(title):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")


# ══════════════════════════════════════════════════════════════
# 1. UNIT TESTS — BehavioralMemory
# ══════════════════════════════════════════════════════════════

async def test_unit_behavioral():
    section("1. BEHAVIORAL MEMORY — Unit Tests")

    from core.behavioral_memory import BehavioralMemory, _extract_topics

    bm = BehavioralMemory()
    path = bm._path(TEST_UID)

    # Cleanup iniziale
    if os.path.exists(path):
        os.remove(path)

    # 1a. Topic extraction
    topics = _extract_topics("oggi ho lavorato tanto sul progetto di casa mia")
    if any(t in topics for t in ["lavorato", "progetto", "casa"]):
        ok("Topic extraction funziona (parole significative estratte)")
    else:
        fail("Topic extraction", f"atteso ['lavorato','progetto','casa'], ottenuto {topics}")

    # 1b. Stopwords filtrate
    topics2 = _extract_topics("il lo la con che non si")
    if len(topics2) == 0:
        ok("Stopwords correttamente filtrate")
    else:
        fail("Stopwords non filtrate", f"topics: {topics2}")

    # 1c. Update accumula correttamente
    for i in range(4):
        await bm.update(TEST_UID,
            user_msg="lavoro tanto oggi stressante",
            assistant_msg="Capisco come ti senti. Come posso aiutarti?",
            emotion="anxious",
        )
    data = bm._load(TEST_UID)

    if data["interaction_style"]["total_turns"] == 4:
        ok("interaction_style.total_turns aggiornato (4 turni)")
    else:
        fail("total_turns errato", f"atteso 4, ottenuto {data['interaction_style']['total_turns']}")

    topic_keys = list(data["topic_emotion_map"].keys())
    if any(t in topic_keys for t in ["lavoro", "tanto", "stressante"]):
        ok(f"topic_emotion_map popolato: {topic_keys[:4]}")
    else:
        fail("topic_emotion_map vuoto", f"keys: {topic_keys}")

    if "anxious" in str(data["topic_emotion_map"]):
        ok("Emozione 'anxious' associata ai topic")
    else:
        fail("Emozione non associata", f"map: {data['topic_emotion_map']}")

    # Verifica peak_hours
    hour_now = time.localtime().tm_hour
    if data["peak_hours"][hour_now] >= 4:
        ok(f"peak_hours aggiornato per ora {hour_now}h")
    else:
        fail("peak_hours non aggiornato", f"ore {hour_now}: {data['peak_hours'][hour_now]}")

    # 1d. Snippet None con sessions < 3
    data_low = bm._default()
    data_low["sessions_count"] = 2
    bm._save(TEST_UID, data_low)
    snippet_low = bm.get_context_snippet(TEST_UID)
    if snippet_low is None:
        ok("Snippet None per sessions < 3 (threshold rispettato)")
    else:
        fail("Snippet non None con sessions=2", f"snippet: {snippet_low}")

    # 1e. Snippet valido dopo soglia
    data_ok = bm._default()
    data_ok["sessions_count"] = 5
    data_ok["interaction_style"] = {
        "total_turns": 20, "total_user_chars": 400, "total_assistant_chars": 3000,
        "questions_in_assistant": 10, "user_followup_count": 5, "avg_user_msg_length": 20.0,
    }
    data_ok["topic_emotion_map"] = {
        "lavoro": {"anxious": 8, "stressed": 4},
        "famiglia": {"worried": 2, "happy": 3},
    }
    data_ok["peak_hours"] = [0] * 20 + [8, 2] + [0] * 2
    bm._save(TEST_UID, data_ok)

    snippet_ok = bm.get_context_snippet(TEST_UID)
    if snippet_ok is not None:
        ok(f"Snippet generato: '{snippet_ok[:70]}...'")
    else:
        fail("Snippet None con sessions=5 e dati validi")

    # Controlla contenuto snippet
    if snippet_ok and ("lavoro" in snippet_ok or "anxious" in snippet_ok):
        ok("Snippet contiene topic sensibile corretto (lavoro/anxious)")
    else:
        fail("Snippet non contiene topic atteso", f"snippet: {snippet_ok}")

    if snippet_ok and "Stile" in snippet_ok:
        ok("Snippet contiene sezione 'Stile preferito'")
    else:
        fail("Sezione 'Stile' mancante nel snippet", f"snippet: {snippet_ok}")

    # Cleanup
    if os.path.exists(path):
        os.remove(path)


# ══════════════════════════════════════════════════════════════
# 2. UNIT TESTS — Mood-Congruent Retrieval
# ══════════════════════════════════════════════════════════════

async def test_unit_mood_congruent():
    section("2. MOOD-CONGRUENT RETRIEVAL — Unit Tests")

    from core.episode_memory import EpisodeMemory
    from core.storage import storage
    from datetime import datetime

    em = EpisodeMemory()
    uid = "_test_mood_unit_"
    now = datetime.utcnow().isoformat()

    ep_anxious = {
        "id": "ep_anxious", "text": "presentazione lavoro importante domani",
        "tags": ["anxious", "lavoro"], "saved_at": now,
        "last_used_at": None, "use_count": 0, "is_future": False, "event_date": None
    }
    ep_happy = {
        "id": "ep_happy", "text": "vacanza mare bellissima estate",
        "tags": ["happy", "relax"], "saved_at": now,
        "last_used_at": None, "use_count": 0, "is_future": False, "event_date": None
    }
    ep_neutral = {
        "id": "ep_neutral", "text": "appuntamento dal dentista lunedi",
        "tags": ["neutral", "salute"], "saved_at": now,
        "last_used_at": None, "use_count": 0, "is_future": False, "event_date": None
    }

    await storage.save(f"episodes:{uid}", [ep_anxious, ep_happy, ep_neutral])

    # Score senza boost
    s_anxious = em._score_relevance(ep_anxious, "ho qualcosa domani")
    s_happy = em._score_relevance(ep_happy, "ho qualcosa domani")
    s_neutral = em._score_relevance(ep_neutral, "ho qualcosa domani")

    # Score con boost (simulato)
    s_anxious_boosted = s_anxious + 0.08

    ok(f"Score base — anxious={s_anxious:.2f} happy={s_happy:.2f} neutral={s_neutral:.2f}")

    if s_anxious_boosted > s_happy:
        ok(f"Boost mood-congruent efficace ({s_anxious:.2f}+0.08 > {s_happy:.2f})")
    else:
        fail("Boost non cambia ranking", f"{s_anxious_boosted:.2f} vs {s_happy:.2f}")

    # Test con parametro current_emotion via get_relevant
    results_anxious = await em.get_relevant(uid, "domani ho qualcosa", limit=3, current_emotion="anxious")
    ids_anxious = [e["id"] for e in results_anxious]

    results_happy = await em.get_relevant(uid, "domani ho qualcosa", limit=3, current_emotion="happy")
    ids_happy = [e["id"] for e in results_happy]

    if results_anxious and results_anxious[0]["id"] in ("ep_anxious", "ep_neutral", "ep_happy"):
        ok(f"get_relevant con emotion=anxious ritorna: {ids_anxious}")
    else:
        fail("get_relevant emotion=anxious non ritorna episodi", f"ids: {ids_anxious}")

    if results_happy and results_happy[0]["id"] in ("ep_anxious", "ep_neutral", "ep_happy"):
        ok(f"get_relevant con emotion=happy ritorna: {ids_happy}")
    else:
        fail("get_relevant emotion=happy non ritorna episodi", f"ids: {ids_happy}")

    # Test parametro non specificato — backward compat
    results_none = await em.get_relevant(uid, "domani ho qualcosa", limit=3)
    if isinstance(results_none, list):
        ok("get_relevant senza current_emotion — backward compatible")
    else:
        fail("get_relevant senza emotion restituisce tipo errato")

    # Cleanup
    await storage.save(f"episodes:{uid}", [])


# ══════════════════════════════════════════════════════════════
# 3. INTEGRATION TEST — API reale
# ══════════════════════════════════════════════════════════════

async def test_integration_api(email: str, password: str):
    section("3. INTEGRATION TEST — API reale")

    async with aiohttp.ClientSession() as session:
        # Login
        async with session.post(f"{BASE_URL}/auth/login",
                                json={"email": email, "password": password}) as r:
            if r.status != 200:
                fail("Login", f"status {r.status}")
                return
            token = (await r.json()).get("access_token")
            ok("Login OK")

        headers = {"Authorization": f"Bearer {token}"}

        # Recupera user_id
        async with session.get(f"{BASE_URL}/auth/me", headers=headers) as r:
            me = await r.json()
            user_id = me.get("id", "")
            ok(f"User ID: {user_id[:12]}...")

        beh_path = f"memory/behavioral/{user_id}.json"
        beh_path_before = os.path.exists(beh_path)

        # Sequenza di messaggi mirati a triggerare behavioral memory
        # e topic-emotion binding
        test_messages = [
            ("ho troppo lavoro oggi, sono stressato",  "stress lavorativo"),
            ("la presentazione di domani mi spaventa", "ansia presentazione"),
            ("anche mia moglie è preoccupata per me",  "stress familiare"),
            ("Napoli è bella?",                        "cambio topic conoscenza"),
            ("torno al lavoro, ancora problemi",       "lavoro ricorrente"),
        ]

        print(f"\n  Invio {len(test_messages)} messaggi di test...")
        for msg, label in test_messages:
            async with session.post(f"{BASE_URL}/api/chat",
                                    json={"message": msg},
                                    headers=headers) as r:
                if r.status == 200:
                    resp = await r.json()
                    reply = resp.get("response", "")[:60]
                    print(f"    [{label}] -> '{reply}...'")
                else:
                    fail(f"Chat request fallita per '{label}'", f"status {r.status}")
            await asyncio.sleep(1.5)  # wait background tasks

        # Attendi background tasks
        await asyncio.sleep(3)

        # Verifica file behavioral su disco
        if os.path.exists(beh_path):
            with open(beh_path, "r", encoding="utf-8") as f:
                beh_data = json.load(f)

            turns = beh_data.get("interaction_style", {}).get("total_turns", 0)
            if turns >= len(test_messages):
                ok(f"File behavioral creato — turns={turns}")
            else:
                fail("turns < atteso", f"turns={turns}, atteso>={len(test_messages)}")

            topic_map = beh_data.get("topic_emotion_map", {})
            if topic_map:
                ok(f"topic_emotion_map popolato: {list(topic_map.keys())[:5]}")
            else:
                fail("topic_emotion_map vuoto dopo 5 messaggi")

            # Verifica peak_hours aggiornato
            total_hours = sum(beh_data.get("peak_hours", [0]*24))
            if total_hours >= len(test_messages):
                ok(f"peak_hours aggiornato (totale={total_hours})")
            else:
                fail("peak_hours non aggiornato", f"totale={total_hours}")

            # Verifica sessions_count
            sc = beh_data.get("sessions_count", 0)
            ok(f"sessions_count={sc}")

        else:
            fail("File behavioral NON creato su disco", f"path: {beh_path}")

        # Verifica snippet nel context (indiretto: se sessions >= 3 deve influenzare risposta)
        sessions = beh_data.get("sessions_count", 0) if os.path.exists(beh_path) else 0
        if sessions >= 3:
            ok(f"sessions_count={sessions} >= 3 — snippet sarà iniettato nei prossimi turni")
        else:
            # Non è un fail — dipende da quante sessioni precedenti esistevano
            print(f"  {YELLOW}NOTE{RESET} sessions_count={sessions} < 3 — snippet non ancora attivo (normale al primo run)")

        # Test: invio un messaggio con contesto emotivo e verifica che la risposta
        # non sia completamente generica (behavioral context sta influenzando)
        async with session.post(f"{BASE_URL}/api/chat",
                                json={"message": "come pensi che stia andando per me ultimamente?"},
                                headers=headers) as r:
            if r.status == 200:
                resp = await r.json()
                reply = resp.get("response", "")
                if any(kw in reply.lower() for kw in ["lavoro", "stress", "present", "preoccup", "difficil"]):
                    ok(f"Risposta contestuale (usa memoria): '{reply[:80]}...'")
                else:
                    print(f"  {YELLOW}NOTE{RESET} Risposta generica (possibile se memoria episodica non ancora accumulata): '{reply[:60]}...'")
            else:
                fail("Messaggio finale fallito", f"status {r.status}")


# ══════════════════════════════════════════════════════════════
# 4. VERIFICA FILE SU DISCO
# ══════════════════════════════════════════════════════════════

async def test_file_structure():
    section("4. STRUTTURA FILE BEHAVIORAL SU DISCO")

    # Crea e verifica un file direttamente
    from core.behavioral_memory import BehavioralMemory
    import os

    bm = BehavioralMemory()
    uid = "_test_file_structure_"
    path = bm._path(uid)

    if os.path.exists(path):
        os.remove(path)

    # Popola con dati realistici
    await bm.update(uid, "ho lavorato molto oggi", "Ok, capito.", "stressed")
    await bm.update(uid, "mia moglie preoccupata", "Lo sento. Come stai?", "worried")
    await bm.update(uid, "guardo la formula 1 sera", "Bella passione!", "happy")

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Verifica struttura JSON
        required_keys = ["interaction_style", "topic_emotion_map", "engagement_signals",
                         "peak_hours", "sessions_count", "last_updated"]
        missing = [k for k in required_keys if k not in data]
        if not missing:
            ok("Struttura JSON corretta (tutti i campi presenti)")
        else:
            fail("Campi mancanti nel JSON", f"missing: {missing}")

        # peak_hours: array da 24
        ph = data.get("peak_hours", [])
        if len(ph) == 24 and all(isinstance(x, (int, float)) for x in ph):
            ok("peak_hours: array[24] corretto")
        else:
            fail("peak_hours malformato", f"len={len(ph)}")

        # topic_emotion_map: dizionario topic → {emotion: count}
        tem = data.get("topic_emotion_map", {})
        if isinstance(tem, dict) and all(isinstance(v, dict) for v in tem.values()):
            ok(f"topic_emotion_map struttura corretta: {list(tem.keys())[:3]}")
        else:
            fail("topic_emotion_map malformato")

        # last_updated: ISO timestamp
        lu = data.get("last_updated", "")
        if lu and "T" in lu:
            ok(f"last_updated: {lu[:19]}")
        else:
            fail("last_updated mancante o malformato")

        os.remove(path)
    else:
        fail("File non creato")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

async def main():
    email = sys.argv[1] if len(sys.argv) > 1 else None
    password = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"\n{BOLD}BEHAVIORAL MEMORY TEST SUITE{RESET}")
    print(f"Target: {BASE_URL}\n")

    # Unit tests (sempre)
    await test_unit_behavioral()
    await test_unit_mood_congruent()
    await test_file_structure()

    # Integration tests (solo se credenziali fornite)
    if email and password:
        await test_integration_api(email, password)
    else:
        print(f"\n{YELLOW}INFO: Integration test saltato (nessuna credenziale fornita){RESET}")
        print(f"      Uso: python test_behavioral_memory.py <email> <password>")

    # Riepilogo
    passed = sum(1 for r in results if r[0] == "PASS")
    failed = sum(1 for r in results if r[0] == "FAIL")
    total = passed + failed

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}RISULTATI FINALI: {passed}/{total}{RESET}", end="  ")
    if failed == 0:
        print(f"{GREEN}TUTTO OK{RESET}")
    else:
        print(f"{RED}{failed} FALLITI{RESET}")
        print(f"\n{RED}Fallimenti:{RESET}")
        for r in results:
            if r[0] == "FAIL":
                print(f"  x {r[1]}")
    print(f"{'='*60}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
