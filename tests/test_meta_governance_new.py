"""
Test del Meta-Governance Engine e Costituzione
Verifica funzionalità core del sistema di sovragovernanza.
"""

import pytest
import asyncio
from core.constitution import GenesisConstitution
from core.meta_governance_engine import MetaGovernanceEngine


class TestConstitution:
    """Test della Costituzione Immutabile."""
    
    def test_constitution_loads(self):
        """Verifica che GenesisConstitution si importi e get_principles() ritorni un dict non vuoto."""
        principles = GenesisConstitution.get_principles()
        assert isinstance(principles, dict)
        assert len(principles) > 0
        assert "identity" in principles
        assert "ethics" in principles
    
    def test_constitution_validate_valid(self):
        """Proposta compatibile ritorna (True, [])."""
        # Proposta valida entro i limiti
        valid_proposal = {
            "supportive_intensity": 0.5,
            "attuned_intensity": 0.6,
            "max_questions_per_response": 2
        }
        
        is_valid, violations = GenesisConstitution.validate_against(valid_proposal)
        assert is_valid is True
        assert len(violations) == 0
    
    def test_constitution_validate_invalid(self):
        """Proposta che viola un hard constraint ritorna (False, [])."""
        # Proposta con valore fuori limiti
        invalid_proposal = {
            "supportive_intensity": 1.5,  # Fuori dal range [0.1, 0.9]
            "max_questions_per_response": 10  # Fuori dal range [0, 5]
        }
        
        is_valid, violations = GenesisConstitution.validate_against(invalid_proposal)
        assert is_valid is False
        assert len(violations) > 0
        assert any("supportive_intensity" in v for v in violations)


class TestMetaGovernanceEngine:
    """Test del Meta-Governance Engine."""
    
    @pytest.fixture
    async def engine(self):
        """Fixture per istanza MetaGovernanceEngine."""
        return MetaGovernanceEngine()
    
    def test_meta_governance_init(self, engine):
        """MetaGovernanceEngine() si istanzia senza eccezioni."""
        assert engine is not None
        assert hasattr(engine, '_epistemic_quality_history')
        assert hasattr(engine, '_banality_history')
        assert hasattr(engine, '_drift_snapshots')
        assert hasattr(engine, '_proposed_shifts')
        assert hasattr(engine, '_rejected_shifts')
    
    @pytest.mark.asyncio
    async def test_epistemic_quality_range(self, engine):
        """analyze_epistemic_quality ritorna float tra 0.0 e 1.0."""
        message = "Mi sento confuso e non so cosa fare"
        response = "Capisco la tua confusione. Cosa ti impedisce di vedere chiaramente la situazione?"
        
        score = await engine.analyze_epistemic_quality(message, response)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
    
    @pytest.mark.asyncio
    async def test_banality_range(self, engine):
        """analyze_banality ritorna float tra 0.0 e 1.0."""
        message = "Come stai?"
        response = "Ok."
        
        score = await engine.analyze_banality(message, response)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
    
    @pytest.mark.asyncio
    async def test_drift_no_history(self, engine):
        """detect_drift con dict vuoto ritorna drift_detected: False."""
        params = {}
        
        drift_info = await engine.detect_drift(params)
        assert isinstance(drift_info, dict)
        assert drift_info["drift_detected"] is False
        assert drift_info["drift_magnitude"] == 0.0
        assert len(drift_info["drifted_params"]) == 0
    
    @pytest.mark.asyncio
    async def test_propose_shift_valid(self, engine):
        """Shift valido viene aggiunto a _proposed_shifts."""
        reason = "Test shift valido"
        target_param = "supportive_intensity"
        delta = 0.1
        
        proposal = await engine.propose_micro_shift(reason, target_param, delta)
        
        assert isinstance(proposal, dict)
        assert len(proposal) > 0
        assert "id" in proposal
        assert proposal["status"] == "pending"
        assert proposal["target_param"] == target_param
        assert proposal["delta"] == delta
        
        # Verifica che sia nella lista
        pending_shifts = [s for s in engine._proposed_shifts if s["status"] == "pending"]
        assert len(pending_shifts) >= 1
    
    @pytest.mark.asyncio
    async def test_propose_shift_rejected_by_constitution(self, engine):
        """Shift che viola la costituzione ritorna {}."""
        reason = "Test shift invalido"
        target_param = "supportive_intensity"
        delta = 2.0  # Fuori dai limiti costituzionali
        
        proposal = await engine.propose_micro_shift(reason, target_param, delta)
        
        assert proposal == {}
        
        # Verifica che sia nella lista dei rifiutati
        assert len(engine._rejected_shifts) >= 1
        rejected = engine._rejected_shifts[-1]
        assert rejected["target_param"] == target_param
        assert rejected["delta"] == delta
    
    @pytest.mark.asyncio
    async def test_governance_summary_structure(self, engine):
        """get_governance_summary() ha tutte le chiavi attese."""
        # Aggiungi qualche dato di test
        await engine.analyze_epistemic_quality("test", "test response")
        await engine.analyze_banality("test", "test response")
        
        summary = engine.get_governance_summary()
        
        expected_keys = [
            "avg_epistemic_quality",
            "avg_banality", 
            "last_drift",
            "pending_shifts",
            "approved_shifts",
            "rejected_shifts"
        ]
        
        for key in expected_keys:
            assert key in summary
        
        # Verifica tipi
        assert isinstance(summary["avg_epistemic_quality"], float)
        assert isinstance(summary["avg_banality"], float)
        assert isinstance(summary["pending_shifts"], int)
        assert isinstance(summary["approved_shifts"], int)
        assert isinstance(summary["rejected_shifts"], int)


class TestIntegration:
    """Test di integrazione tra Costituzione e Meta-Governance."""
    
    @pytest.mark.asyncio
    async def test_constitution_integration(self):
        """Verifica integrazione costituzione nel meta-governance."""
        engine = MetaGovernanceEngine()
        
        # Proposta valida
        valid_proposal = await engine.propose_micro_shift(
            "Test valid", "supportive_intensity", 0.1
        )
        assert len(valid_proposal) > 0
        
        # Proposta invalida
        invalid_proposal = await engine.propose_micro_shift(
            "Test invalid", "supportive_intensity", 2.0
        )
        assert invalid_proposal == {}
