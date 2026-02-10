# QUARANTENA FILE COMPLESSI

Questi file sono stati messi in quarantena perché sono troppo complessi per Genesi Core v2.

## 📁 FILE IN QUARANTENA

### 🔥 **DA RISCRIVERE COMPLETAMENTE**
- `core/surgical_pipeline.py` - Pipeline troppo complessa con troppi livelli
- `core/engines.py` - Sistema engine con fallback multipli
- `core/intent_engine.py` - Classificazione troppo complessa
- `core/proactor.py` - Orchestrazione che viola 1 intent → 1 funzione
- `api/chat.py` - Endpoint con troppa logica integrata
- `main.py` - Entry point con troppe dipendenze

### 🔧 **DA SEMPLIFICARE DRASTICAMENTE**
- `api/upload.py` - Upload con routing complesso
- `api/stt.py` - STT con logica non necessaria
- `auth/` - Sistema autenticazione - da verificare se necessario per v2
- `storage/` - Sistema storage - da rivedere per v2
- `memory/` - Sistema memoria - troppo complesso per v2
- `tts/` - Sistema TTS - da isolare e semplificare

## 🎯 **PRINCIPIO VIOLATO**
Tutti questi file violano il principio: **1 intent → 1 funzione**

## 📋 **STATO ATTUALE**
Solo i file essenziali rimangono attivi:
- `core/local_llm.py` - Interfaccia modello
- `core/log.py` - Logging
- `core/state.py` - Stato base
- `core/user.py` - Utente base
- `api/user.py` - Bootstrap utente
- `config/` - Configurazioni
- `static/` - Frontend
- `requirements.txt` - Dipendenze

## 🚀 **PROSSIMI PASSI**
1. Riscrivere da zero i file critici
2. Implementare architettura 1 intent → 1 funzione
3. Mantenere solo i file essenziali salvati
