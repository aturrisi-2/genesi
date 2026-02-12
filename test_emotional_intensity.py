"""
TEST EMOTIONAL INTENSITY ENGINE - Genesi Cognitive System v3
Verifica:
- Input depresso: contiene validazione, no invito generico
- Input narrativo: genera storia vera, non rimanda all'utente
- Input ciao: saluto espanso (non solo 'Ciao!')
- Anti-passive: frasi standalone espanse
- Response mode: short/medium/deep probabilistic
- Empathic phrase blocker: no repeated banned phrases
- Repeated input 3x: switches to direct style
- No regressioni su test v2/v3
"""

import asyncio
import sys
import os
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-local-testing")

from core.emotional_intensity_engine import emotional_intensity_engine
from core.memory_brain import memory_brain
from core.latent_state import latent_state_engine
from core.evolution_engine import generate_response_from_brain
from core.drift_modulator import drift_modulator
from core.storage import storage

TEST_USER = "test_intensity_001"

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


async def cleanup():
    await storage.save(f"episodes/{TEST_USER}", [])
    await storage.save(f"long_term_profile:{TEST_USER}", None)
    await storage.save(f"relational_state:{TEST_USER}", None)
    await storage.save(f"latent_state:{TEST_USER}", None)


async def full_pipeline(message: str) -> tuple:
    """Run full v3 pipeline and return (enhanced_response, brain_state)."""
    brain_state = await memory_brain.update_brain(TEST_USER, message)
    latent = await latent_state_engine.update_latent_state(
        user_id=TEST_USER,
        user_message=message,
        emotional_analysis=brain_state.get("emotion", {}),
        relational_state=brain_state.get("relational", {}),
        episode_stored=brain_state.get("episode_id") is not None,
    )
    brain_state["latent"] = latent
    base_response = await generate_response_from_brain(TEST_USER, message, brain_state)
    enhanced = emotional_intensity_engine.enhance(base_response, message, brain_state)
    return enhanced, brain_state


async def test_depressed_input():
    print("\n===== TEST 1: Input depresso =====")
    await cleanup()

    # First set name so responses are personalized
    await memory_brain.update_brain(TEST_USER, "Mi chiamo Marco")

    response, bs = await full_pipeline("mi sento un po depresso")
    words = response.split()
    word_count = len(words)
    has_question = "?" in response
    resp_lower = response.lower()

    # Validation keywords
    validation_words = ["sento", "senti", "capisco", "comprendo", "conta", "valore",
                        "importante", "coraggio", "normale", "naturale", "qui con te",
                        "sono qui", "quello che"]
    has_validation = any(v in resp_lower for v in validation_words)

    # Generic endings to reject
    generic_endings = ["dimmi pure.", "raccontami.", "ti ascolto.", "vai avanti.", "continua."]
    ends_generic = any(resp_lower.rstrip().endswith(g) for g in generic_endings)

    print(f"  -> Risposta ({word_count} parole): {response[:200]}...")
    check("risposta non vuota", word_count >= 5, f"got {word_count}")
    check("contiene validazione emotiva", has_validation)
    check("NON termina con invito generico", not ends_generic)


async def test_narrative_input():
    print("\n===== TEST 2: Input narrativo =====")
    await cleanup()

    response, bs = await full_pipeline("raccontami una storia")
    words = response.split()
    word_count = len(words)
    resp_lower = response.lower()

    # Should generate actual story content, not redirect
    redirect_phrases = ["cosa vorresti", "di cosa vorresti", "che tipo di storia",
                        "dimmi tu", "scegli tu", "preferisci"]
    is_redirect = any(r in resp_lower for r in redirect_phrases)

    # Should have narrative content
    narrative_indicators = ["c'era", "una volta", "un giorno", "immagina", "racconto",
                            "storia", "uomo", "donna", "ragazza", "ragazzo", "citta",
                            "paese", "notte", "mattina", "trovo", "disse", "lanterna",
                            "pescatore", "mare", "lettera"]
    has_narrative = any(n in resp_lower for n in narrative_indicators)

    print(f"  -> Risposta ({word_count} parole): {response[:200]}...")
    check("genera storia vera (non rimanda)", not is_redirect)
    check("contiene contenuto narrativo", has_narrative)
    check(">=50 parole", word_count >= 50, f"got {word_count}")


async def test_ciao_input():
    print("\n===== TEST 3: Input ciao =====")
    await cleanup()
    await memory_brain.update_brain(TEST_USER, "Mi chiamo Luca")

    response, bs = await full_pipeline("ciao")
    words = response.split()
    word_count = len(words)

    print(f"  -> Risposta ({word_count} parole): {response[:200]}...")
    check("saluto espanso (non solo Ciao)", word_count > 5, f"got {word_count}")
    check("non e' solo 'Ciao!'", word_count > 3)


async def test_anti_passive():
    print("\n===== TEST 4: Anti-passive =====")
    await cleanup()

    # Simulate what the engine does with passive standalone responses
    brain_state = {
        "emotion": {"emotion": "neutral", "intensity": 0.3, "vulnerability": 0.0},
        "latent": {"emotional_resonance": 0.5, "curiosity": 0.5,
                   "attachment": 0.5, "stability": 0.5, "relational_energy": 0.5},
        "profile": {"name": "Test"},
        "relational": {"trust": 0.3, "stage": "initial"},
        "episodes": [],
    }

    passive_inputs = [
        "Ti ascolto.",
        "Dimmi pure.",
        "Raccontami.",
        "Sono qui. Dimmi pure.",
    ]

    for passive in passive_inputs:
        enhanced = emotional_intensity_engine.enhance(passive, "come stai?", brain_state)
        word_count = len(enhanced.split())
        check(f"'{passive}' espansa (>{10} parole)", word_count > 10, f"got {word_count}: {enhanced[:80]}")


async def test_emotional_exploration():
    print("\n===== TEST 5: Esplorazione emotiva =====")
    await cleanup()
    await memory_brain.update_brain(TEST_USER, "Mi chiamo Sara")

    response, bs = await full_pipeline("ho paura di non farcela, mi sento inadeguata")
    words = response.split()
    word_count = len(words)
    has_question = "?" in response

    print(f"  -> Risposta ({word_count} parole): {response[:200]}...")
    check("risposta non vuota (vulnerabilita')", word_count >= 5, f"got {word_count}")
    check("contiene domanda esplorativa", has_question)


async def test_no_extra_llm():
    print("\n===== TEST 6: Nessuna chiamata LLM extra =====")
    await cleanup()

    # The emotional intensity engine is pure local — no API calls
    brain_state = {
        "emotion": {"emotion": "sad", "intensity": 0.7, "vulnerability": 0.6},
        "latent": {"emotional_resonance": 0.7, "curiosity": 0.6,
                   "attachment": 0.6, "stability": 0.5, "relational_energy": 0.6},
        "profile": {"name": "Test"},
        "relational": {"trust": 0.4, "stage": "developing"},
        "episodes": [],
    }

    # This should work without any API call
    result = emotional_intensity_engine.enhance(
        "Sono qui.", "mi sento triste", brain_state
    )
    check("enhance() funziona senza LLM", len(result) > 0)
    check("risultato espanso", len(result.split()) > 10)


async def test_response_mode():
    print("\n===== TEST 7: Response mode probabilistic =====")
    await cleanup()

    brain_state = {
        "emotion": {"emotion": "neutral", "intensity": 0.3, "vulnerability": 0.0},
        "latent": {"emotional_resonance": 0.5, "curiosity": 0.5,
                   "attachment": 0.5, "stability": 0.5, "relational_energy": 0.5},
        "profile": {"name": ""},
        "relational": {"trust": 0.3, "stage": "initial"},
        "episodes": [],
    }

    # Run 20 times and check we get variation in length
    import random
    random.seed(42)
    lengths = []
    for _ in range(20):
        result = emotional_intensity_engine.enhance(
            "Capisco quello che dici. E' una situazione complessa che richiede attenzione.",
            "come stai?", brain_state
        )
        lengths.append(len(result.split()))

    min_len = min(lengths)
    max_len = max(lengths)
    print(f"  -> Lengths: min={min_len} max={max_len} spread={max_len - min_len}")
    check("variazione lunghezza (spread > 0)", max_len > min_len, f"min={min_len} max={max_len}")
    check("almeno una risposta breve (<20 parole)", min_len < 20, f"min={min_len}")


async def test_empathic_blocker():
    print("\n===== TEST 8: Empathic phrase blocker =====")
    await cleanup()

    brain_state = {
        "emotion": {"emotion": "sad", "intensity": 0.7, "vulnerability": 0.5},
        "latent": {"emotional_resonance": 0.7, "curiosity": 0.5,
                   "attachment": 0.5, "stability": 0.5, "relational_energy": 0.5},
        "profile": {"name": ""},
        "relational": {"trust": 0.4, "stage": "developing"},
        "episodes": [],
    }

    # Reset engine state
    emotional_intensity_engine._recent_responses.clear()
    emotional_intensity_engine._recent_inputs.clear()

    # First call: "sono qui con te" should pass
    r1 = emotional_intensity_engine.enhance(
        "Sono qui con te. Capisco il tuo dolore.", "mi sento triste", brain_state
    )
    # Second call: same phrase should be stripped
    r2 = emotional_intensity_engine.enhance(
        "Sono qui con te. Capisco il tuo dolore.", "sono molto triste", brain_state
    )
    print(f"  -> R1: {r1[:80]}...")
    print(f"  -> R2: {r2[:80]}...")
    check("seconda volta 'sono qui con te' rimossa", "sono qui con te" not in r2.lower())


async def test_repeated_input():
    print("\n===== TEST 9: Repeated input 3x =====")
    await cleanup()

    brain_state = {
        "emotion": {"emotion": "sad", "intensity": 0.5, "vulnerability": 0.3},
        "latent": {"emotional_resonance": 0.5, "curiosity": 0.5,
                   "attachment": 0.5, "stability": 0.5, "relational_energy": 0.5},
        "profile": {"name": ""},
        "relational": {"trust": 0.3, "stage": "initial"},
        "episodes": [],
    }

    # Reset engine state
    emotional_intensity_engine._recent_responses.clear()
    emotional_intensity_engine._recent_inputs.clear()

    msg = "mi sento male"
    r1 = emotional_intensity_engine.enhance("Capisco.", msg, brain_state)
    r2 = emotional_intensity_engine.enhance("Capisco.", msg, brain_state)
    r3 = emotional_intensity_engine.enhance("Capisco.", msg, brain_state)

    print(f"  -> R1: {r1[:80]}")
    print(f"  -> R2: {r2[:80]}")
    print(f"  -> R3 (direct): {r3[:80]}")

    # R3 should be direct style (from DIRECT_STYLE_RESPONSES)
    direct_indicators = ["gia' detto", "cosa vuoi", "ripetendo", "cosa cambi",
                         "cosa fai", "prossimo passo", "agire", "decidere"]
    is_direct = any(d in r3.lower() for d in direct_indicators)
    check("3a ripetizione = stile diretto", is_direct, f"got: {r3[:60]}")
    check("R3 diversa da R1", r3 != r1)


async def main():
    print("=" * 55)
    print("GENESI v3 - EMOTIONAL INTENSITY ENGINE TESTS")
    print("=" * 55)

    await cleanup()
    await test_depressed_input()
    await cleanup()
    await test_narrative_input()
    await cleanup()
    await test_ciao_input()
    await test_anti_passive()
    await cleanup()
    await test_emotional_exploration()
    await test_no_extra_llm()
    await test_response_mode()
    await test_empathic_blocker()
    await test_repeated_input()
    await cleanup()

    print("\n" + "=" * 55)
    print(f"RISULTATI: {passed} passed, {failed} failed")
    print("=" * 55)

    if failed == 0:
        print("\nOK - EMOTIONAL INTENSITY ENGINE OPERATIVO")
    else:
        print(f"\nATTENZIONE: {failed} test falliti")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
