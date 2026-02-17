# Genesi Lab v1.1 - Sistema di Versioning Automatico

Modulo sperimentale completamente isolato per miglioramento globale automatico del sistema Genesi con versioning e rollback.

## 🧪 Struttura

```
lab/
├── __init__.py              # Funzione principale run_lab_cycle() con versioning
├── metrics_schema.py        # Dataclass per metriche conversazioni
├── supervisor.py           # Supervisore qualitativo euristico
├── simulator.py            # Simulatore conversazioni realistiche
├── adaptive_prompt.py      # Builder adattivo per prompt globali
├── prompt_versioning.py    # 🆕 Sistema di versioning e rollback
├── auto_runner.py          # 🆕 Esecuzione automatica e report
└── prompt_history/         # 🆕 History versioni prompt
```

## 🚀 Utilizzo

### Esecuzione ciclo completo con versioning
```python
from lab import run_lab_cycle

# Esegue ciclo con 50 conversazioni (default)
report = run_lab_cycle()

# Esegue ciclo con 100 conversazioni
report = run_lab_cycle(n_conversations=100)
```

### Esecuzione automatica giornaliera
```bash
python -m lab.auto_runner
```

Output:
```
📈 Overall Score: 0.672
📈 Variazione: +0.003
🔄 Versione: ✅ ACCETTATO
📁 Versioni totali: 2
🎯 Qualità: 👍 BUONA
```

### Test versioning
```python
from lab import run_versioning_test

# Test completo del sistema di versioning
results = run_versioning_test()
```

### Test rapido
```python
from lab import run_quick_test

# Test con 10 conversazioni per verifica
report = run_quick_test()
```

## 📊 Metriche Valutate

- **Clarity Score**: Chiarezza e specificità (0-1)
- **Coherence Score**: Coerenza logica (0-1)
- **Memory Score**: Uso corretto dati profilo (0-1)
- **Human Likeness**: Naturalità linguaggio (0-1)
- **Redundancy Score**: Basso livello ripetizioni (0-1)
- **Hallucination Risk**: Rischio invenzioni (0-1)
- **Overall Score**: Score complessivo ponderato (0-1)

## 🔄 Sistema di Versioning

### Logica di Accettazione
- **Tolleranza**: 2% (0.02)
- **Regola**: `new_score >= previous_score - 0.02`
- **Comportamento**: Accetta se sopra soglia, altrimenti rollback automatico

### Version History
- **Formato file**: `prompt_YYYYMMDD_HHMMSS.json`
- **Location**: `lab/prompt_history/`
- **Metadata**: timestamp, score, improvement areas

### Rollback Automatico
- **Trigger**: Score sotto soglia minima
- **Azione**: Ripristina versione precedente
- **Logging**: Completo con motivazione

## 🔄 Processo Completo

1. **Simulazione**: Genera conversazioni realistiche con 5 profili utente
2. **Valutazione**: Analizza euristica qualità senza LLM
3. **Ottimizzazione**: Costruisce prompt migliorato basato su metriche
4. **Confronto**: Compara score precedente con nuovo
5. **Decisione**: Accetta o esegue rollback basato su soglia
6. **Salvataggio**: Versiona prompt e genera report

## 📁 Output Files

- `lab/supervisor_logs.json` - Log append-only valutazioni
- `lab/global_prompt.json` - Prompt attuale migliorato
- `lab/prompt_history/` - 🆕 History versioni prompt
- `lab/lab_cycle_report_YYYYMMDD_HHMMSS.json` - Report completo

## 🛡️ Sicurezza

- **Zero side effects** sul sistema principale
- **Nessuna modifica** a file esistenti
- **Nessuna dipendenza** esterna nuova
- **Completamente isolato** in cartella `/lab/`
- **Solo funzioni chiamabili** manualmente
- **🆕 Rollback automatico** su degradazione performance

## 🎯 Profili Utente Simulati

1. **Curioso**: Domande dettagliate su tecnologia/scienza
2. **Distratto**: Messaggi brevi, cambia tema frequentemente  
3. **Emotivo**: Focus su emozioni e relazioni
4. **Tecnico**: Richieste precise su programmazione
5. **Provocatorio**: Domande sfidanti e critiche

## ⚡ Performance

- **50 conversazioni**: ~2-3 secondi
- **100 conversazioni**: ~5-7 secondi
- **Zero API calls**: completamente offline
- **Memory efficient**: < 10MB per ciclo completo
- **🆕 Versioning overhead**: < 100ms

## 🧪 Test Interni

### Test Versioning Completo
```python
from lab import run_versioning_test
run_versioning_test()
```

Verifica:
- ✅ Primo ciclo accettato
- ✅ Rollback su score inferiore
- ✅ Statistiche versioning
- ✅ History management

### Esecuzione come Script
```bash
# Report sintetico automatico
python -m lab.auto_runner
```

## 📈 Versioning Features

- **🆕 Versionamento automatico** con timestamp
- **🆕 Confronto punteggi** con tolleranza 2%
- **🆕 Rollback automatico** su degradazione
- **🆕 History persistente** con metadata
- **🆕 Statistiche versioning** complete
- **🆕 Test automatici** del sistema
