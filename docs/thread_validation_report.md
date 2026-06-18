# Thread Validation Report

Data: 2026-06-18

Fase: FASE 3 - Thread / Discussion Engine

## Dataset usato

Fixture annotata:

- `tests/fixtures/thread_validation_sample.json`
- `tests/fixtures/thread_validation_expected.json`

Il dataset contiene eventi reali anonimizzati derivati dal flusso WhatsApp offline e casi mirati su:

- T7 / M2
- STF / T7
- ELS07 COPERTURA T2
- SS01 Mandata T7
- EWC05 montante L4
- UTA T7 / pressione canale
- Area break / portata
- BDF 200x100
- Pre riscaldo
- media senza OCR
- eventi personali/logistici/sociali da escludere

## Numeri

- Eventi annotati: 36
- Thread attesi: 12
- Thread generati dal motore corrente: 15
- Precisione raggruppamento: 0.6452
- Recall raggruppamento: 0.5882
- Overmerge rate: 0.3548
- Fragmentation rate: 0.4118
- Related past thread ids creati: 2

## Casi problematici principali

### Overmerge

Il caso principale di overmerge rilevato e':

- Thread generato `thread_8224131f857b`
- Label fuse:
  - `STF_T7_ALIMENTAZIONE`: `val_016`, `val_017`, `val_018`
  - `SS01_MANDATA_T7`: `val_021`, `val_033`

Interpretazione:

Il motore usa ancora `T7` come continuita' forte in alcuni casi, ma `SS01 Mandata T7` dovrebbe restare distinto da `STF T7 alimentazione`. Serve pesare meglio il codice piu' specifico rispetto al tag comune `T7`.

### Frammentazione

Casi principali:

- `UTA_T7_PRESSIONE_CANALE` spezzato in 3 thread generati.
- `PD_VERIFICA` spezzato in 3 thread generati.
- `EWC05_MONTANTE_L4` spezzato in 2 thread generati.
- `SS01_MANDATA_T7` spezzato in 2 thread generati e parzialmente fuso con STF.
- `AREA_BREAK_PORTATA` ha un evento mancante (`val_024`).
- `BDF_200x100` non apre thread operativo.
- `PRE_RISCALDO` non apre thread operativo.

Interpretazione:

Il motore e' diventato conservativo: riduce le fusioni ampie, ma perde continuita' su thread brevi, codici sintetici e macro-temi operativi leggeri.

## Eventi operativi orfani

- `val_024`: Area break ora non balla piu' adesso
- `val_025`: BDF 200x100 da ordinare
- `val_026`: BDF 200x100 confermare misura
- `val_027`: Pre riscaldo da provare domani
- `val_028`: Pre riscaldo funziona

## Raccomandazioni

Raccomandazione principale: **introdurre macro-thread/sottothread**.

Motivo:

- Ridurre solo frammentazione rischia di riaprire il problema delle fusioni aggressive.
- Ridurre solo overmerge renderebbe il sistema ancora piu' frammentato.
- I dati mostrano entrambi i problemi: overmerge su tag comuni (`T7`) e frammentazione su temi leggeri (`PD`, `UTA`, `BDF`, `Pre riscaldo`).

Prossima azione consigliata:

1. Tenere le regole attuali come baseline misurata.
2. Introdurre un livello `macro_thread` sopra i thread operativi.
3. Collegare thread distinti tramite `parent_thread_id` o `macro_thread_id` quando condividono area/sistema ma non abbastanza segnali per fondersi.
4. Aggiungere una soglia di specificita': tag generici come `T7` non devono dominare tag piu' specifici come `SS01`, `STF`, `ELS07`, `EWC05`.
5. Ripetere questa validazione dopo la modifica e confrontare precision/recall.

## Decisione

Restare in FASE 3.

La qualita' dei thread ora e' misurabile, ma non ancora ottimizzata. La fase successiva non va avviata finche' non viene introdotto e validato il concetto di macro-thread/sottothread o una strategia equivalente di collegamento non distruttivo tra discussioni correlate.
