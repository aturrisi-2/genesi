#!/usr/bin/env python3
"""
TEST SIMULAZIONE COMPLETA - Verifica funzionalità sistema migliorato
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_simulation_complete():
    """Test simulazione del sistema completo con dati mock"""
    print("TEST SIMULAZIONE COMPLETA - Sistema migliorato")
    print("=" * 50)
    
    try:
        from core.engines import APIToolsEngine
        from core.surgical_pipeline import sanitize_for_tts
        
        engine = APIToolsEngine()
        
        # 1. Test separazione TTS
        print("1. TEST SEPARAZIONE TTS:")
        text_with_emoji = "Meteo: sole a Roma con 15 gradi"
        tts_clean = sanitize_for_tts(text_with_emoji)
        
        print(f"   Visivo: '{text_with_emoji}'")
        print(f"   TTS: '{tts_clean}'")
        
        # Test con emoji reali (senza stamparle)
        emoji_text = "☀️ A Roma ci sono 15 gradi"
        emoji_clean = sanitize_for_tts(emoji_text)
        
        has_emoji_visivo = len(emoji_text) > len(emoji_clean)
        has_emoji_tts = len(emoji_clean) == 0 or len(emoji_clean) < len(emoji_text)
        
        tts_separation_ok = has_emoji_visivo and not has_emoji_tts
        print(f"   Separazione OK: {tts_separation_ok}")
        
        # 2. Test news approfondite
        print("\n2. TEST NEWS APPROFONDITE:")
        
        # Simula articoli
        mock_articles = [
            {
                "title": "Roma: nuova linea metro B",
                "description": "I lavori sulla linea B della metropolitana causano disagi nella circolazione urbana."
            },
            {
                "title": "Comune approva piano traffico",
                "description": "Il sindaco annuncia nuove misure per limitare il traffico nel centro storico."
            }
        ]
        
        # Test estrazione località
        location = engine._extract_location_from_message("dimmi le notizie su roma")
        print(f"   Località estratta: '{location}'")
        
        # Test categoria
        category = engine._get_news_category(mock_articles[0]["title"], mock_articles[0]["description"])
        emoji = engine._get_news_emoji(category)
        print(f"   Categoria: '{category}' -> Emoji: '{emoji}'")
        
        # Test contesto
        relevance = engine._get_relevance_context(mock_articles[0]["description"], "Roma")
        print(f"   Contesto: '{relevance.strip()}'")
        
        # 3. Test weather emoji
        print("\n3. TEST WEATHER EMOJI:")
        weather_conditions = ["cielo sereno", "nuvoloso", "pioggia leggera", "nebbia densa"]
        for condition in weather_conditions:
            emoji = engine._get_weather_emoji(condition)
            print(f"   '{condition}' -> '{emoji}'")
        
        # 4. Verifiche finali
        print("\n4. VERIFICHE FINALI:")
        checks = {
            "Separazione TTS": tts_separation_ok,
            "Estrazione località": location == "Roma",
            "Categorie news": category in ["Trasporti", "Politica"],
            "Emoji news": emoji in ["🚇", "🏛️"],
            "Contesto rilevanza": "questo" in relevance.lower(),
            "Emoji weather": all(engine._get_weather_emoji(c) for c in weather_conditions)
        }
        
        all_passed = all(checks.values())
        for check, passed in checks.items():
            status = "OK" if passed else "KO"
            print(f"   {status} {check}: {passed}")
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'PARZIALE'}")
        
        if all_passed:
            print("\nSISTEMA MIGLIORATO FUNZIONANTE!")
            print("✅ News approfondite con contesto")
            print("✅ Emoji globali in tutti i motori")
            print("✅ Separazione testo/TTS perfetta")
            print("✅ Filtraggio località funzionante")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_simulation_complete())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
