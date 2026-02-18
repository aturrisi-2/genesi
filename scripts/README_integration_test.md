# Genesi Integration Test Suite

## Scopo
Script completo per testare end-to-end tutti i sistemi di Genesi via API HTTP reale.

## Prerequisiti
- Genesi in esecuzione su http://localhost:8000
- Python 3.8+ con aiohttp
- Utente di test creato (o script lo crea automaticamente)

## Installazione dipendenze
```bash
cd /opt/genesi
pip install -r scripts/integration_test_requirements.txt
```

## Creazione utente di test (se necessario)
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -d '{"email":"test_integration@genesi.local","password":"integration_test_2026"}'
```

## Esecuzione
```bash
cd /opt/genesi
python scripts/integration_test.py
```

## Cosa testa lo script

### GRUPPO 1 — Intent Classification
Verifica che ogni tipo di messaggio venga classificato correttamente:
- greeting, how_are_you, identity, weather, date, news, chat_free, emotional

### GRUPPO 2 — TTS Routing  
Verifica selezione provider corretto:
- openai per conversazioni
- edge_tts per tool

### GRUPPO 3 — Memory e Contesto
Verifica memoria conversazionale:
- Ricorda nome e lavoro dell'utente
- Mantiene contesto tra messaggi

### GRUPPO 4 — Profile Detection
Verifica estrazione profilo utente:
- Interessi, preferenze, dati personali

### GRUPPO 5 — Evolution Engine
Verifica controlli di stabilità:
- Throttling evolutivo
- Delta clamping
- Decisioni cognitive

### GRUPPO 6 — Latenza
Verifica performance:
- Chat semplice < 3000ms
- Chat con tool < 5000ms

### GRUPPO 7 — Fallback e Resilienza
Testa edge case:
- Messaggi vuoti
- Messaggi lunghissimi  
- Solo emoji
- Lingua straniera

### GRUPPO 8 — Context Continuity
Verifica continuità contesto:
- Messaggi corti interpretati correttamente
- Nessuna risposta "non ho capito" inappropriata

## Output
- Report completo in `/opt/genesi/reports/integration_test_report.md`
- Log in tempo reale durante esecuzione
- Statistiche finali di pass/fail

## Pulizia
Lo script pulisce automaticamente i dati dell'utente di test al termine.

## Troubleshooting
- Se l'autenticazione fallisce, creare prima l'utente di test
- Se i log non vengono letti, verificare che journalctl funzioni
- Se l'API non risponde, verificare che Genesi sia in esecuzione
