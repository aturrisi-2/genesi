"""
GENESI - Memory Brain Resilience Tests
Tests _safe_emotion_label and consolidation robustness.
"""

import asyncio
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-local-testing")

from core.memory_brain import (
    _safe_emotion_label,
    ConsolidationEngine,
    memory_brain,
)

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        print(f"  [OK] {label}")
        passed += 1
    else:
        print(f"  [FAIL] {label}")
        failed += 1


# ═══════════════════════════════════════════════════════════════
# TEST 1: _safe_emotion_label — string input
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 1: emotion as string =====")
check("'sad' -> 'sad'", _safe_emotion_label("sad") == "sad")
check("'happy' -> 'happy'", _safe_emotion_label("happy") == "happy")
check("'neutral' -> 'neutral'", _safe_emotion_label("neutral") == "neutral")
check("'' -> ''", _safe_emotion_label("") == "")

# ═══════════════════════════════════════════════════════════════
# TEST 2: _safe_emotion_label — dict with "label" key
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 2: emotion as dict with 'label' =====")
check("dict label='angry'", _safe_emotion_label({"label": "angry", "score": 0.9}) == "angry")
check("dict label=None", _safe_emotion_label({"label": None}) == "neutral")
check("dict label=''", _safe_emotion_label({"label": ""}) == "neutral")

# ═══════════════════════════════════════════════════════════════
# TEST 3: _safe_emotion_label — dict with "emotion" key
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 3: emotion as dict with 'emotion' =====")
check("dict emotion='sad'", _safe_emotion_label({"emotion": "sad", "intensity": 0.8}) == "sad")
check("dict emotion=None", _safe_emotion_label({"emotion": None}) == "neutral")

# ═══════════════════════════════════════════════════════════════
# TEST 4: _safe_emotion_label — None
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 4: emotion as None =====")
check("None -> 'neutral'", _safe_emotion_label(None) == "neutral")

# ═══════════════════════════════════════════════════════════════
# TEST 5: _safe_emotion_label — missing emotion key in episode
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 5: episode dict without 'emotion' key =====")
ep_no_emotion = {"msg": "ciao", "intensity": 0.5}
check("no emotion key -> passthrough to raw handling", isinstance(_safe_emotion_label(ep_no_emotion), str))

# ═══════════════════════════════════════════════════════════════
# TEST 6: _safe_emotion_label — nested dict (emotion is dict inside episode)
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 6: nested structure (emotion is dict inside episode) =====")
ep_nested = {"emotion": {"label": "anxious", "score": 0.7, "sub": {"detail": "panic"}}}
result = _safe_emotion_label(ep_nested)
check(f"nested dict -> '{result}' (should be 'anxious')", result == "anxious")

ep_nested2 = {"emotion": {"emotion": "fearful", "intensity": 0.9}}
result2 = _safe_emotion_label(ep_nested2)
check(f"nested emotion key -> '{result2}' (should be 'fearful')", result2 == "fearful")

ep_nested_empty = {"emotion": {}}
result3 = _safe_emotion_label(ep_nested_empty)
check(f"empty nested dict -> '{result3}' (should be 'neutral')", result3 == "neutral")

# ═══════════════════════════════════════════════════════════════
# TEST 7: _safe_emotion_label — exotic types (int, list, bool)
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 7: exotic types =====")
check("int 42 -> str", isinstance(_safe_emotion_label(42), str))
check("list -> str", isinstance(_safe_emotion_label(["sad", "happy"]), str))
check("bool True -> str", isinstance(_safe_emotion_label(True), str))
check("float 0.5 -> str", isinstance(_safe_emotion_label(0.5), str))

# ═══════════════════════════════════════════════════════════════
# TEST 8: _safe_emotion_label — episode with string emotion (normal case)
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 8: normal episode with string emotion =====")
ep_normal = {"emotion": "sad", "intensity": 0.8, "msg": "mi sento triste"}
check("normal episode -> 'sad'", _safe_emotion_label(ep_normal) == "sad")

# ═══════════════════════════════════════════════════════════════
# TEST 9: Counter compatibility — mixed emotion types
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 9: Counter with mixed emotion types =====")
from collections import Counter
mixed_episodes = [
    {"emotion": "sad", "msg": "triste"},
    {"emotion": {"label": "sad"}, "msg": "molto triste"},
    {"emotion": None, "msg": "boh"},
    {"emotion": "happy", "msg": "felice"},
    {"msg": "senza emotion"},  # missing key
    {"emotion": {"emotion": "sad", "intensity": 0.9}, "msg": "ancora triste"},
]
try:
    counts = Counter(_safe_emotion_label(e) for e in mixed_episodes)
    check("Counter works with mixed types", True)
    check(f"sad count = {counts.get('sad', 0)} (expected 3)", counts.get("sad", 0) == 3)
    check(f"happy count = {counts.get('happy', 0)} (expected 1)", counts.get("happy", 0) == 1)
    check(f"neutral count = {counts.get('neutral', 0)} (expected 2: None + missing key)", counts.get("neutral", 0) == 2)
except TypeError as e:
    check(f"Counter should not crash: {e}", False)

# ═══════════════════════════════════════════════════════════════
# TEST 10: ConsolidationEngine._extract_patterns with mixed episodes
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 10: _extract_patterns with mixed emotion types =====")
ce = ConsolidationEngine()
test_episodes = [
    {"emotion": "sad", "msg": "triste", "tags": ["famiglia"]},
    {"emotion": {"label": "sad"}, "msg": "molto triste", "tags": ["famiglia"]},
    {"emotion": None, "msg": "boh", "tags": []},
    {"emotion": "happy", "msg": "felice", "tags": ["lavoro"]},
    {"emotion": {"emotion": "sad"}, "msg": "ancora", "tags": ["famiglia"]},
]
try:
    patterns = ce._extract_patterns(test_episodes)
    check("_extract_patterns does not crash", True)
    emotion_patterns = [p for p in patterns if p["type"] == "emotion"]
    sad_pattern = [p for p in emotion_patterns if p["key"] == "sad"]
    check(f"sad pattern found with frequency >= 2", len(sad_pattern) > 0 and sad_pattern[0]["frequency"] >= 2)
except Exception as e:
    check(f"_extract_patterns should not crash: {e}", False)

# ═══════════════════════════════════════════════════════════════
# TEST 11: ConsolidationEngine._extract_traits with mixed episodes
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 11: _extract_traits with mixed emotion types =====")
try:
    traits = ce._extract_traits(test_episodes)
    check("_extract_traits does not crash", True)
    check("has communication trait", any(t["type"] == "communication" for t in traits))
except Exception as e:
    check(f"_extract_traits should not crash: {e}", False)

# ═══════════════════════════════════════════════════════════════
# TEST 12: Consolidation fail-safe (update_brain doesn't crash)
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 12: Consolidation fail-safe =====")


async def test_consolidation_failsafe():
    try:
        brain_state = await memory_brain.update_brain("test_memory_safe_001", "mi sento triste e solo")
        check("update_brain returns brain_state", brain_state is not None)
        check("brain_state has emotion", "emotion" in brain_state)
        check("brain_state has relational", "relational" in brain_state)
        return True
    except Exception as e:
        check(f"update_brain should not crash: {e}", False)
        return False


asyncio.run(test_consolidation_failsafe())

# ═══════════════════════════════════════════════════════════════
# TEST 13: _safe_emotion_label never raises
# ═══════════════════════════════════════════════════════════════
print("\n===== TEST 13: _safe_emotion_label never raises =====")
edge_cases = [
    None, "", "sad", 0, 42, 3.14, True, False,
    [], [1, 2], {}, {"label": "x"}, {"emotion": "y"},
    {"emotion": {"label": "z"}}, {"emotion": None},
    {"emotion": {"emotion": None}}, {"emotion": []},
    {"emotion": 123}, {"emotion": True},
    object(),
]
all_safe = True
for i, case in enumerate(edge_cases):
    try:
        result = _safe_emotion_label(case)
        if not isinstance(result, str):
            print(f"  [FAIL] case {i}: returned non-string {type(result)}")
            all_safe = False
    except Exception as e:
        print(f"  [FAIL] case {i}: raised {e}")
        all_safe = False
check(f"all {len(edge_cases)} edge cases return string without exception", all_safe)


# ═══════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*55}")
print(f"RISULTATI: {passed} passed, {failed} failed")
print(f"{'='*55}")

if failed > 0:
    print("\nFAILED - Ci sono test falliti")
    sys.exit(1)
else:
    print("\nOK - MEMORY BRAIN RESILIENCE TESTS PASSATI")
    sys.exit(0)
