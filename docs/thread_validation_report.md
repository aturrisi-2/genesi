# Thread Validation Report

Data: 2026-06-18

Fase: FASE 3 - Thread / Discussion Engine

## Dataset usato

Fixture annotata:

- `tests/fixtures/thread_validation_sample.json`
- `tests/fixtures/thread_validation_expected.json`

Il dataset contiene eventi reali anonimizzati derivati dal flusso WhatsApp offline e casi mirati su:

- T7 / M2
- STF / STA / STM / T7
- ELS07 COPERTURA T2
- SS01 Mandata T7
- EWC05 montante L4
- UTA T7 / pressione canale
- Area break / portata
- BDF 200x100
- Pre riscaldo
- B02 porta 034 / porta 40
- L3 T7 SSLE SPECIALI
- media senza OCR
- eventi personali/logistici/sociali da escludere

## Numeri thread

- Eventi annotati: 40
- Thread attesi: 15
- Thread generati dal motore corrente: 18
- Precisione raggruppamento: 0.6562
- Recall raggruppamento: 0.6000
- Overmerge rate: 0.3438
- Fragmentation rate: 0.4000

## Numeri macro-thread

- Macro-thread attesi: 4
- Macro-thread generati: 4
- Thread collegati a macro-thread: 13
- Eventi operativi orfani: 5
- Macro precision: 0.3571
- Macro recall: 0.5556
- Macro overmerge rate: 0.6429
- Macro fragmentation rate: 0.4444
- Subthread preservation rate: 1.0000

Interpretazione:

Il livello macro-thread e' non distruttivo: conserva i thread operativi distinti e li collega tramite `macro_thread_id`, senza fonderli. Tuttavia la qualita' del raggruppamento macro e' ancora da calibrare: il motore usa tag comuni come `T7` con troppo peso e questo crea macro-thread troppo larghi.

## Report reale rigenerato

Report:

- `output/reports/tab-cefla-hq-enel-roma_macro_report.md`

Statistiche dal flusso reale offline:

- Eventi processati: 140
- Media rilevati: 64
- Media analizzati: 43
- Media con testo estratto: 0
- Thread operativi totali: 37
- Macro-thread operativi: 4
- Thread collegati a macro-thread: 23
- Thread senza macro-thread: 14
- Macro-thread aperti/waiting/in progress: 2
- Macro-thread risolti: 0
- Critical item dentro macro-thread: 12
- Open item dentro macro-thread: 9

## Casi problematici principali

### Overmerge thread

Il motore thread mantiene ancora un rischio di fusione parziale quando tag generici e vicinanza temporale si sommano.

Caso indicativo:

- `STF_T7_ALIMENTAZIONE`
- `SS01_MANDATA_T7`

Interpretazione:

`T7` e' un contesto utile, ma non basta per fondere automaticamente sottosistemi distinti. I codici piu' specifici (`SS01`, `STF`, `ELS07`, `EWC05`) devono pesare piu' dei tag generici.

### Overmerge macro

Casi rilevati:

- Macro `macro_476f855f971b` collega `L3_T7_SSLE_SPECIALI`, `SS01_MANDATA_T7`, `STF_T7_ALIMENTAZIONE`, `T7_M2_NON_PARTE_FOLLOWUP`, `UTA_T7_PRESSIONE_CANALE`.
- Macro `macro_b6e2db245fb5` collega `EWC05_MONTANTE_L4`, `EWC05_MONTANTE_L4_FOLLOWUP`, `T7_M2_NON_PARTE`.

Interpretazione:

Il macro-layer riduce la frammentazione percepita, ma in questa baseline tende a creare macro-temi troppo ampi quando trova sistemi generici condivisi o sequenze operative vicine.

### Frammentazione

Casi rilevati:

- `SS01_T7_MANDATA_RIPRESA` non collega ancora correttamente tutti i sottothread attesi, in particolare `BDF_200x100`.
- `UTA_T7_CANALE_PRESSIONE` resta separato da `PRE_RISCALDO`.
- Alcuni elementi brevi o logistico-operativi leggeri restano orfani.

Interpretazione:

Il sistema non deve tornare a fondere aggressivamente. La direzione corretta e' migliorare il macro-layer, non indebolire la separazione dei thread.

## Eventi operativi orfani

- `val_024`: Area break ora non balla piu' adesso
- `val_025`: BDF 200x100 da ordinare
- `val_026`: BDF 200x100 confermare misura
- `val_027`: Pre riscaldo da provare domani
- `val_028`: Pre riscaldo funziona

## Valutazione

Overmerge ridotto:

- A livello thread: resta misurabile ma controllato.
- A livello macro: non ancora. Il valore 0.6429 indica che la prima versione macro e' troppo permissiva.

Frammentazione mitigata:

- Parzialmente. 13 thread su 18 nel dataset e 23 thread su 37 nel report reale sono collegati a macro-thread.
- Rimangono orfani e macro-frammentazioni da analizzare prima di avanzare di fase.

Leggibilita' del report:

- Migliorata. La sezione `Macro-thread operativi` fornisce una vista superiore dei pacchetti di lavoro senza cancellare i sottothread.
- Non ancora affidabile come metrica decisionale autonoma, perche' alcune macro sono troppo larghe.

## Raccomandazioni

Raccomandazione principale: **restare in FASE 3 e calibrare il macro-thread engine**.

Azioni precise:

1. Mantenere il layer macro-thread, perche' preserva i sottothread (`subthread_preservation_rate = 1.0000`).
2. Ridurre il peso dei tag generici (`T7`, `UTA`) quando non sono accompagnati da almeno un codice specifico o un work package coerente.
3. Aumentare il peso di codici specifici e coppie contesto-componente, per esempio `SS01 + Mandata`, `EWC05 + montante`, `B02 + porta`.
4. Non fondere macro-thread tramite sola sequenza temporale.
5. Ripetere la validazione dopo la calibrazione e puntare prima a ridurre `macro_overmerge_rate` sotto 0.30.

## Decisione

Restare in FASE 3.

Il macro-layer e' stato introdotto come collegamento non distruttivo, ma non e' ancora abbastanza preciso da considerare chiusa la qualita' dei thread. La fase successiva non va avviata finche' la validazione non mostra macro-thread piu' affidabili e meno dipendenti da tag generici.
