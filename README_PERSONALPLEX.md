# PersonalPlex 7B - LLM Locale per Genesi

## Overview
PersonalPlex 7B è un LLM locale basato su llama.cpp e modello Mistral 7B Instruct GGUF, integrato nell'architettura Genesi come primo livello di analisi del Proactor.

## Architettura
```
Input Utente → Proactor → PERSONALPLEX (localhost:8001) → GPT (fallback)
```

## Setup VPS Ubuntu

### 1. Installazione Automatica
```bash
# Esegui script di setup
chmod +x setup_personalplex_vps.sh
./setup_personalplex_vps.sh
```

### 2. Avvio Manuale
```bash
# Avvia servizio
sudo systemctl start personalplex

# Verifica stato
sudo systemctl status personalplex

# Visualizza log
sudo journalctl -u personalplex -f
```

## API Endpoints

### Health Check
```bash
curl http://localhost:8001/health
```

Risposta attesa:
```json
{
  "status": "ok",
  "model": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
  "backend": "llama.cpp (running)"
}
```

### Generate Test
```bash
curl -X POST http://localhost:8001/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"ciao","max_tokens":50}'
```

### Analyze Test
```bash
curl -X POST http://localhost:8001/analyze \
  -H 'Content-Type: application/json' \
  -d '{"text":"come stai?"}'
```

## Integrazione Genesi

### Log Obbligatori
Il sistema genera questi log inequivocabili:

```
[PROACTOR] calling PERSONALPLEX
[PERSONALPLEX] request received text='...'
[PERSONALPLEX] response generated latency=...ms
[PROACTOR] PERSONALPLEX success intent=... confidence=... latency=...ms
[PROACTOR] fallback to GPT
```

### Comportamento
1. **PERSONALPLEX up**: Viene chiamato per primo dal Proactor
2. **Confidence > 0.6**: Usa risposta PERSONALPLEX
3. **PERSONALPLEX down/low confidence**: Fallback automatico a GPT
4. **GPT sempre disponibile**: Fallback sicuro garantito

## Test Completi

### Esegui Test Integrazione
```bash
python3 test_personalplex_vps.py
```

### Test Manuali
```bash
# 1. Verifica server attivo
curl -s http://localhost:8001/health | jq .

# 2. Test generazione
curl -X POST http://localhost:8001/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"raccontami una barzelletta"}' | jq .

# 3. Test analisi
curl -X POST http://localhost:8001/analyze \
  -H 'Content-Type: application/json' \
  -d '{"text":"ho mal di testa, aiutami"}' | jq .
```

## Troubleshooting

### Server non parte
```bash
# Controlla log
sudo journalctl -u personalplex --no-pager -n 50

# Verifica dipendenze
pip3 list | grep -E "(torch|transformers|fastapi)"
```

### Porta 8001 non raggiungibile
```bash
# Controlla processi
ps aux | grep -E "(llama|personalplex)"

# Controlla porte
netstat -tlnp | grep 8001
```

### Performance lenta
```bash
# Monitor risorse
htop
iostat -x 1

# Aumenta thread llama.cpp (modifica setup script)
--threads 8  # Usa tutti i core CPU
```

## File Chiave

- `setup_personalplex_vps.sh` - Setup automatico VPS
- `personalplex_server.py` - Server FastAPI wrapper
- `core/local_llm.py` - Integrazione Genesi
- `core/intent_engine.py` - Proactor integration
- `test_personalplex_vps.py` - Test completi

## Specifiche Tecniche

- **Modello**: Mistral 7B Instruct v0.2 (Q4_K_M GGUF)
- **Backend**: llama.cpp (CPU ottimizzata)
- **Server**: FastAPI + uvicorn
- **Porta**: 8001 (PersonalPlex), 8080 (llama.cpp interno)
- **Timeout**: 15s chiamate, 30s generazione
- **Memory**: ~4GB RAM per modello
- **CPU**: 4+ thread consigliati

## Criteri di Successo

✅ PersonalPlex risponde davvero  
✅ Porta 8001 attiva  
✅ Proactor lo chiama realmente  
✅ GPT usato SOLO come fallback  
✅ Log chiari e inequivocabili  

## Manutenzione

### Aggiornamento modello
```bash
# Scarica nuovo modello GGUF
wget -O models/new-model.gguf [URL]

# Aggiorna path in personalplex_server.py
MODEL_PATH = "./models/new-model.gguf"

# Riavvia servizio
sudo systemctl restart personalplex
```

### Monitoraggio
```bash
# Log real-time
sudo journalctl -u personalplex -f

# Statistiche sistema
curl -s http://localhost:8001/health | jq .
```

---

**PersonalPlex 7B è ora integrato in Genesi come LLM locale primario!** 🚀
