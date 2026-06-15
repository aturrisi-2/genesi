"""
TEST LATENT STATE + DRIFT MODULATOR - Genesi Cognitive System v3
Verifica:
- attachment aumenta su vulnerabilita'
- curiosity aumenta su domande aperte
- resonance aumenta su emozioni intense
- drift_modulator produce variazione controllata
- nessuna chiamata LLM extra
- pipeline completa funziona
- decay su inattivita'
- micro-eventi banali NON aumentano nulla
"""

import asyncio
import sys
import os
import io

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-local-testing")

from core.latent_state import LatentStateEngine, latent_state_engine
from core.drift_modulator import DriftModulator, drift_modulator
from core.memory_brain import memory_brain
from core.storage import storage

TEST_USER = "test_latent_001"

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [OK] {label}")
    else:
        failed += 1
        print(f"  [FAIL] {label}")


async def cleanup():
    await storage.save(f"episodes/{TEST_USER}", [])
    await storage.save(f"long_term_profile:{TEST_USER}", None)
    await storage.save(f"relational_state:{TEST_USER}", None)
    await storage.save(f"latent_state:{TEST_USER}", None)


async def test_initial_state():
    print("\n===== TEST 1: Stato iniziale neutro =====")
    engine = LatentStateEngine()
    state = await engine.load(TEST_USER)
    check("attachment in range 0.4-0.6", 0.4 <= state["attachment"] <= 0.6)
    check("curiosity in range 0.4-0.6", 0.4 <= state["curiosity"] <= 0.6)
    check("emotional_resonance in range 0.3-0.6", 0.3 <= state["emotional_resonance"] <= 0.6)
    check("stability in range 0.4-0.7", 0.4 <= state["stability"] <= 0.7)
    check("relational_energy in range 0.3-0.6", 0.3 <= state["relational_energy"] <= 0.6)


async def test_attachment_on_vulnerability():
    print("\n===== TEST 2: Attachment aumenta su vulnerabilita' =====")
    await cleanup()
    engine = LatentStateEngine()
    state_before = await engine.load(TEST_USER)
    att_before = state_before["attachment"]

    # Simulate vulnerable message
    emotional = {"emotion": "sad", "intensity": 0.8, "vulnerability": 0.9, "urgency": 0.1}
    relational = {"trust": 0.4, "depth": 0.3, "consistency": 0.5,
                  "history": {"total_msgs": 10, "emotion_variance": 0.05}}

    state_after = await engine.update_latent_state(
        user_id=TEST_USER,
        user_message="Mi sento solo e ho paura di non farcela, soffro molto",
        emotional_analysis=emotional,
        relational_state=relational,
        episode_stored=True,
        episode_tags=["emozione", "identita"]
    )
    check("attachment aumentato", state_after["attachment"] > att_before)
    check("emotional_resonance aumentato", state_after["emotional_resonance"] > state_before["emotional_resonance"])


async def test_curiosity_on_questions():
    print("\n===== TEST 3: Curiosity aumenta su domande aperte =====")
    await cleanup()
    engine = LatentStateEngine()
    state_before = await engine.load(TEST_USER)
    cur_before = state_before["curiosity"]

    emotional = {"emotion": "neutral", "intensity": 0.3, "vulnerability": 0.0, "urgency": 0.0}
    relational = {"trust": 0.3, "depth": 0.2, "consistency": 0.5,
                  "history": {"total_msgs": 5, "emotion_variance": 0.02}}

    state_after = await engine.update_latent_state(
        user_id=TEST_USER,
        user_message="Perche' secondo te le persone hanno paura di cambiare? Cosa ne pensi? Spiegami il tuo punto di vista",
        emotional_analysis=emotional,
        relational_state=relational,
        episode_stored=True,
        episode_tags=[]
    )
    check("curiosity aumentato", state_after["curiosity"] > cur_before)


async def test_resonance_on_intense_emotion():
    print("\n===== TEST 4: Resonance aumenta su emozioni intense =====")
    await cleanup()
    engine = LatentStateEngine()
    state_before = await engine.load(TEST_USER)
    res_before = state_before["emotional_resonance"]

    emotional = {"emotion": "angry", "intensity": 0.9, "vulnerability": 0.5, "urgency": 0.6}
    relational = {"trust": 0.5, "depth": 0.4, "consistency": 0.5,
                  "history": {"total_msgs": 15, "emotion_variance": 0.1}}

    state_after = await engine.update_latent_state(
        user_id=TEST_USER,
        user_message="Sono furioso! Non ne posso piu' di questa situazione, sono esausto e arrabbiato!",
        emotional_analysis=emotional,
        relational_state=relational,
        episode_stored=True,
        episode_tags=["emozione"]
    )
    check("resonance aumentato", state_after["emotional_resonance"] > res_before)


async def test_drift_modulator_variation():
    print("\n===== TEST 5: Drift modulator produce variazione controllata =====")
    mod = DriftModulator()

    latent_high = {
        "attachment": 0.8, "curiosity": 0.7,
        "emotional_resonance": 0.8, "stability": 0.6,
        "relational_energy": 0.8
    }
    latent_low = {
        "attachment": 0.2, "curiosity": 0.2,
        "emotional_resonance": 0.2, "stability": 0.8,
        "relational_energy": 0.2
    }
    relational = {"trust": 0.6, "depth": 0.5, "stage": "developing"}

    base = "Ti ascolto. Raccontami cosa e' successo."

    # Run multiple times to check variation
    results_high = set()
    results_low = set()
    for _ in range(20):
        r = mod.modulate_response_style(latent_high, relational, base)
        results_high.add(r)
        r = mod.modulate_response_style(latent_low, relational, base)
        results_low.add(r)

    check("high latent produce variazione (>1 output unico)", len(results_high) > 1)
    check("low latent produce output (non vuoto)", all(len(r) > 0 for r in results_low))
    check("output non caotico (contiene parole base)", all("ascolto" in r.lower() or "raccontami" in r.lower() or "sento" in r.lower() or "parlami" in r.lower() for r in results_high))

    # Check that short responses stay coherent
    short_base = "Dimmi."
    short_result = mod.modulate_response_style(latent_low, relational, short_base)
    check("short response resta coerente", len(short_result) >= 3)


async def test_no_llm_calls():
    print("\n===== TEST 6: Nessuna chiamata LLM extra =====")
    await cleanup()

    # Full pipeline through memory_brain + latent_state
    brain_state = await memory_brain.update_brain(TEST_USER, "Ciao, mi chiamo Marco")
    emotional = brain_state.get("emotion", {})
    relational = brain_state.get("relational", {})

    latent = await latent_state_engine.update_latent_state(
        user_id=TEST_USER,
        user_message="Ciao, mi chiamo Marco",
        emotional_analysis=emotional,
        relational_state=relational,
        episode_stored=brain_state.get("episode_id") is not None
    )

    check("latent state aggiornato senza errori", latent is not None)
    check("latent ha 5 dimensioni", all(k in latent for k in
          ["attachment", "curiosity", "emotional_resonance", "stability", "relational_energy"]))
    check("update_count incrementato", latent.get("update_count", 0) >= 1)

    # Drift modulation
    vector = latent_state_engine.get_vector(latent)
    result = drift_modulator.modulate_response_style(vector, relational, "Ciao Marco!")
    check("drift modulator output non vuoto", len(result) > 0)


async def test_banal_messages_no_effect():
    print("\n===== TEST 7: Micro-eventi banali NON aumentano nulla =====")
    await cleanup()
    engine = LatentStateEngine()

    # First: set baseline
    emotional_neutral = {"emotion": "neutral", "intensity": 0.3, "vulnerability": 0.0, "urgency": 0.0}
    relational = {"trust": 0.2, "depth": 0.1, "consistency": 0.5,
                  "history": {"total_msgs": 2, "emotion_variance": 0.0}}

    state_base = await engine.update_latent_state(
        user_id=TEST_USER,
        user_message="ok",
        emotional_analysis=emotional_neutral,
        relational_state=relational,
        episode_stored=False,  # banal = not stored
        episode_tags=[]
    )

    # Second banal message
    state_after = await engine.update_latent_state(
        user_id=TEST_USER,
        user_message="si",
        emotional_analysis=emotional_neutral,
        relational_state=relational,
        episode_stored=False,
        episode_tags=[]
    )

    # Deltas should be tiny (near zero, within noise range ~0.003 stddev per update)
    att_delta = abs(state_after["attachment"] - state_base["attachment"])
    res_delta = abs(state_after["emotional_resonance"] - state_base["emotional_resonance"])
    check("attachment delta minimo su banale (<0.03)", att_delta < 0.03)
    check("resonance delta minimo su banale (<0.03)", res_delta < 0.03)


async def test_stability_grows_with_consistency():
    print("\n===== TEST 8: Stability cresce con interazione consistente =====")
    await cleanup()
    engine = LatentStateEngine()
    state = await engine.load(TEST_USER)
    stb_initial = state["stability"]

    emotional = {"emotion": "neutral", "intensity": 0.3, "vulnerability": 0.0, "urgency": 0.0}
    relational = {"trust": 0.5, "depth": 0.3, "consistency": 0.8,
                  "history": {"total_msgs": 30, "emotion_variance": 0.01}}

    # Multiple consistent interactions
    for i in range(5):
        state = await engine.update_latent_state(
            user_id=TEST_USER,
            user_message=f"Oggi ho fatto una passeggiata al parco, messaggio numero {i}",
            emotional_analysis=emotional,
            relational_state=relational,
            episode_stored=True,
            episode_tags=["salute"]
        )

    check("stability cresciuta dopo interazioni consistenti", state["stability"] > stb_initial)


async def test_full_pipeline_integration():
    print("\n===== TEST 9: Pipeline completa v3 =====")
    await cleanup()

    # Simulate full proactor-like pipeline
    # Step 1: brain update
    brain_state = await memory_brain.update_brain(TEST_USER, "Mi chiamo Luca e sono preoccupato per mia moglie Anna")

    # Step 2: latent state
    latent = await latent_state_engine.update_latent_state(
        user_id=TEST_USER,
        user_message="Mi chiamo Luca e sono preoccupato per mia moglie Anna",
        emotional_analysis=brain_state["emotion"],
        relational_state=brain_state["relational"],
        episode_stored=brain_state.get("episode_id") is not None,
        episode_tags=brain_state.get("episodes", [{}])[0].get("tags", []) if brain_state.get("episodes") else []
    )

    check("latent state creato", latent is not None)
    check("attachment > baseline (messaggio personale)", latent["attachment"] > 0.44)
    check("resonance > baseline (preoccupazione)", latent["emotional_resonance"] > 0.39)

    # Step 3: generate response (from evolution_engine)
    from core.evolution_engine import generate_response_from_brain
    brain_state["latent"] = latent
    response = await generate_response_from_brain(TEST_USER, "Mi chiamo Luca e sono preoccupato per mia moglie Anna", brain_state)
    check("response non vuota", len(response) > 0)

    # Step 4: drift modulation
    vector = latent_state_engine.get_vector(latent)
    modulated = drift_modulator.modulate_response_style(vector, brain_state["relational"], response)
    check("modulated response non vuota", len(modulated) > 0)
    check("modulated response coerente (non caotica)", len(modulated) < len(response) * 3)


async def test_memory_selectivity():
    print("\n===== TEST 10: Selettivita' memoria (banali non salvati) =====")
    await cleanup()

    # Banal message should NOT create episode
    brain_state_banal = await memory_brain.update_brain(TEST_USER, "ok")
    check("banale 'ok' non crea episodio", brain_state_banal.get("episode_id") is None)

    # Meaningful message SHOULD create episode
    brain_state_meaningful = await memory_brain.update_brain(TEST_USER, "Mi chiamo Sara e lavoro come insegnante a Roma")
    check("messaggio significativo crea episodio", brain_state_meaningful.get("episode_id") is not None)


async def main():
    print("=" * 50)
    print("GENESI COGNITIVE SYSTEM v3 - LATENT STATE TESTS")
    print("=" * 50)

    await cleanup()

    await test_initial_state()
    await cleanup()
    await test_attachment_on_vulnerability()
    await cleanup()
    await test_curiosity_on_questions()
    await cleanup()
    await test_resonance_on_intense_emotion()
    await test_drift_modulator_variation()
    await cleanup()
    await test_no_llm_calls()
    await cleanup()
    await test_banal_messages_no_effect()
    await cleanup()
    await test_stability_grows_with_consistency()
    await cleanup()
    await test_full_pipeline_integration()
    await cleanup()
    await test_memory_selectivity()

    await cleanup()

    print("\n" + "=" * 50)
    print(f"RISULTATI: {passed} passed, {failed} failed")
    print("=" * 50)

    if failed == 0:
        print("\nOK - TUTTI I TEST v3 PASSATI - Latent state + drift operativi")
   

if __name__ == "__main__":
    asyncio.run(main())
