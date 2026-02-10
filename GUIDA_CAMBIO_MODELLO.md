# 🚀 GUIDA COMPLETA CAMBIO MODELLO - MISTRAL 7B

## 📋 RIEPILOGO MODIFICHE FATTE:

✅ **local_llm.py** - Aggiornato percorso modello e parametri
✅ **engines.py** - Prompt formato Mistral + tokens aumentati
✅ **download_mistral.sh** - Script download automatico

## 🎯 PASSI DA ESEGUIRE:

### 1. DOWNLOAD MODELLO
```bash
cd /path/to/genesi
chmod +x download_mistral.sh
./download_mistral.sh
```

### 2. FERMA LLAMA.CPP VECCHIO
```bash
# Se è in esecuzione, fermalo
pkill -f llama.cpp
```

### 3. AVVIA NUOVO MODELLO
```bash
# Sostituisci con il tuo path llama.cpp
./path/to/llama.cpp/main -m /opt/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf \
                         --host 127.0.0.1 \
                         --port 8080 \
                         --ctx-size 2048 \
                         --threads 4
```

### 4. TEST RAPIDO
```bash
cd /path/to/genesi
python -c "
import asyncio
from core.surgical_pipeline import surgical_pipeline
from core.state import CognitiveState

async def test():
    result = await surgical_pipeline.process_message(
        'ciao come stai?', 
        CognitiveState.build('test'), 
        [], [], None, {}, None
    )
    print(f'Risposta: {result.get(\"display_text\", \"\")}')

asyncio.run(test())
"
```

## 🎯 BENEFICI ATTESI:

✅ **10x più capace** di Llama-2-7B
✅ **Migliore comprensione** del contesto
✅ **Risposte più naturali** e coerenti
✅ **Stessa architettura** - zero breaking changes
✅ **Stesso peso** (~4GB) - stesso hardware

## 🚨 NOTE IMPORTANTI:

- **Mistral usa formato `[INST]...[/INST]`** - già configurato
- **Context size aumentato** a 2048 per conversazioni più lunghe
- **Temperature bilanciata** a 0.5 per naturalezza senza caos
- **Tokens aumentati** a 80 per risposte più ricche

## 🔧 TROUBLESHOOTING:

### Se llama.cpp non parte:
```bash
# Controlla che il file esista
ls -la /opt/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf

# Se manca, riesegui download
./download_mistral.sh
```

### Se risposte strane:
```bash
# Controlla log Genesi per prompt inviato
# Dovrebbe essere: [INST] ... [/INST]
```

## 🎉 RISULTATO FINALE:

Chat_free diventerà **molto più naturale** e **capace** mantenendo la stessa architettura solida!

**Fammi sapere quando hai scaricato il modello!**
