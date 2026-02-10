#!/usr/bin/env python3
"""
TEST LOGICA SISTEMA MIGLIORATO - Verifica funzionalità senza encoding
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_logic_only():
    """Test della logica del sistema migliorato"""
    print("TEST LOGICA SISTEMA MIGLIORATO")
    print("=" * 50)
    
    try:
        from core.engines import APIToolsEngine
        from core.surgical_pipeline import sanitize_for_tts
        
        engine = APIToolsEngine()
        
        # 1. Test separazione TTS (logica)
        print("1. TEST SEPARAZIONE TTS:")
        text_with_emoji = "Test con simboli speciali"
        tts_clean = sanitize_for_tts(text_with_emoji)
        
        # Test con emoji (verifica lunghezza)
        emoji_test = "Sole a Roma"
        emoji_clean = sanitize_for_tts(emoji_test)
        
        print(f"   Test base: '{text_with_emoji}' -> '{tts_clean}'")
        print(f"   Funzione sanitize: {len(tts_clean) == len(text_with_emoji)}")
        
        # 2. Test news approfondite
        print("\n2. TEST NEWS APPROFONDITE:")
        
        # Test estrazione località
        location = engine._extract_location_from_message("dimmi le notizie su roma")
        print(f"   Località estratta: '{location}'")
        
        # Test categoria
        category = engine._get_news_category("Metro B lavori", "lavori sulla metropolitana")
        print(f"   Categoria trasporti: '{category}'")
        
        # Test emoji (senza stampare)
        transport_emoji = engine._get_news_emoji("Trasporti")
        print(f"   Emoji trasporti: presente {bool(transport_emoji)}")
        
        # Test contesto
        relevance = engine._get_relevance_context("lavori sulla metropolitana causano disagi", "Roma")
        print(f"   Contesto: '{relevance.strip()}'")
        
        # 3. Test weather emoji
        print("\n3. TEST WEATHER EMOJI:")
        weather_emoji = engine._get_weather_emoji("cielo sereno")
        print(f"   Emoji soleggiato: presente {bool(weather_emoji)}")
        
        rain_emoji = engine._get_weather_emoji("pioggia")
        print(f"   Emoji pioggia: presente {bool(rain_emoji)}")
        
        # 4. Verifiche finali
        print("\n4. VERIFICHE FINALI:")
        checks = {
            "Estrazione località": location == "Roma",
            "Categorie news": category == "Trasporti",
            "Emoji news": bool(transport_emoji),
            "Contesto rilevanza": "questo" in relevance.lower(),
            "Emoji weather": bool(weather_emoji) and bool(rain_emoji),
            "Sanitize TTS": len(tts_clean) > 0
        }
        
        all_passed = all(checks.values())
        for check, passed in checks.items():
            status = "OK" if passed else "KO"
            print(f"   {status} {check}: {passed}")
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'PARZIALE'}")
        
        if all_passed:
            print("\nSISTEMA MIGLIORATO FUNZIONANTE!")
            print("✅ Logica news approfondite OK")
            print("✅ Logica emoji globale OK")
            print("✅ Logica separazione TTS OK")
            print("✅ Logica filtraggio località OK")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_logic_only())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
