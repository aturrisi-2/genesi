# WhatsApp Information Sources

Branch: `operational-memory-mvp`
Scope: gruppi WhatsApp di cantiere

## Obiettivo

Mappare le fonti informative che possono apparire in un gruppo WhatsApp di
cantiere e definire cosa si puo estrarre, quanto vale operativamente e quali
sono le criticita.

Il principio guida e semplice: nel cantiere il testo non basta. Molte decisioni,
prove, problemi e responsabilita emergono da immagini, screenshot e documenti.

## Fonti

| Fonte | Informazioni estraibili | Valore operativo | Criticita | Accuratezza attesa |
| --- | --- | --- | --- | --- |
| Messaggi testuali | decisioni, task, assegnazioni, domande, problemi, date | Alta: e la fonte piu diretta | Linguaggio informale, messaggi incompleti, riferimenti impliciti | Alta su frasi esplicite; media su impliciti |
| Immagini fotografiche | stato avanzamento, difetti visibili, materiali, aree, lavorazioni | Molto alta: prova visiva dello stato reale | Qualita foto, angolazione, assenza di contesto, privacy | Media senza testo; alta se accompagnata da descrizione |
| Immagini annotate | problemi evidenziati, misure, frecce, correzioni, aree interessate | Molto alta: spesso contengono intenzione operativa | Annotazioni piccole, testo scritto a mano, colori poco contrastati | Media-alta con OCR/vision ibrido |
| Screenshot | chat, email, ordini, pagine web, conferme, errori | Alta: spesso sono prove/documenti informali | Doppia compressione, testo piccolo, parti tagliate | Alta se testo leggibile |
| PDF | preventivi, DDT, ordini, verbali, schede tecniche, cronoprogrammi | Molto alta: documento formale | PDF immagine, pagine miste, firme/timbri, tabelle complesse | Alta su PDF testo; media su scansioni |
| DOCX | verbali, relazioni, specifiche, SAL, report | Alta | Versioni multiple, formattazione, commenti nascosti | Alta per testo; media per tabelle complesse |
| XLSX | computi, liste materiali, scadenze, avanzamento, costi | Molto alta | Formule, fogli multipli, celle unite, assenza di intestazioni | Alta se tabella regolare; media altrimenti |
| Foto di documenti | ordini, bolle, ricevute, appunti, verbali cartacei | Alta | Prospettiva, ombre, sfocatura, pieghe | Media con OCR; alta se foto buona |
| Foto di tabelle | computi, turni, misure, materiali, scadenze | Alta | Struttura tabellare difficile da ricostruire | Media |
| Cronoprogrammi fotografati | fasi, date, dipendenze, ritardi, milestone | Molto alta | Gantt piccoli, colori, linee e date difficili | Media-bassa se solo foto; media con immagini nitide |
| Report avanzamento | completato, da fare, criticita, percentuali | Molto alta | Formati non standard, allegati multipli | Alta se digitale; media se fotografato |
| Immagini tecniche | dettagli costruttivi, planimetrie, sezioni, impianti | Alta ma specialistica | Richiede dominio tecnico; rischio di interpretazione errata | Bassa-media senza legenda; media con testo/quote |
| Audio/vocali | decisioni, urgenze, incarichi | Fuori MVP iniziale | STT, rumore, consenso, privacy | Non stimata in MVP |

## Informazioni operative target

Ogni fonte deve contribuire, se possibile, a una o piu categorie operative:

- `Decision`: scelta presa, cambio di piano, approvazione, blocco deciso.
- `Task`: azione da fare, responsabile, scadenza, priorita.
- `Issue`: problema aperto, blocco, non conformita, rischio.
- `Information`: fatto rilevante, misura, consegna, documento ricevuto.
- `Question`: punto non chiarito, richiesta di conferma, dato mancante.

## Accuratezza attesa per fase MVP

Stima iniziale, da validare con dati reali:

| Tipo informazione | Accuratezza attesa |
| --- | --- |
| Task espliciti nel testo | 75-90% |
| Decisioni esplicite nel testo | 70-85% |
| Domande aperte nel testo | 80-90% |
| Informazioni da PDF testuale | 75-90% |
| Informazioni da screenshot leggibile | 65-85% |
| Informazioni da foto documento | 50-75% |
| Stato visivo da foto cantiere | 40-65% |
| Cronoprogrammi fotografati | 35-60% |

## Quali informazioni NON possono essere ricostruite in modo affidabile

- Decisioni prese a voce e mai scritte.
- Responsabili impliciti non nominati.
- Contesto tecnico non visibile nella foto.
- Misure non leggibili o parzialmente tagliate.
- Date dedotte da riferimenti vaghi come "domani" senza timestamp affidabile.
- Stato reale di una lavorazione se l'immagine mostra solo un dettaglio.
- Causa di un problema se e visibile solo l'effetto.
- Priorita se non esplicitata.
- Approvazioni se espresse con emoji o risposte ambigue.
- Informazioni cancellate, modificate o non esportate da WhatsApp.

## Implicazione architetturale

Ogni informazione estratta deve mantenere:

- fonte originale
- tipo fonte
- confidenza
- timestamp messaggio
- evidenza testuale o visiva
- eventuale file/documento collegato

Senza evidenza, l'informazione non deve diventare stato operativo affidabile.
