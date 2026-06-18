# Daily Report

Branch: `operational-memory-mvp`

## Obiettivo

Generare un report giornaliero minimale a partire dallo Stato Operativo
Persistente.

Il report non legge direttamente WhatsApp. Usa lo stato gia estratto.

## Endpoint

```text
GET /operational-state/{project_id}/daily-report
```

## Output

Il primo output e JSON con anche una versione Markdown stampabile.

Sezioni:

- titolo
- data
- decisioni
- task aperti
- task completati
- problemi aperti
- informazioni rilevanti
- domande aperte
- prossime azioni suggerite

## Regole

- Non inventare azioni.
- Derivare tutto dallo stato.
- I task completati sono task con `status=completed`.
- Le prossime azioni sono suggerimenti cauti derivati da task senza owner, task
  senza scadenza, issue aperte e domande aperte.

## Esempio Markdown

```markdown
# Aggiornamento giornaliero - cantiere-demo

## Decisioni
- La posa del vano scala e' spostata a venerdi mattina

## Task aperti
- Verificare il materiale | owner: Luca | due: entro le 10

## Task completati
- Chiudere stuccatura pareti uffici | owner: Gianni | due: oggi
```
