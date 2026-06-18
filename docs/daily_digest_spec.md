# Daily Digest Spec

Branch: `operational-memory-mvp`

## Principio

Il Daily Digest non e il prodotto. E una vista generata dallo Stato Operativo
Persistente.

Non deve leggere direttamente la chat se non per evidenze. Deve usare lo stato.

## Formato

```text
AGGIORNAMENTO GIORNALIERO
Progetto: <nome>
Data: <data>

Decisioni prese oggi
- ...

Task aperti
- ...

Task completati
- ...

Problemi aperti
- ...

Nuovi rischi
- ...

Documenti ricevuti
- ...

Immagini rilevanti
- ...

Questioni aperte
- ...

Prossime azioni suggerite
- ...
```

## Sezioni

### Decisioni prese oggi

Derivano da `decisions` con `decided_at` nel giorno corrente.

Ogni decisione deve includere:

- testo
- fonte
- confidenza se bassa

### Task aperti

Derivano da `tasks_open`.

Ordinamento:

1. scadenza vicina
2. priorita
3. ultimo aggiornamento

### Task completati

Derivano da `tasks_completed` con `completed_at` nel giorno corrente.

### Problemi aperti

Derivano da `issues_open`.

Evidenziare:

- severita
- blocchi
- responsabile se noto

### Nuovi rischi

Derivano da `risks` creati o aggiornati oggi.

### Documenti ricevuti

Derivano da `documents`.

Includere:

- nome file
- tipo stimato
- informazioni estratte

### Immagini rilevanti

Derivano da `images` con linked item o confidenza sufficiente.

Non includere immagini senza valore operativo.

### Questioni aperte

Derivano da `open_questions`.

### Prossime azioni suggerite

Sono derivate, non autonome:

- task senza owner
- task senza scadenza
- issue senza responsabile
- domande aperte da piu di N giorni

## Regole di sicurezza prodotto

- Non inventare nuove azioni.
- Non assegnare responsabilita non presenti nello stato.
- Non trasformare suggerimenti in comandi.
- Mostrare fonte per elementi critici.

## Output MVP

Per la prima fase:

- generazione testo semplice
- export PDF successivo
- nessuna pubblicazione automatica su WhatsApp
- consultazione manuale dalla dashboard o endpoint
