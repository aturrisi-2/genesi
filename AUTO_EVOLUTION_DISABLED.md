# ⛔ AUTO-EVOLUTION SYSTEMS DISABLED

**Data:** 2026-04-28  
**Motivo:** Credit drain massivo su OpenRouter (~$2.52 consumati in 24 ore, 7.491 richieste API)  
**Stato:** ✅ TUTTI I SISTEMI DI AUTO-EVOLUZIONE DISABILITATI

---

## 🚨 Cosa è stato disabilitato

Sono stati disabilitati 4 sistemi che consumavano crediti automaticamente:

### 1. **AutoEvolutionEngine** (core/auto_evolution_engine.py)
- **Cosa faceva:** Watchdog che monitorava cartella `lab/` per file di report e li processava in parallelo
- **Problema:** Causava burst massivi di richieste LLM (53 richieste al secondo osservato)
- **Disabilitazione:** Flag `AUTO_EVOLUTION_DISABLED = True` (linea ~28)
- **Metodi bloccati:**
  - `start_monitoring()` - ritorna subito senza avviare watchdog
  - `start_auto_evolution()` - ritorna subito senza iniziare il monitoraggio

### 2. **LabFeedbackCycle** (core/lab_feedback_cycle.py)
- **Cosa faceva:** Leggeva fallback events, analizzava con LLM e generava regole per system prompt
- **Problema:** Looping automatico ogni 6 ore, potenzialmente scatenato da altri sistemi
- **Disabilitazione:** Flag `LAB_FEEDBACK_CYCLE_DISABLED = True` (linea ~29)
- **Metodi bloccati:**
  - `trigger_if_needed()` - ritorna subito senza avviare il ciclo

### 3. **Evolution Scheduler** (main.py)
- **Cosa faceva:** Eseguiva `supervisor.run()` ogni 12 ore per auto-evoluzione
- **Problema:** Poteva scatenare analisi LLM massive
- **Disabilitazione:** Task async completamente disabilitato (lines ~295-309)
- **Sostituzione:** Il task adesso ritorna immediatamente con warning

### 4. **Lab Cycle Scheduler** (main.py)
- **Cosa faceva:** Controllava ogni 6 ore se c'erano eventi pending e li processava
- **Problema:** Scatenava LabFeedbackCycle
- **Disabilitazione:** Task async completamente disabilitato (lines ~280-293)
- **Sostituzione:** Il task adesso ritorna immediatamente con warning

### 5. **GenesiAuditor** (core/genesi_auditor.py)
- **Cosa faceva:** Generava report analitici automaticamente
- **Problema:** Ogni report causava analisi LLM + iniezione nel lab_feedback_cycle
- **Disabilitazione:** Flag `GENESI_AUDITOR_DISABLED = True` (linea ~7)
- **Metodo bloccato:**
  - `generate_report()` - ritorna messaggio di disabilitazione

---

## 📊 Impatto del consumo osservato

Dal file CSV `openrouter_activity_2026-04-28 (1).csv`:

| Metrica | Valore |
|---------|---------|
| **Righe (richieste)** | 7.491 |
| **Costo totale** | ~$2.52 |
| **Picco massimo** | 53 richieste in 1 secondo (06:25:15) |
| **Modello usato** | gpt-4o-mini |
| **Orario di picco** | 06:25:15 - 06:25:20 |
| **Pattern** | Looping parallelo con 385-2898 token di prompt |

---

## 🔧 Come ri-abilitare (se necessario)

Per ri-abilitare i sistemi di auto-evoluzione:

### AutoEvolutionEngine
```python
# core/auto_evolution_engine.py (linea ~28)
AUTO_EVOLUTION_DISABLED = False  # ← Cambia da True a False
```

### LabFeedbackCycle
```python
# core/lab_feedback_cycle.py (linea ~29)
LAB_FEEDBACK_CYCLE_DISABLED = False  # ← Cambia da True a False
```

### Evolution & Lab Cycle Scheduler
```python
# main.py (lines ~295-309 e ~280-293)
# Restaura il codice originale commentato:
# async def evolution_scheduler():
#     supervisor = SupervisorEngine()
#     while True:
#         await asyncio.sleep(43200)  # 12 ore
#         try:
#             supervisor.run()
#         except Exception as e:
#             log("EVOLUTION_SCHEDULER_ERROR", error=str(e))
```

### GenesiAuditor
```python
# core/genesi_auditor.py (linea ~7)
GENESI_AUDITOR_DISABLED = False  # ← Cambia da True a False
```

---

## 📝 Note importanti

1. **Non perdere i dati:** I file di stato (current_state.json, ecc.) rimangono intatti
2. **Manuale ancora possibile:** Gli admin possono ancora triggerare manualmente:
   - `lab_feedback_cycle.run(force=True)` via API
   - `supervisor.run()` via script
3. **Le iniezioni di tipo admin:** Rimangono non bloccate (es. `record_observation()` da fallback_engine)
4. **Logs:** Tutti i sistemi loggano quando sono disabilitati, search per "DISABLED" nei log

---

## 🔍 Monitoraggio OpenRouter

Per verificare che i crediti non vengono più consumati:

1. Vai a https://openrouter.ai/account/usage
2. Verifica che non ci siano più picchi di 50+ richieste al secondo
3. Aspetta almeno 30 minuti per confermare

---

## 🎯 Prossimi passi suggeriti

1. **Investigare la root cause:** Cosa ha triggerato il burst di 7491 richieste?
2. **Implementare rate limiting:** Aggiungere limiti massimi di parallelismo
3. **Monitoraggio dei costi:** Aggiungere alert per consumi anomali
4. **Strategia di evoluzione:** Riprogettare il sistema di auto-evoluzione con limiti ristretti

---

**Status:** ✅ DISABILITATO E VERIFICATO
