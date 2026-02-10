#!/usr/bin/env python3
"""
TEST FINALI FIX ARCHITETTURALI - Verifica completa
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_architectural_fixes():
    """Test completo dei fix architetturali"""
    print("TEST FINALI FIX ARCHITETTURALI")
    print("=" * 50)
    
    try:
        from core.engines import APIToolsEngine
        from core.surgical_pipeline import sanitize_for_tts
        
        engine = APIToolsEngine()
        
        # 1. Test filtro news locale severo
        print("1. TEST FILTRO NEWS LOCALE SEVERO:")
        
        # Simula articoli misti
        mock_articles = [
            {"title": "Roma: nuova linea metro B", "description": "Lavori sulla metropolitana"},
            {"title": "Oroscopo della settimana", "description": "Previsioni per tutti i segni"},
            {"title": "Serie A: Juventus vince", "description": "Partita di calcio nazionale"},
            {"title": "Comune di Roma approva piano", "description": "Decisione amministrativa locale"},
            {"title": "Borsa Italiana in calo", "description": "Andamento mercati finanziari"}
        ]
        
        filtered = engine._filter_news_by_location(mock_articles, "Roma")
        print(f"   Articoli originali: {len(mock_articles)}")
        print(f"   Articoli filtrati: {len(filtered)}")
        print(f"   Solo locali: {len(filtered) == 2}")
        
        # 2. Test formato news profondo
        print("\n2. TEST FORMATO NEWS PROFONDO:")
        
        # Simula articoli locali
        local_articles = [
            {"title": "Metro B: lavori programmati", "description": "Intervento di manutenzione sulla linea B"},
            {"title": "Campidoglio: nuova ordinanza", "description": "Misure per il traffico nel centro"}
        ]
        
        # Test estrazione località
        location = engine._extract_location_from_message("dimmi le notizie su roma")
        print(f"   Località estratta: '{location}'")
        
        # Test categoria
        category = engine._get_news_category(local_articles[0]["title"], local_articles[0]["description"])
        print(f"   Categoria: '{category}'")
        
        # Test contesto
        relevance = engine._get_relevance_context(local_articles[0]["description"], "Roma")
        print(f"   Contesto: '{relevance.strip()}'")
        
        # 3. Test fix meteo "su Roma"
        print("\n3. TEST FIX METEO 'SU ROMA':")
        
        location_test1 = engine._extract_location("dammi il meteo su roma")
        location_test2 = engine._extract_location("che tempo fa a roma")
        
        print(f"   'su roma' -> '{location_test1}'")
        print(f"   'a roma' -> '{location_test2}'")
        print(f"   Entrambe corrette: {location_test1 == 'Roma' and location_test2 == 'Roma'}")
        
        # 4. Test separazione TTS
        print("\n4. TEST SEPARAZIONE TTS:")
        
        # Test con emoji
        text_emoji = "🚇 Roma – Trasporti\n👉 Metro B: lavori\n📍 Questo potrebbe cambiare gli spostamenti"
        tts_clean = sanitize_for_tts(text_emoji)
        
        has_emoji_visivo = any(ord(c) > 127 for c in text_emoji)
        has_emoji_tts = any(ord(c) > 127 for c in tts_clean)
        
        print(f"   Testo con emoji: {len(text_emoji)} caratteri")
        print(f"   Testo TTS: {len(tts_clean)} caratteri")
        print(f"   Separazione OK: {has_emoji_visivo and not has_emoji_tts}")
        
        # 5. Verifiche finali
        print("\n5. VERIFICHE FINALI:")
        checks = {
            "Filtro locale severo": len(filtered) == 2,
            "Estrazione località news": location == "Roma",
            "Categorie news": category == "Trasporti",
            "Contesto rilevanza": "questo" in relevance.lower(),
            "Fix meteo su roma": location_test1 == "Roma",
            "Separazione TTS": has_emoji_visivo and not has_emoji_tts
        }
        
        all_passed = all(checks.values())
        for check, passed in checks.items():
            status = "OK" if passed else "KO"
            print(f"   {status} {check}: {passed}")
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'PARZIALE'}")
        
        if all_passed:
            print("\nFIX ARCHITETTURALI FUNZIONANTI!")
            print("✅ News veramente locali")
            print("✅ Formatto profondo Cosa/Percché")
            print("✅ Fix meteo 'su Roma'")
            print("✅ Separazione TTS perfetta")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_architectural_fixes())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
