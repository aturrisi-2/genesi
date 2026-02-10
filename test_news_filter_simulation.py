#!/usr/bin/env python3
"""
TEST FILTRO NEWS LOCALITÀ - Simulazione senza API key
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_news_filter_simulation():
    """Test simulazione del filtro news per località"""
    print("TEST FILTRO NEWS LOCALITÀ - SIMULAZIONE")
    print("=" * 50)
    
    try:
        from core.engines import APIToolsEngine
        
        engine = APIToolsEngine()
        
        # Simula articoli API con contenuti misti
        mock_articles = [
            {
                "title": "Roma: nuovo piano traffico in centro",
                "description": "Il Comune di Roma approva nuove misure per la circolazione."
            },
            {
                "title": "Oroscopo della settimana",
                "description": "Previsioni astrologiche per tutti i segni zodiacali."
            },
            {
                "title": "Metalmeccanici in sciopero nazionale",
                "description": "Protesta dei sindacati contro le nuove normative."
            },
            {
                "title": "Lazio: emergenza siccità",
                "description": "La regione Lazio dichiara stato di emergenza per la siccità."
            },
            {
                "title": "Milano: nuova linea metropolitana",
                "description": "Apertura della nuova linea M4 a Milano."
            }
        ]
        
        print(f"Articoli totali: {len(mock_articles)}")
        
        # Test filtro per Roma
        print("\nTest filtro per Roma:")
        roma_filtered = engine._filter_news_by_location(mock_articles, "Roma")
        print(f"Articoli filtrati per Roma: {len(roma_filtered)}")
        for article in roma_filtered:
            print(f"  - {article['title']}")
        
        # Test filtro per Milano
        print("\nTest filtro per Milano:")
        milano_filtered = engine._filter_news_by_location(mock_articles, "Milano")
        print(f"Articoli filtrati per Milano: {len(milano_filtered)}")
        for article in milano_filtered:
            print(f"  - {article['title']}")
        
        # Test estrazione località
        print("\nTest estrazione località:")
        test_messages = [
            "dimmi le notizie su roma",
            "dimmi le notizie su milano",
            "dimmi le notizie di oggi"
        ]
        
        for msg in test_messages:
            location = engine._extract_location_from_message(msg)
            print(f"  '{msg}' -> '{location}'")
        
        # Verifiche
        roma_correct = len(roma_filtered) == 2 and all("roma" in a["title"].lower() or "lazio" in a["title"].lower() for a in roma_filtered)
        milano_correct = len(milano_filtered) == 1 and "milano" in milano_filtered[0]["title"].lower()
        extraction_correct = engine._extract_location_from_message("dimmi le notizie su roma") == "Roma"
        
        print(f"\nVerifiche:")
        print(f"  Filtro Roma: {roma_correct}")
        print(f"  Filtro Milano: {milano_correct}")
        print(f"  Estrazione località: {extraction_correct}")
        
        if roma_correct and milano_correct and extraction_correct:
            print("\nSUCCESSO: Filtro news per località funzionante!")
            return True
        else:
            print("\nFALLITO: Filtro non funzionante correttamente")
            return False
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_news_filter_simulation())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
