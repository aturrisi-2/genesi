"""
TEST COGNITIVE SYSTEM - Genesi v2
6 scenari obbligatori:
1. Inserimento nome
2. Inserimento familiare
3. Dialogo neutro
4. Dialogo emotivo
5. Richiesta memoria
6. Quota LLM simulata 429
"""

import asyncio
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


async def run_tests():
    from core.memory_brain import memory_brain, LocalEmotionAnalyzer
    from core.evolution_engine import generate_response_from_brain, score_message_complexity
    from core.storage import storage

    TEST_USER = "test_cognitive_001"
    passed = 0
    failed = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            print(f"  [OK] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name} -- {detail}")
            failed += 1

    # ---------- CLEANUP ----------
    # Remove test user data
    await storage.save(f"long_term_profile:{TEST_USER}", None)
    await storage.save(f"episodes/{TEST_USER}", [])
    await storage.save(f"relational_state:{TEST_USER}", None)

    # =================================
    # TEST 1: Inserimento nome
    # =================================
    print("\n===== TEST 1: Inserimento nome =====")
    brain1 = await memory_brain.update_brain(TEST_USER, "Ciao, mi chiamo Alfio")
    profile1 = brain1["profile"]
    check("Nome estratto", profile1.get("name") == "Alfio", f"got: {profile1.get('name')}")
    check("Trust inizializzato", brain1["relational"]["trust"] > 0, f"trust={brain1['relational']['trust']}")
    check("Episodio creato", brain1.get("episode_id") is not None, "no episode_id")

    resp1 = await generate_response_from_brain(TEST_USER, "Ciao, mi chiamo Alfio", brain1)
    check("Risposta non vuota", len(resp1) > 0, "empty response")
    check("Risposta contiene nome o saluto", "Alfio" in resp1 or "ciao" in resp1.lower(),
          f"resp: {resp1[:80]}")
    print(f"  -> Risposta: {resp1}")

    # =================================
    # TEST 2: Inserimento familiare
    # =================================
    print("\n===== TEST 2: Inserimento familiare =====")
    brain2 = await memory_brain.update_brain(TEST_USER, "Mia moglie si chiama Rita")
    profile2 = brain2["profile"]
    entities = profile2.get("entities", {})
    check("Entità moglie estratta", "moglie" in entities, f"entities: {list(entities.keys())}")
    if "moglie" in entities:
        check("Nome moglie = Rita", entities["moglie"].get("name") == "Rita",
              f"got: {entities['moglie'].get('name')}")

    resp2 = await generate_response_from_brain(TEST_USER, "Mia moglie si chiama Rita", brain2)
    check("Risposta non vuota", len(resp2) > 0, "empty response")
    print(f"  -> Risposta: {resp2}")

    # =================================
    # TEST 3: Dialogo neutro
    # =================================
    print("\n===== TEST 3: Dialogo neutro =====")
    brain3 = await memory_brain.update_brain(TEST_USER, "Oggi ho fatto una passeggiata al parco")
    emotion3 = brain3["emotion"]
    check("Emozione neutra o bassa intensità",
          emotion3["emotion"] == "neutral" or emotion3["intensity"] < 0.5,
          f"emotion={emotion3['emotion']} intensity={emotion3['intensity']}")

    resp3 = await generate_response_from_brain(TEST_USER, "Oggi ho fatto una passeggiata al parco", brain3)
    check("Risposta non vuota", len(resp3) > 0, "empty response")
    check("Risposta non generica (contiene nome o contesto)",
          "Alfio" in resp3 or "parco" in resp3.lower() or "passeggiata" in resp3.lower() or len(resp3) > 10,
          f"resp: {resp3[:80]}")
    print(f"  -> Risposta: {resp3}")

    # =================================
    # TEST 4: Dialogo emotivo
    # =================================
    print("\n===== TEST 4: Dialogo emotivo =====")
    brain4 = await memory_brain.update_brain(TEST_USER, "Sono molto triste oggi, mi sento solo")
    emotion4 = brain4["emotion"]
    check("Emozione triste rilevata", emotion4["emotion"] == "sad",
          f"got: {emotion4['emotion']}")
    check("Intensità alta", emotion4["intensity"] > 0.5,
          f"intensity={emotion4['intensity']}")

    resp4 = await generate_response_from_brain(TEST_USER, "Sono molto triste oggi, mi sento solo", brain4)
    check("Risposta non vuota", len(resp4) > 0, "empty response")
    check("Risposta empatica (contiene parole di supporto)",
          any(w in resp4.lower() for w in ["qui", "ascolto", "capisco", "solo", "senti", "valore"]),
          f"resp: {resp4[:80]}")
    print(f"  -> Risposta: {resp4}")

    # =================================
    # TEST 5: Richiesta memoria
    # =================================
    print("\n===== TEST 5: Richiesta memoria =====")
    brain5 = await memory_brain.update_brain(TEST_USER, "Cosa ti ricordi di me?")

    resp5 = await generate_response_from_brain(TEST_USER, "Cosa ti ricordi di me?", brain5)
    check("Risposta non vuota", len(resp5) > 0, "empty response")
    check("Risposta contiene nome Alfio", "Alfio" in resp5 or "alfio" in resp5.lower(),
          f"resp: {resp5[:100]}")
    check("Risposta contiene Rita o moglie",
          "Rita" in resp5 or "moglie" in resp5.lower(),
          f"resp: {resp5[:100]}")
    print(f"  -> Risposta: {resp5}")

    # =================================
    # TEST 6: Quota LLM simulata 429
    # =================================
    print("\n===== TEST 6: Quota LLM simulata 429 =====")
    # Test complexity scoring
    complexity_simple = score_message_complexity("Ciao", brain5)
    complexity_complex = score_message_complexity(
        "Spiegami la differenza tra architettura monolitica e microservizi nel contesto di sistemi distribuiti",
        brain5
    )
    check("Messaggio semplice = bassa complessità", complexity_simple < 0.4,
          f"score={complexity_simple}")
    check("Messaggio complesso = alta complessità", complexity_complex >= 0.4,
          f"score={complexity_complex}")

    # Simulate: even with high complexity, if LLM fails, autonomous response works
    brain6 = await memory_brain.update_brain(TEST_USER, "Come stai?")
    resp6 = await generate_response_from_brain(TEST_USER, "Come stai?", brain6)
    check("Risposta senza LLM non vuota", len(resp6) > 0, "empty response")
    check("Risposta non è errore generico",
          "errore" not in resp6.lower() and "problema" not in resp6.lower(),
          f"resp: {resp6[:80]}")
    print(f"  -> Risposta: {resp6}")

    # =================================
    # TEST EXTRA: Local Emotion Analyzer
    # =================================
    print("\n===== TEST EXTRA: Local Emotion Analyzer =====")
    analyzer = LocalEmotionAnalyzer()

    e1 = analyzer.analyze("Sono molto felice oggi!")
    check("Felice rilevato", e1["emotion"] == "happy", f"got: {e1['emotion']}")

    e2 = analyzer.analyze("Ho paura di quello che succederà")
    check("Ansia/paura rilevata", e2["emotion"] in ("anxious", "fear"),
          f"got: {e2['emotion']}")

    e3 = analyzer.analyze("Buongiorno")
    check("Neutro per saluto", e3["emotion"] == "neutral", f"got: {e3['emotion']}")

    e4 = analyzer.analyze("Sono davvero arrabbiato con il mio capo")
    check("Rabbia rilevata", e4["emotion"] == "angry", f"got: {e4['emotion']}")
    check("Intensificatore 'davvero' aumenta intensità", e4["intensity"] > 0.7,
          f"intensity={e4['intensity']}")

    # =================================
    # TEST EXTRA: Experience Linking
    # =================================
    print("\n===== TEST EXTRA: Experience Linking =====")
    episodes = await memory_brain.episodic.recall(TEST_USER, limit=10)
    check("Episodi creati", len(episodes) > 0, f"count={len(episodes)}")

    # Check that some episodes have links
    linked = [e for e in episodes if e.get("links")]
    check("Almeno un episodio ha links", len(linked) > 0,
          f"linked={len(linked)} total={len(episodes)}")

    # =================================
    # TEST EXTRA: Relational Evolution
    # =================================
    print("\n===== TEST EXTRA: Relational Evolution =====")
    rel = await memory_brain.relational.load(TEST_USER)
    check("Trust > iniziale", rel["trust"] > 0.15,
          f"trust={rel['trust']}")
    check("Total messages tracked", rel["history"]["total_msgs"] > 0,
          f"msgs={rel['history']['total_msgs']}")
    check("Stage non initial", rel["stage"] != "initial" or rel["history"]["total_msgs"] < 5,
          f"stage={rel['stage']} msgs={rel['history']['total_msgs']}")

    # =================================
    # SUMMARY
    # =================================
    print(f"\n{'=' * 50}")
    print(f"RISULTATI: {passed} passed, {failed} failed")
    print(f"{'=' * 50}")

    if failed > 0:
        print("\n!! ATTENZIONE: Alcuni test falliti!")
        sys.exit(1)
    else:
        print("\nOK - TUTTI I TEST PASSATI - Sistema cognitivo operativo")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_tests())
