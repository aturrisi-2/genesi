"""
TTS Provider Tests - Genesi Cognitive System
Test pytest per il layer di astrazione TTS multi-provider
"""

import pytest
import json
import tempfile
import os
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Import dei moduli da testare
from core.tts_provider import (
    TTSProvider, PiperTTSProvider, EdgeTTSProvider, OpenAITTSProvider,
    get_tts_provider, synthesize_with_fallback, get_tts_provider_for_intent
)


class TestTTSConfig:
    """Test per la configurazione TTS."""
    
    def test_config_loads(self):
        """Verifica che tts_config.json sia leggibile."""
        config_path = Path("config/tts_config.json")
        assert config_path.exists(), "config/tts_config.json deve esistere"
        
        with open(config_path, 'r', encoding='utf-8-sig') as f:  # Use utf-8-sig to handle BOM
            config = json.load(f)
        
        assert "active_provider" in config, "config deve avere active_provider"
        assert "providers" in config, "config deve avere providers"
        assert config["active_provider"] in ["piper", "edge_tts", "openai"], "active_provider deve essere valido"


class TestPiperTTSProvider:
    """Test per PiperTTSProvider."""
    
    def test_piper_provider_instantiates(self):
        """Verifica che PiperTTSProvider() si crei senza eccezioni."""
        provider = PiperTTSProvider()
        assert provider.name() == "piper"
        assert provider.binary == "/opt/piper/piper/piper"
        assert provider.model.endswith(".onnx")
    
    @pytest.mark.asyncio
    async def test_piper_empty_text_returns_none(self):
        """Test che testo vuoto ritorni None."""
        provider = PiperTTSProvider()
        result = await provider.synthesize("")
        assert result is None
        
        result = await provider.synthesize("   ")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_piper_synthesize_with_mock(self):
        """Test sintesi Piper mockata."""
        provider = PiperTTSProvider()
        
        # Mock del subprocess
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"fake_pcm_data", b"")
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_proc):
            result = await provider.synthesize("test text")
            assert result is not None
            assert result.startswith(b'RIFF')  # WAV header


class TestEdgeTTSProvider:
    """Test per EdgeTTSProvider."""
    
    def test_edge_provider_instantiates(self):
        """Verifica che EdgeTTSProvider() si crei senza eccezioni."""
        provider = EdgeTTSProvider()
        assert provider.name() == "edge_tts"
        assert provider.voice == "it-IT-DiegoNeural"
        assert provider.rate == "+0%"
        assert provider.volume == "+0%"
    
    @pytest.mark.asyncio
    async def test_edge_empty_text_returns_none(self):
        """Test che testo vuoto ritorni None."""
        provider = EdgeTTSProvider()
        result = await provider.synthesize("")
        assert result is None
        
        result = await provider.synthesize("   ")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_edge_not_installed_fallback(self):
        """Test fallback quando edge_tts non è installato."""
        provider = EdgeTTSProvider()
        
        # Simula ImportError
        with patch.dict('sys.modules', {'edge_tts': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                result = await provider.synthesize("test text")
                assert result is None
    
    @pytest.mark.asyncio
    async def test_edge_timeout_fallback(self):
        """Test fallback su timeout."""
        provider = EdgeTTSProvider()
        
        # Mock edge_tts con timeout
        mock_communicate = AsyncMock()
        mock_communicate.stream.side_effect = asyncio.TimeoutError()
        
        with patch('edge_tts.Communicate', return_value=mock_communicate):
            result = await provider.synthesize("test text")
            assert result is None


class TestTTSProviderFactory:
    """Test per la factory function get_tts_provider()."""
    
    def test_factory_returns_piper_provider(self):
        """Test che factory ritorni PiperTTSProvider con config piper."""
        # Crea config temporanea
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "active_provider": "piper",
                "providers": {
                    "piper": {"enabled": True, "model": "it_IT-paola-medium", "speed": 1.0},
                    "edge_tts": {"enabled": True, "voice": "it-IT-DiegoNeural", "rate": "+0%", "volume": "+0%"}
                }
            }, f)
            temp_config_path = f.name
        
        try:
            # Patch del path di config
            with patch('core.tts_provider.Path') as mock_path:
                mock_path.return_value = Path(temp_config_path)
                mock_path.return_value.stat.return_value.st_mtime = 123456789
                
                provider = get_tts_provider()
                assert isinstance(provider, PiperTTSProvider)
                assert provider.name() == "piper"
        finally:
            os.unlink(temp_config_path)
    
    def test_factory_returns_edge_provider(self):
        """Test che factory ritorni EdgeTTSProvider con config edge_tts."""
        # Crea config temporanea
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "active_provider": "edge_tts",
                "providers": {
                    "piper": {"enabled": True, "model": "it_IT-paola-medium", "speed": 1.0},
                    "edge_tts": {"enabled": True, "voice": "it-IT-DiegoNeural", "rate": "+0%", "volume": "+0%"}
                }
            }, f)
            temp_config_path = f.name
        
        try:
            # Patch del path di config
            with patch('core.tts_provider.Path') as mock_path:
                mock_path.return_value = Path(temp_config_path)
                mock_path.return_value.stat.return_value.st_mtime = 123456789
                
                provider = get_tts_provider()
                assert isinstance(provider, EdgeTTSProvider)
                assert provider.name() == "edge_tts"
        finally:
            os.unlink(temp_config_path)
    
    def test_factory_unknown_provider_falls_back_to_piper(self):
        """Test che provider sconosciuto faccia fallback a Piper."""
        # Crea config temporanea
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "active_provider": "unknown_provider",
                "providers": {
                    "piper": {"enabled": True, "model": "it_IT-paola-medium", "speed": 1.0},
                    "edge_tts": {"enabled": True, "voice": "it-IT-DiegoNeural", "rate": "+0%", "volume": "+0%"}
                }
            }, f)
            temp_config_path = f.name
        
        try:
            # Patch del path di config
            with patch('core.tts_provider.Path') as mock_path:
                mock_path.return_value = Path(temp_config_path)
                mock_path.return_value.stat.return_value.st_mtime = 123456789
                
                provider = get_tts_provider()
                assert isinstance(provider, PiperTTSProvider)
                assert provider.name() == "piper"
        finally:
            os.unlink(temp_config_path)
    
    def test_factory_missing_config_falls_back_to_piper(self):
        """Test che config mancante faccia fallback a Piper."""
        with patch('core.tts_provider.Path') as mock_path:
            mock_path.return_value = Path("/nonexistent/config.json")
            mock_path.return_value.stat.side_effect = FileNotFoundError()
            
            provider = get_tts_provider()
            assert isinstance(provider, PiperTTSProvider)
            assert provider.name() == "piper"


class TestSwitchScript:
    """Test per lo script switch_tts.py."""
    
    def test_switch_script_changes_config(self):
        """Test che lo script switch modifichi correttamente il JSON."""
        import subprocess
        import sys
        
        # Crea config temporanea
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "active_provider": "piper",
                "providers": {
                    "piper": {"enabled": True, "model": "it_IT-paola-medium", "speed": 1.0},
                    "edge_tts": {"enabled": True, "voice": "it-IT-DiegoNeural", "rate": "+0%", "volume": "+0%"}
                }
            }, f)
            temp_config_path = f.name
        
        try:
            # Esegui script switch
            script_path = Path(__file__).parent.parent / "scripts" / "switch_tts.py"
            result = subprocess.run([
                sys.executable, str(script_path), "edge_tts"
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
            
            assert result.returncode == 0, f"Script fallito: {result.stderr}"
            
            # Verifica che la config sia cambiata
            with open(temp_config_path, 'r') as f:
                config = json.load(f)
            
            assert config["active_provider"] == "edge_tts"
            
        finally:
            os.unlink(temp_config_path)


class TestSynthesizeWithFallback:
    """Test per la funzione synthesize_with_fallback."""
    
    @pytest.mark.asyncio
    async def test_synthesize_with_fallback_success(self):
        """Test fallback quando provider primario fallisce."""
        # Mock provider primario che fallisce
        mock_primary = AsyncMock()
        mock_primary.name.return_value = "edge_tts"
        mock_primary.synthesize.return_value = None
        
        # Mock fallback provider che funziona
        mock_fallback = AsyncMock()
        mock_fallback.synthesize.return_value = b"fake_audio_data"
        
        with patch('core.tts_provider.get_tts_provider', return_value=mock_primary):
            with patch('core.tts_provider.PiperTTSProvider', return_value=mock_fallback):
                result = await synthesize_with_fallback("test text")
                
                assert result == b"fake_audio_data"
                mock_primary.synthesize.assert_called_once_with("test text")
                mock_fallback.synthesize.assert_called_once_with("test text")
    
    @pytest.mark.asyncio
    async def test_synthesize_with_fallback_both_fail(self):
        """Test eccezione quando entrambi i provider falliscono."""
        # Mock provider primario che fallisce
        mock_primary = AsyncMock()
        mock_primary.name.return_value = "edge_tts"
        mock_primary.synthesize.return_value = None
        
        # Mock fallback provider che fallisce
        mock_fallback = AsyncMock()
        mock_fallback.synthesize.return_value = None
        
        with patch('core.tts_provider.get_tts_provider', return_value=mock_primary):
            with patch('core.tts_provider.PiperTTSProvider', return_value=mock_fallback):
                with pytest.raises(RuntimeError, match="Both primary and fallback TTS providers failed"):
                    await synthesize_with_fallback("test text")


class TestTTSRouting:
    """Test per il routing automatico TTS basato su intent."""
    
    def test_routing_conversational_returns_openai(self):
        """Test che intent conversazionale ritorni OpenAI provider."""
        provider = get_tts_provider_for_intent(intent="greeting")
        assert provider.name() == "openai"
    
    def test_routing_informational_returns_edge(self):
        """Test che intent informativo ritorni Edge provider."""
        provider = get_tts_provider_for_intent(intent="weather")
        assert provider.name() == "edge_tts"
    
    def test_routing_unknown_intent_defaults_conversational(self):
        """Test che intent sconosciuto default a conversazionale (OpenAI)."""
        provider = get_tts_provider_for_intent(intent="sconosciuto_xyz")
        assert provider.name() == "openai"
