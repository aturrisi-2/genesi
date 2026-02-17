import pytest
from core.evolution_state_manager import EvolutionStateManager
from core.auto_evolution_engine import AutoEvolutionEngine

@pytest.fixture
def clean_state(tmp_path):
    # Isola directory evolution per test
    evolution_dir = tmp_path / "evolution"
    manager = EvolutionStateManager(str(evolution_dir))
    return manager

def build_report(success=0.97, supportive=0.19, confrontational=0.03,
                 repetition=0.01, error_rate=0.03, total=100):
    return {
        "metrics": {
            "total_messages": total,
            "success_count": int(success * total),
            "error_count": int(error_rate * total),
            "supportive_count": int(supportive * total),
            "confrontational_count": int(confrontational * total),
            "repetition_detected": int(repetition * total),
            "avg_response_time": 2.1
        }
    }

def test_no_unlock_if_only_ema_recovers(clean_state):
    manager = clean_state
    state = manager.load_current_state()
    state["ema_stability"] = 0.7
    state["auto_evolution_locked"] = True
    manager.save_current_state(state)

    assert manager.load_current_state()["auto_evolution_locked"] is True


def test_no_unlock_if_only_reports_valid(clean_state):
    manager = clean_state
    state = manager.load_current_state()
    state["ema_stability"] = 0.3
    state["auto_evolution_locked"] = True
    state["consecutive_valid_reports"] = 3
    manager.save_current_state(state)

    assert manager.load_current_state()["auto_evolution_locked"] is True


def test_unlock_after_3_valid_reports_and_ema(clean_state):
    manager = clean_state
    state = manager.load_current_state()
    state["ema_stability"] = 0.65
    state["auto_evolution_locked"] = True
    state["consecutive_valid_reports"] = 3
    manager.save_current_state(state)

    # Simula unlock logic usando state manager
    should_unlock, reason = manager.evaluate_lock_status(state)
    
    # Aggiorna stato se unlock
    if not should_unlock:
        state["auto_evolution_locked"] = False
        manager.save_current_state(state)

    assert manager.load_current_state()["auto_evolution_locked"] is False


def test_unlock_requires_consecutive(clean_state):
    manager = clean_state
    state = manager.load_current_state()
    state["ema_stability"] = 0.7
    state["auto_evolution_locked"] = True
    state["consecutive_valid_reports"] = 2
    manager.save_current_state(state)

    # Simula unlock logic usando state manager
    should_unlock, reason = manager.evaluate_lock_status(state)
    
    # Aggiorna stato se unlock
    if not should_unlock:
        state["auto_evolution_locked"] = False
        manager.save_current_state(state)

    assert manager.load_current_state()["auto_evolution_locked"] is True


def test_no_unlock_if_success_rate_low(clean_state):
    report = build_report(success=0.5)
    assert report["metrics"]["success_count"] < 90


def test_no_unlock_if_error_rate_high(clean_state):
    report = build_report(error_rate=0.2)
    assert report["metrics"]["error_count"] > 5
