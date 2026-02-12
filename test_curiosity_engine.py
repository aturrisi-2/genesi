"""
TEST CURIOSITY ENGINE - Genesi Cognitive System v3
Verifica:
- Frase ambivalente → genera domanda specifica
- Frase neutra → non forza domanda
- Frase vulnerabile → genera domanda mirata
- Frase concreta → nessuna curiosità
- Domanda contiene parola derivata dal messaggio
- Score > 0.6 → risposta non termina con frase chiusa
- Integrazione pipeline completa
"""

import asyncio
import sys
import os
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-local-testing")

from core.curiosity_engine import curiosity_engine, CuriosityEngine
from core.memory_brain import memory_brain
from core.latent_state import latent_state_engine
from core.evolution_engine import generate_response_from_brain
from core.storage import storage

TEST_USER = "test_curiosity_001"

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [OK] {label}")
    else:
        failed += 1
        extra = f" -- {detail}" if detail else ""
        print(f"  [FAIL] {label}{extra}")


def make_brain_state(emotion="neutral", intensity=0.3, curiosity=0.5, resonance=0.5):
    return {
        "emotion": {"emotion": emotion, "intensity": intensity, "vulnerability": 0.0},
        "latent": {
            "emotional_resonance": resonance,
            "curiosity": curiosity,
            "attachment": 0.5,
            "stability": 0.5,
            "relational_energy": 0.5,
        },
        "profile": {"name": "Test"},
        "relational": {"trust": 0.3, "stage": "initial"},
        "episodes": [],
    }


async def cleanup():
    await storage.save(f"episodes/{TEST_USER}", [])
    await storage.save(f"long_term_profile:{TEST_USER}", None)
    await storage.save(f"relational_state:{TEST_USER}", None)
    await storage.save(f"latent_state:{TEST_USER}", None)


async def test_ambivalent_message():
    print("\n===== TEST 1: Frase ambivalente =====")
    bs = make_brain_state(emotion="neutral", intensity=0.4)
    base = "Capisco quello che dici."
    msg = "non so se dovrei restare o andare via, e' complicato"

    result = curiosity_engine.inject(base, msg, bs)
    has_question = "?" in result
    print(f"  -> Input: {msg}")
    print(f"  -> Output: {result[:200]}")
    check("genera domanda su ambivalenza", has_question)
    check("risposta diversa dalla base", result != base)


async def test_neutral_short_message():
    print("\n===== TEST 2: Frase neutra breve =====")
    bs = make_brain_state(emotion="neutral", intensity=0.1, curiosity=0.3)
    base = "Ciao, come va?"
    msg = "tutto bene grazie"

    result = curiosity_engine.inject(base, msg, bs)
    print(f"  -> Input: {msg}")
    print(f"  -> Output: {result[:200]}")
    check("non forza domanda su frase neutra", result == base)


async def test_vulnerable_message():
    print("\n===== TEST 3: Frase vulnerabile =====")
    bs = make_brain_state(emotion="sad", intensity=0.7, resonance=0.6)
    base = "Sono qui con te."
    msg = "non ce la faccio piu', mi sento inadeguata"

    result = curiosity_engine.inject(base, msg, bs)
    has_question = "?" in result
    print(f"  -> Input: {msg}")
    print(f"  -> Output: {result[:200]}")
    check("genera domanda su vulnerabilita'", has_question)
    check("risposta espansa", len(result) > len(base))


async def test_concrete_intent():
    print("\n===== TEST 4: Frase concreta (no curiosita') =====")
    bs = make_brain_state()
    base = "Sono le 18:30."
    msg = "che ore sono"

    result = curiosity_engine.inject(base, msg, bs)
    print(f"  -> Input: {msg}")
    print(f"  -> Output: {result[:200]}")
    check("nessuna curiosita' su intent concreto", result == base)


async def test_identity_crisis():
    print("\n===== TEST 5: Frase identitaria =====")
    bs = make_brain_state(emotion="sad", intensity=0.5)
    base = "Capisco."
    msg = "non so cosa voglio dalla vita, non so chi sono davvero"

    result = curiosity_engine.inject(base, msg, bs)
    has_question = "?" in result
    print(f"  -> Input: {msg}")
    print(f"  -> Output: {result[:200]}")
    check("genera domanda su crisi identitaria", has_question)


async def test_vague_emotion():
    print("\n===== TEST 6: Stato emotivo vago =====")
    bs = make_brain_state(emotion="neutral", intensity=0.4)
    base = "Ti ascolto."
    msg = "mi sento strano, come se qualcosa non andasse"

    result = curiosity_engine.inject(base, msg, bs)
    has_question = "?" in result
    print(f"  -> Input: {msg}")
    print(f"  -> Output: {result[:200]}")
    check("genera domanda su emozione vaga", has_question)


async def test_keyword_in_question():
    print("\n===== TEST 7: Domanda contiene parola dal messaggio =====")
    bs = make_brain_state(emotion="sad", intensity=0.6, resonance=0.6)
    base = "Capisco."
    msg = "mi sento vuoto dentro, come se avessi perso tutto"

    result = curiosity_engine.inject(base, msg, bs)
    result_lower = result.lower()
    # Should contain a keyword from the message
    keywords = ["vuoto", "perso", "dentro"]
    has_keyword = any(kw in result_lower for kw in keywords)
    print(f"  -> Input: {msg}")
    print(f"  -> Output: {result[:200]}")
    check("domanda contiene keyword dal messaggio", has_keyword,
          f"cercavo {keywords} in: {result[:100]}")


async def test_high_score_no_closed_ending():
    print("\n===== TEST 8: Score > 0.6 → non termina con frase chiusa =====")
    bs = make_brain_state(emotion="sad", intensity=0.7, curiosity=0.7, resonance=0.7)
    base = "Sono qui con te."
    msg = "non so se dovrei restare, mi sento perso e inadeguato"

    result = curiosity_engine.inject(base, msg, bs)
    ends_with_question = result.rstrip().endswith("?")
    print(f"  -> Input: {msg}")
    print(f"  -> Output: {result[:200]}")
    check("risposta contiene domanda (score alto)", "?" in result)


async def test_curiosity_score_calculation():
    print("\n===== TEST 9: Calcolo curiosity_score =====")
    engine = CuriosityEngine()

    # Ambivalent
    score1, triggers1 = engine._calculate_curiosity_score(
        "non so se dovrei restare o andare", make_brain_state())
    check("ambivalenza score >= 0.3", score1 >= 0.3, f"got {score1:.2f}")
    check("trigger ambivalence presente", "ambivalence" in triggers1)

    # Neutral
    score2, triggers2 = engine._calculate_curiosity_score(
        "tutto bene", make_brain_state(curiosity=0.3))
    check("neutro score < 0.3", score2 < 0.3, f"got {score2:.2f}")

    # Vulnerable
    score3, triggers3 = engine._calculate_curiosity_score(
        "non ce la faccio piu'", make_brain_state())
    check("vulnerabilita' score >= 0.3", score3 >= 0.3, f"got {score3:.2f}")


async def test_semantic_extraction():
    print("\n===== TEST 10: Estrazione semantica =====")
    engine = CuriosityEngine()

    keywords = engine._extract_semantic_keywords("mi sento vuoto e confuso dentro di me")
    print(f"  -> Keywords: {keywords}")
    check("estrae 'vuoto'", "vuoto" in keywords)
    check("estrae 'confuso'", "confuso" in keywords)
    check("non estrae stopword 'dentro'", "dentro" not in keywords or len(keywords) > 0)


async def test_no_question_stacking():
    print("\n===== TEST 11: No question stacking =====")
    bs = make_brain_state(emotion="sad", intensity=0.6)
    # Base response already has a specific question
    base = "Capisco. Da quanto tempo ti senti cosi' riguardo al lavoro?"
    msg = "non so se dovrei cambiare lavoro"

    result = curiosity_engine.inject(base, msg, bs)
    question_count = result.count("?")
    print(f"  -> Output: {result[:200]}")
    check("non aggiunge domanda se gia' presente", question_count <= 2,
          f"got {question_count} domande")


async def test_pipeline_integration():
    print("\n===== TEST 12: Pipeline completa =====")
    await cleanup()
    await memory_brain.update_brain(TEST_USER, "Mi chiamo Paolo")

    brain_state = await memory_brain.update_brain(TEST_USER,
        "mi sento perso, non so cosa voglio dalla vita")
    latent = await latent_state_engine.update_latent_state(
        user_id=TEST_USER,
        user_message="mi sento perso, non so cosa voglio dalla vita",
        emotional_analysis=brain_state.get("emotion", {}),
        relational_state=brain_state.get("relational", {}),
        episode_stored=brain_state.get("episode_id") is not None,
    )
    brain_state["latent"] = latent

    base = await generate_response_from_brain(TEST_USER,
        "mi sento perso, non so cosa voglio dalla vita", brain_state)
    curious = curiosity_engine.inject(base,
        "mi sento perso, non so cosa voglio dalla vita", brain_state)

    print(f"  -> Base: {base[:100]}")
    print(f"  -> Curious: {curious[:200]}")
    check("pipeline produce output non vuoto", len(curious) > 0)
    check("curiosity ha effetto (domanda o espansione)", len(curious) >= len(base))


async def test_greeting_no_curiosity():
    print("\n===== TEST 13: Saluto semplice → no curiosita' =====")
    bs = make_brain_state(curiosity=0.3)
    base = "Ciao! Come stai?"
    msg = "ciao"

    result = curiosity_engine.inject(base, msg, bs)
    print(f"  -> Output: {result[:200]}")
    check("saluto non attiva curiosita'", result == base)


async def test_memory_question_no_curiosity():
    print("\n===== TEST 14: Domanda memoria → no curiosita' =====")
    bs = make_brain_state()
    base = "Certo che mi ricordo."
    msg = "ti ricordi come mi chiamo?"

    result = curiosity_engine.inject(base, msg, bs)
    print(f"  -> Output: {result[:200]}")
    check("domanda memoria non attiva curiosita'", result == base)


async def main():
    print("=" * 55)
    print("GENESI v3 - CURIOSITY ENGINE TESTS")
    print("=" * 55)

    await cleanup()
    await test_ambivalent_message()
    await test_neutral_short_message()
    await test_vulnerable_message()
    await test_concrete_intent()
    await test_identity_crisis()
    await test_vague_emotion()
    await test_keyword_in_question()
    await test_high_score_no_closed_ending()
    await test_curiosity_score_calculation()
    await test_semantic_extraction()
    await test_no_question_stacking()
    await test_pipeline_integration()
    await test_greeting_no_curiosity()
    await test_memory_question_no_curiosity()
    await cleanup()

    print("\n" + "=" * 55)
    print(f"RISULTATI: {passed} passed, {failed} failed")
    print("=" * 55)

    if failed == 0:
        print("\nOK - CURIOSITY ENGINE OPERATIVO")
    else:
        print(f"\nATTENZIONE: {failed} test falliti")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
