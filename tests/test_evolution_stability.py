import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.auto_evolution_engine import EVOLUTION_MAX_DELTA, EVOLUTION_MIN_MESSAGES_BETWEEN_SHIFTS

def test_max_delta_constants_exist():
    assert "supportive_intensity" in EVOLUTION_MAX_DELTA
    assert "confrontational_intensity" in EVOLUTION_MAX_DELTA
    # max_questions_per_response può essere >0.1 perché è un conteggio, non un parametro 0-1
    intensity_params = {k: v for k, v in EVOLUTION_MAX_DELTA.items() if k != "max_questions_per_response"}
    assert all(v <= 0.1 for v in intensity_params.values()), "max_delta troppo alto per parametri intensità"

def test_throttling_constant_exists():
    assert EVOLUTION_MIN_MESSAGES_BETWEEN_SHIFTS >= 5

def test_confrontational_more_conservative():
    assert EVOLUTION_MAX_DELTA["confrontational_intensity"] <= EVOLUTION_MAX_DELTA["supportive_intensity"]

def test_evolution_delta_clamp_method():
    from core.auto_evolution_engine import AutoEvolutionEngine
    engine = AutoEvolutionEngine()
    
    # Test clamp normale
    result = engine._apply_clamped_delta("supportive_intensity", 0.5, 0.52)
    assert result == 0.52, "Delta normale non clampato"
    
    # Test clamp eccessivo
    result = engine._apply_clamped_delta("supportive_intensity", 0.5, 0.6)
    assert result == 0.55, "Delta eccessivo non clampato correttamente"
    
    # Test clamp negativo
    result = engine._apply_clamped_delta("supportive_intensity", 0.5, 0.3)
    assert result == 0.45, "Delta negativo non clampato correttamente"

def test_clamped_delta_actually_clamps():
    from core.auto_evolution_engine import AutoEvolutionEngine, EVOLUTION_MAX_DELTA
    engine = AutoEvolutionEngine()
    max_d = EVOLUTION_MAX_DELTA["supportive_intensity"]
    result = engine._apply_clamped_delta("supportive_intensity", 0.1, 0.9)
    assert abs(result - 0.1) <= max_d + 0.001, f"Clamping non funziona: {result}"

def test_meta_governance_block_method():
    from core.meta_governance_engine import MetaGovernanceEngine
    engine = MetaGovernanceEngine()
    
    # Test senza previous params
    block, reason = engine.should_block_evolution({"a": 0.5}, {})
    assert not block, "Dovrebbe permettere evoluzione senza previous params"
    
    # Test drift normale
    block, reason = engine.should_block_evolution({"a": 0.52}, {"a": 0.5})
    assert not block, "Dovrebbe permettere drift normale"
    
    # Test drift eccessivo
    block, reason = engine.should_block_evolution({"a": 0.7}, {"a": 0.5})
    assert block, "Dovrebbe bloccare drift eccessivo"
    assert "single_param_drift" in reason

def test_drift_recentering_method():
    from core.drift_modulator import DriftModulator, DRIFT_CENTER, DRIFT_RECENTERING_RATE
    modulator = DriftModulator()
    
    # Test recentering verso centro
    result = modulator._apply_recentering(0.7)
    expected = 0.7 - DRIFT_RECENTERING_RATE
    assert abs(result - expected) < 0.001, "Recentering non calcolato correttamente"
    
    # Test recentering da sotto
    result = modulator._apply_recentering(0.3)
    expected = 0.3 + DRIFT_RECENTERING_RATE
    assert abs(result - expected) < 0.001, "Recentering non calcolato correttamente"
    
    # Test già centrato
    result = modulator._apply_recentering(DRIFT_CENTER)
    assert result == DRIFT_CENTER, "Valore già centrato non dovrebbe cambiare"
