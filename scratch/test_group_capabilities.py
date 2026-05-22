import asyncio
import sys
import os

# Aggiungi la root directory al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.link_explorer import explore_links_in_text

async def main():
    print("=== TEST INIZIO: Link Explorer ===")
    
    # Test 1: Testo normale senza link
    text_no_links = "Ciao Genesi, come stai oggi?"
    res1 = await explore_links_in_text(text_no_links)
    print(f"Test 1 Risultato:\n{res1}\n")
    assert res1 == text_no_links, "Errore: il testo senza link non dovrebbe cambiare!"

    # Test 2: Testo con link reale (usiamo un URL pubblico stabile o un mock se offline)
    # Usiamo ad esempio 'https://httpbin.org/html' che restituisce un semplice HTML di test
    text_with_link = "Guarda questo link interessante: https://httpbin.org/html"
    print("Esploro il link (connessione di rete richiesta)...")
    res2 = await explore_links_in_text(text_with_link)
    print(f"Test 2 Risultato:\n{res2}\n")
    
    assert "https://httpbin.org/html" in res2, "Errore: l'URL originale deve rimanere nel testo!"
    assert "[Contenuto dei Link esplorati" in res2, "Errore: blocco dei link esplorati non trovato!"
    assert "Herman Melville" in res2 or "Moby Dick" in res2 or "Errore" in res2 or "non raggiungibile" in res2, "Errore nel contenuto del link!"

    # Test 3: Testo con link non raggiungibile/inesistente
    text_broken_link = "Ecco un link non funzionante: https://invalid-domain-genesi-12345.com/test"
    res3 = await explore_links_in_text(text_broken_link)
    print(f"Test 3 Risultato:\n{res3}\n")
    assert "invalid-domain" in res3, "L'URL originale deve rimanere!"
    assert "Errore:" in res3 or "non raggiungibile" in res3, "Dovrebbe rilevare un errore/non raggiungibilità!"

    print("=== TUTTI I TEST LOCALI SUPERATI CON SUCCESSO! ===")

if __name__ == "__main__":
    asyncio.run(main())
