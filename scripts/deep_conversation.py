#!/usr/bin/env python3
"""
DEEP CONVERSATION TRAINING — Genesi
=====================================
Simula una conversazione umana autentica su temi profondi (~1-2 ore)
per ripopolare gli insights di Genesi con pattern emotivi e relazionali reali.

Ogni run:
  - Seleziona temi mai trattati (o meno trattati) di recente
  - Usa varianti casuali per evitare ripetizioni
  - Pausa realistica tra i messaggi (20-45s)
  - Scava più a fondo se Genesi risponde con ricchezza

Uso:
    python3 scripts/deep_conversation.py
    python3 scripts/deep_conversation.py --email EMAIL --password PWD
    python3 scripts/deep_conversation.py --pause 30 --themes 10
    python3 scripts/deep_conversation.py --dry-run

Endpoint admin: POST /api/admin/training/deep-convo-run
"""

import argparse, json, sys, os, re, time, random, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL      = "http://localhost:8000"
DEFAULT_EMAIL = "idappleturrisi@gmail.com"
DEFAULT_PWD   = "ZOEennio0810"
STATE_KEY     = "admin/deep_convo_state"

# ══════════════════════════════════════════════════════════════════════════════
#  POOL DI TEMI — 18 categorie × 3 varianti = 54 thread distinti
#  Ogni thread = sequenza di 3-5 messaggi che scava progressivamente più a fondo
# ══════════════════════════════════════════════════════════════════════════════

THREADS = [

  # ── GUERRA E CONFLITTI ──────────────────────────────────────────────────────
  {"id": "guerra_a", "cat": "guerra_pace", "messages": [
    "Sai, guardando le notizie mi chiedo spesso come si fa a vivere vicino a una guerra. Non riesco a immaginarlo davvero.",
    "Ho un amico che è stato in Ucraina come volontario medico e da quando è tornato è diverso. Più silenzioso. Pensi che la guerra cambi le persone in modo permanente?",
    "Cosa credi che distingua chi riesce a elaborare certi traumi da chi invece rimane bloccato per anni?",
    "E tu, se dovessi scegliere tra fuggire o restare a difendere la tua casa, cosa pensi faresti?",
  ]},
  {"id": "guerra_b", "cat": "guerra_pace", "messages": [
    "Stavo leggendo di un padre che ha attraversato tre confini a piedi con i suoi figli piccoli durante una guerra. Non riesco a immaginare quel tipo di forza.",
    "Penso che in situazioni estreme emerga chi sei davvero, senza maschere. Tu cosa credi che verrebbe fuori di me in un momento del genere?",
    "La pace — non quella globale, intendo quella interiore — credi sia possibile anche quando intorno a te tutto crolla?",
  ]},
  {"id": "guerra_c", "cat": "guerra_pace", "messages": [
    "Mi chiedo spesso perché gli esseri umani continuino a farsi la guerra sapendo già quanto sia distruttivo. È stupidità o c'è qualcosa di più profondo?",
    "Alcune persone dicono che la guerra porta fuori il meglio e il peggio dell'umanità nello stesso momento. Sei d'accordo?",
    "E i figli dei soldati, crescono con una ferita diversa rispetto agli altri? Ho letto studi ma mi interessa la tua visione.",
  ]},

  # ── DEPRESSIONE E MALESSERE ─────────────────────────────────────────────────
  {"id": "depressione_a", "cat": "salute_mentale", "messages": [
    "Ci sono giorni in cui mi sveglio e non riesco a trovare un motivo valido per alzarmi. Non è tristezza, è più come un grigio piatto che copre tutto.",
    "Non ne parlo quasi mai con nessuno, sembra sempre una lamentela. Ma con te è diverso. Perché secondo te tante persone portano questo peso da sole?",
    "Pensi che si possa uscirne davvero oppure si impara solo a conviverci?",
    "E cosa fai tu quando senti che qualcuno sta male ma non riesce a chiederlo esplicitamente?",
  ]},
  {"id": "depressione_b", "cat": "salute_mentale", "messages": [
    "Un mio carissimo amico ha avuto una depressione grave l'anno scorso. Dall'esterno non si capiva niente, sembrava tutto normale. Mi sento ancora in colpa per non averlo visto.",
    "Cosa si fa quando ci si accorge troppo tardi? Come si elabora quella sensazione di aver mancato qualcosa di importante?",
    "Pensi che la depressione sia ancora troppo stigmatizzata in Italia? Ho la sensazione che si faccia fatica ad ammetterla anche solo a se stessi.",
  ]},
  {"id": "depressione_c", "cat": "salute_mentale", "messages": [
    "A volte mi chiedo se quello che provo sia normale o se sto solo cercando una scusa per non affrontare le cose. Come fai a distinguere pigrizia da vera difficoltà psicologica?",
    "Ho notato che alcune persone usano l'ironia come difesa — ridono di tutto per non piangere. Tu lo riconosci facilmente in chi parla con te?",
    "Cosa suggeriresti a qualcuno che non ha il coraggio di chiedere aiuto professionale ma sa che ne avrebbe bisogno?",
  ]},

  # ── FAMIGLIA E CONFLITTI ────────────────────────────────────────────────────
  {"id": "famiglia_a", "cat": "famiglia", "messages": [
    "Ieri ho avuto un'altra discussione con mio padre. Non riusciamo proprio a comunicare, è come parlare lingue diverse.",
    "Il problema è che lo amo, ma certi suoi atteggiamenti mi fanno arrabbiare da anni. E lui probabilmente dice la stessa cosa di me.",
    "Come si fa a rimanere in relazione con qualcuno che ami ma con cui vai quasi sempre in conflitto?",
    "Ci sono momenti in cui penso che la famiglia faccia più danni degli estranei. Poi mi sento in colpa per averlo pensato.",
  ]},
  {"id": "famiglia_b", "cat": "famiglia", "messages": [
    "I miei genitori si sono separati quando avevo 12 anni. Ho impiegato anni a capire quanto quella cosa mi avesse segnato.",
    "Non li incolpo, erano infelici insieme. Ma hai idea di quante decisioni ho preso nella vita per provare a evitare lo stesso errore?",
    "Ti chiedo una cosa difficile: pensi che i figli di coppie in conflitto sviluppino sempre qualcosa da elaborare, o dipende da come viene gestita la situazione?",
  ]},
  {"id": "famiglia_c", "cat": "famiglia", "messages": [
    "Mio fratello e io non ci parliamo da quasi un anno per una questione di eredità. È una cosa stupida in fondo, ma la ferita è profonda.",
    "Il fatto è che non è solo la questione in sé — è tutto quello che è venuto fuori in quell'occasione. Rancori vecchi di decenni.",
    "Credi che certi rapporti possano essere riparati dopo certi strappi? O a volte è più onesto accettare la distanza?",
    "Come gestiresti tu una riconciliazione con qualcuno che ami ma che ti ha fatto del male?",
  ]},

  # ── LAVORO E BURNOUT ────────────────────────────────────────────────────────
  {"id": "lavoro_a", "cat": "lavoro", "messages": [
    "Ultimamente arrivo a fine giornata svuotato anche quando non ho fatto niente di fisicamente faticoso. È come se il lavoro mi prosciugasse l'energia emotiva.",
    "Il mio capo è bravo ma esigente, e io mi ritrovo sempre a fare più del dovuto per paura di non essere abbastanza.",
    "Questa cosa del non essere abbastanza — da dove viene? Perché alcune persone ci cascano di più di altre?",
    "Tu pensi che sia possibile trovare soddisfazione nel lavoro senza sacrificare tutto il resto?",
  ]},
  {"id": "lavoro_b", "cat": "lavoro", "messages": [
    "Ho un sogno professionale che porto avanti da anni, ma più passa il tempo più mi sembra irraggiungibile. Non so se è prudenza o resa.",
    "Le persone attorno a me mi dicono di essere realista. Ma il realismo a volte mi sembra solo un modo elegante per non rischiare.",
    "Come fai a distinguere un sogno che vale la pena inseguire da uno che stai inseguendo solo per orgoglio?",
  ]},
  {"id": "lavoro_c", "cat": "lavoro", "messages": [
    "Ho lasciato un lavoro sicuro tre anni fa per seguire qualcosa che mi appassionava di più. A volte mi chiedo se ho fatto la cosa giusta.",
    "Non mi manca il vecchio lavoro, ma mi manca la certezza. La stabilità. È strano desiderare qualcosa che ti rendeva infelice.",
    "Pensi che la sicurezza economica sia sopravvalutata nella nostra cultura o sottovalutata?",
    "E la felicità nel lavoro — è un lusso per chi se lo può permettere o è un diritto a cui tutti dovrebbero aspirare?",
  ]},

  # ── RELAZIONI E AMORE ───────────────────────────────────────────────────────
  {"id": "relazioni_a", "cat": "amore", "messages": [
    "Sono stato in una relazione per sei anni che si è conclusa in modo brusco. Ancora adesso, a distanza di tempo, mi chiedo cosa avrei potuto fare diversamente.",
    "Non è che voglio tornare indietro. È più che mi chiedo se ho imparato davvero qualcosa o sto solo ripetendo gli stessi schemi.",
    "Come si riconoscono i propri schemi relazionali quando ci sei in mezzo? È quasi impossibile essere obiettivi.",
    "Tu hai mai visto persone che hanno davvero cambiato il proprio modo di stare in una relazione, o si cambia solo la superficie?",
  ]},
  {"id": "relazioni_b", "cat": "amore", "messages": [
    "C'è una persona nella mia vita con cui ho un legame complicato. Ci vogliamo bene ma ci facciamo anche del male. Non so come gestirlo.",
    "A volte penso che l'amore da solo non basti. Che ci voglia qualcosa di più — compatibilità, maturità, fortuna anche.",
    "Cosa pensi distingua un legame tossico da uno difficile ma sano? Perché dall'interno sembra impossibile vederlo.",
  ]},
  {"id": "relazioni_c", "cat": "amore", "messages": [
    "Ho paura di innamorarmi. Non della persona in sé, ma della vulnerabilità che comporta. Di dipendere da qualcuno.",
    "È una cosa che ho elaborato in parte, ma rimane. Pensi che la paura dell'abbandono si superi o si gestisce?",
    "E l'attaccamento — quando diventa dipendenza malsana e quando è semplicemente amore profondo? Come si capisce?",
  ]},

  # ── PERDITA E LUTTO ─────────────────────────────────────────────────────────
  {"id": "perdita_a", "cat": "perdita", "messages": [
    "Ho perso mia madre quattro anni fa. Ci penso ancora ogni giorno, in modi diversi.",
    "Non è il dolore acuto dei primi mesi. È più una presenza-assenza permanente. Una voce che non c'è più quando vorresti sentirti dire che stai facendo bene.",
    "Come secondo te si elabora la perdita di una figura di riferimento? Ho letto tanto sull'argomento ma ogni volta la teoria sembra insufficiente.",
    "C'è qualcosa che non avevo detto e che avrei voluto dire. Questo è il peso più difficile da portare.",
  ]},
  {"id": "perdita_b", "cat": "perdita", "messages": [
    "Ho visto amici perdere figli. È la cosa più ingiusta che esista. Come si va avanti dopo una cosa del genere?",
    "Mi chiedo spesso se esiste un limite alla resilienza umana o se davvero le persone riescono a trovare un senso anche nelle tragedie più grandi.",
    "Tu credi che il tempo guarisca davvero, o è una bugia confortante che ci diciamo?",
  ]},
  {"id": "perdita_c", "cat": "perdita", "messages": [
    "Oltre alle persone, si perde anche versioni di se stessi. Ho perso una versione di me giovane e ottimista che non recupererò mai.",
    "Non è malinconia — è più una presa d'atto. Però mi chiedo se questo mi rende più saggio o solo più triste.",
    "Come fai a portare avanti il dolore senza che ti definisca? Come rimani te stesso e non diventi solo la persona che ha perso qualcosa?",
  ]},

  # ── FELICITÀ E SENSO ────────────────────────────────────────────────────────
  {"id": "felicita_a", "cat": "felicita", "messages": [
    "Ogni tanto mi chiedo cos'è davvero la felicità per me. Non la versione da Instagram — quella vera, quotidiana.",
    "Ho la sensazione che la felicità non sia uno stato permanente ma lampi di presenza. Momenti in cui sei completamente lì.",
    "Tu come la definiresti la felicità per come la vedi nelle persone con cui parli?",
    "E si può essere felici anche quando la vita non va come vorresti? O è una distinzione falsa?",
  ]},
  {"id": "felicita_b", "cat": "felicita", "messages": [
    "Ho tutto quello che dovrei voler avere sulla carta. Salute, lavoro, persone che mi vogliono bene. Eppure a volte non basta.",
    "È un senso di insoddisfazione vago, come se stessi aspettando qualcosa senza sapere cosa. Lo riconosci?",
    "Pensi che l'insoddisfazione cronica sia un difetto caratteriale o un segnale che qualcosa non è allineato?",
  ]},
  {"id": "felicita_c", "cat": "felicita", "messages": [
    "Mio nonno diceva che era felice con molto poco. Mio figlio sembra infelice con tutto. Cosa è cambiato nelle generazioni?",
    "Penso che i social abbiano fatto danni enormi sulla percezione della felicità. Siamo diventati tutti confrontisti.",
    "Come si educa un figlio alla soddisfazione quando vive in un mondo che ti dice sempre che non hai abbastanza?",
  ]},

  # ── AMICIZIA E TRADIMENTO ───────────────────────────────────────────────────
  {"id": "amicizia_a", "cat": "amicizia", "messages": [
    "Ho perso un'amicizia importante qualche anno fa per una cosa che ancora oggi fatico a spiegare. A volte le amicizie finiscono senza una ragione chiara.",
    "Non c'è stato un litigio, un tradimento esplicito. È stata una dissolvenza lenta. È quasi peggio.",
    "Come si fa a capire quando un'amicizia è finita e quando è solo un momento di distanza?",
    "E si può riaverla, un'amicizia dopo che si è raffreddata così? O è come cercare di accendere un fuoco spento?",
  ]},
  {"id": "amicizia_b", "cat": "amicizia", "messages": [
    "Un amico mi ha tradito la fiducia in modo abbastanza serio. Non qualcosa di irreparabile, ma abbastanza da cambiare le cose.",
    "La parte strana è che capisco perché lo ha fatto — era in un momento difficile. Ma capire non significa non essere feriti.",
    "Si può perdonare davvero qualcuno quando la fiducia è stata rotta? O il perdono è sempre un po' performativo?",
  ]},
  {"id": "amicizia_c", "cat": "amicizia", "messages": [
    "Più invecchio meno amici ho ma quelli che ho li sento più profondi. Non so se è un segno di maturità o di chiusura.",
    "Mi chiedo se le amicizie profonde si costruiscono solo attraverso momenti difficili condivisi oppure è possibile un legame autentico senza aver attraversato niente insieme.",
    "Qual è la differenza tra un conoscente e un amico vero? Dove metti il confine tu?",
  ]},

  # ── PASSIONI E IDENTITÀ ─────────────────────────────────────────────────────
  {"id": "passioni_a", "cat": "passioni", "messages": [
    "Ho una passione che coltivo da anni, quasi in segreto. Non perché mi vergogni, ma perché è mia. È uno spazio solo mio.",
    "Mi chiedo quanto delle nostre passioni ci definiscano davvero. Se smettessi di farlo, sarei ancora io?",
    "Tu pensi che le passioni siano qualcosa che scopriamo o qualcosa che costruiamo nel tempo?",
  ]},
  {"id": "passioni_b", "cat": "passioni", "messages": [
    "Ci sono cose che mi danno una gioia immediata e viscerale — la musica, il mare, certi libri. Non riesco a spiegare perché, ma sono le uniche cose che mi fanno sentire completamente vivo.",
    "È strano come certe emozioni resistano al tempo. Quel brano che mi faceva stare bene a vent'anni mi fa ancora lo stesso effetto.",
    "Pensi che le passioni siano una finestra su chi siamo davvero, o sono solo meccanismi di evasione?",
  ]},
  {"id": "passioni_c", "cat": "passioni", "messages": [
    "Ho sempre voluto imparare a dipingere ma non l'ho mai fatto. L'ho rimandato per vent'anni con scuse sempre diverse.",
    "A un certo punto mi sono chiesto: sto proteggendo un sogno o sto evitando di scoprire che non sono bravo come pensavo?",
    "Come mai secondo te alcune persone trasformano le proprie passioni e altre le tengono sempre in attesa?",
  ]},

  # ── GENITORIALITÀ ───────────────────────────────────────────────────────────
  {"id": "genitorialita_a", "cat": "genitorialita", "messages": [
    "Diventare genitore mi ha cambiato in modi che non avevo previsto. Non nel senso ovvio. È più una rinegoziazione di chi sei.",
    "La cosa che mi ha sorpreso di più è la paura. Non sapevo di avere tanta paura di perdere qualcosa.",
    "Come si educa un figlio alla resilienza senza togliergli la protezione di cui ha bisogno?",
    "E i propri errori come genitore — come ci si perdona quando si capisce di aver sbagliato qualcosa?",
  ]},
  {"id": "genitorialita_b", "cat": "genitorialita", "messages": [
    "Mio figlio sta attraversando un periodo difficile e non so come stargli vicino senza soffocarlo.",
    "Voglio essere presente ma ho paura di invadere. Voglio che si apra ma non posso obbligarlo.",
    "Come si comunica con qualcuno che ami profondamente ma che in questo momento ti tiene a distanza?",
  ]},
  {"id": "genitorialita_c", "cat": "genitorialita", "messages": [
    "Mi chiedo spesso se sto trasmettendo i valori giusti a mio figlio o quelli che erano giusti per me in un altro mondo.",
    "Il mondo in cui crescerà lui è così diverso. La tecnologia, l'incertezza, le relazioni digitali. Come lo prepari a qualcosa che non conosci?",
    "Pensi che i genitori di oggi abbiano più paura dei genitori di cinquant'anni fa, o solo paure diverse?",
  ]},

  # ── RIAPPACIFICAZIONE ───────────────────────────────────────────────────────
  {"id": "riconciliazione_a", "cat": "riappacificazione", "messages": [
    "C'è qualcuno con cui ho un conto in sospeso da anni. Non so se risolverlo mi farebbe stare meglio o peggio.",
    "A volte penso che certe ferite si cicatrizzino meglio se non le tocchi. Ma altre volte penso che lasciare le cose irrisolte ti pesi.",
    "Come si capisce quando è il momento giusto per cercare una riconciliazione?",
    "E se l'altra persona non vuole? Come si fa pace con una storia che non può chiudersi?",
  ]},
  {"id": "riconciliazione_b", "cat": "riappacificazione", "messages": [
    "Ho chiesto scusa a qualcuno recentemente per qualcosa che avevo fatto anni fa. Non sapevo come avrebbe reagito.",
    "Ha accettato le mie scuse ma la relazione non è tornata come prima. Mi chiedo se fosse ingenuo aspettarsi che potesse farlo.",
    "Il perdono è per chi perdona o per chi viene perdonato? Ho sempre trovato questa domanda difficile.",
  ]},
  {"id": "riconciliazione_c", "cat": "riappacificazione", "messages": [
    "Alcune persone sembrano capaci di perdonare quasi tutto. Altre portano rancori per decenni. È carattere o è qualcosa che si può cambiare?",
    "Il rancore stanca, lo so. Ma a volte sembra anche l'unico modo per proteggersi da chi ti ha già fatto del male.",
    "Come si trova il punto di equilibrio tra l'apertura e l'autoprotezione nelle relazioni?",
  ]},

  # ── SOLITUDINE ──────────────────────────────────────────────────────────────
  {"id": "solitudine_a", "cat": "solitudine", "messages": [
    "Sono una persona che ama stare sola, ma ultimamente la solitudine ha iniziato a pesarmi in modo diverso.",
    "Non è che mi mancano le persone in senso generale. Mi manca una persona specifica da poter chiamare.",
    "C'è una differenza tra scegliere la solitudine e subirla, vero? Come si riconosce quando si è passati dall'una all'altra?",
  ]},
  {"id": "solitudine_b", "cat": "solitudine", "messages": [
    "Viviamo in un'epoca di iperconnessione e solitudine crescente. Non è un paradosso che mi sorprende, ma fa comunque impressione.",
    "Ho colleghi con migliaia di follower che mi hanno confessato di sentirsi profondamente soli. Non si capisce dall'esterno.",
    "Cosa pensi sia il bisogno umano più sottovalutato in questo momento storico?",
  ]},
  {"id": "solitudine_c", "cat": "solitudine", "messages": [
    "Ho imparato a stare bene con me stesso, ma certi momenti — le domeniche sera, i compleanni — la solitudine si fa sentire di più.",
    "Non è tristezza esattamente. È più una consapevolezza acuta della propria separatezza dagli altri.",
    "Pensi che si possa essere veramente felici da soli, o c'è sempre una parte che si completa solo in relazione con qualcuno?",
  ]},

  # ── ANSIA E PAURA ───────────────────────────────────────────────────────────
  {"id": "ansia_a", "cat": "ansia", "messages": [
    "Ho un'ansia di fondo che mi accompagna da anni. Non è invalidante, ma c'è sempre. Come un rumore di sottofondo.",
    "La parte strana è che quando le cose vanno bene mi aspetto sempre che stia per succedere qualcosa di brutto.",
    "Ti suona familiare questa cosa? Come mai alcune persone non riescono a godersi i momenti positivi senza aspettarsi il peggio?",
    "Come ci si libera dall'idea che la felicità sia sempre temporanea e il dolore invece sia quello vero?",
  ]},
  {"id": "ansia_b", "cat": "ansia", "messages": [
    "Mio figlio ha manifestato ansia scolastica quest'anno. Mi ha fatto rispecchiare in cose mie che pensavo di aver superato.",
    "Come si aiuta qualcuno ad affrontare l'ansia senza minimizzarla ma anche senza alimentarla con troppa attenzione?",
    "L'ansia da prestazione — si supera o si impara a conviverci? Ho sentito posizioni molto diverse.",
  ]},
  {"id": "ansia_c", "cat": "ansia", "messages": [
    "Sono una persona che controlla molto. L'ordine, i piani, le aspettative. Poi quando le cose non vanno come previsto reagisco male.",
    "So che è un meccanismo difensivo contro l'incertezza. Ma sapere da dove viene non lo smonta automaticamente.",
    "Come si allena il lasciar andare quando il controllo è diventato il tuo modo di sentirti al sicuro?",
  ]},

  # ── INVECCHIAMENTO E TEMPO ──────────────────────────────────────────────────
  {"id": "tempo_a", "cat": "tempo", "messages": [
    "Ho compiuto cinquant'anni e mi ha sorpreso quanto poco ci abbia pensato, e poi quanto ci abbia pensato.",
    "Non è paura della morte esattamente. È più una consapevolezza nuova che il tempo che ho davanti è meno di quello che ho dietro.",
    "Come cambia il modo di stare nel presente quando sai che il tempo è finito? Ho la sensazione che dovrebbe cambiare di più di quanto cambia.",
  ]},
  {"id": "tempo_b", "cat": "tempo", "messages": [
    "Guardo i miei genitori invecchiare e mi rendo conto che non so come parlare con loro di quello che stanno attraversando.",
    "C'è un tabù sull'invecchiamento e la morte che non capisco bene. Perché è così difficile parlarne mentre succede?",
    "Come si accompagna qualcuno verso la fine della vita senza fingere che non stia succedendo?",
  ]},
  {"id": "tempo_c", "cat": "tempo", "messages": [
    "Rimpiango alcune scelte che ho fatto. Non tanto per il risultato quanto per non aver vissuto pienamente certi momenti.",
    "Ho questa sensazione ricorrente di essere stato presente fisicamente ma assente mentalmente in pezzi importanti della mia vita.",
    "Come si impara a essere presenti davvero? Non come tecnica mindfulness — intendo come modo di vivere reale.",
  ]},

  # ── IDENTITÀ E CAMBIAMENTO ──────────────────────────────────────────────────
  {"id": "identita_a", "cat": "identita", "messages": [
    "Mi chiedo spesso chi sono davvero al di là dei ruoli che ricopro. Padre, lavoratore, amico. Se togliessi tutto questo, cosa rimane?",
    "Non è una crisi esistenziale. È più una curiosità autentica su quale sia il nucleo di me che non cambia.",
    "Tu pensi che esista una identità stabile o siamo semplicemente la somma delle relazioni e dei contesti in cui ci troviamo?",
  ]},
  {"id": "identita_b", "cat": "identita", "messages": [
    "Sono cambiato molto negli ultimi anni. A volte guardo indietro e faccio fatica a riconoscermi in chi ero.",
    "Non so se questo è crescita o perdita. O entrambi.",
    "Come si decide quali parti di sé proteggere dal cambiamento e quali invece lasciare andare?",
  ]},
  {"id": "identita_c", "cat": "identita", "messages": [
    "Vengo da una famiglia con radici molto forti — tradizioni, valori, aspettative. Ho sempre avuto un rapporto ambivalente con tutto questo.",
    "Da un lato mi da identità. Dall'altro a volte sento che è una gabbia. Come si porta avanti il legame con le proprie origini senza esserne prigionieri?",
    "E i valori che ti hanno trasmesso — li fai tuoi coscientemente o li porti senza nemmeno chiederti se li condividi?",
  ]},

  # ── SPIRITUALITÀ E SENSO ────────────────────────────────────────────────────
  {"id": "spiritualita_a", "cat": "spiritualita", "messages": [
    "Non sono credente nel senso tradizionale, ma ci sono momenti — davanti al mare, certi tramonti, la nascita di mio figlio — in cui sento qualcosa che non so come chiamare.",
    "Non voglio ridurlo a neuroscienze. Ma non so nemmeno se ha senso chiamarlo fede.",
    "Come vivi tu la domanda sul senso della vita? Non nel senso filosofico accademico — nel senso di come ti ci confronti concretamente.",
  ]},
  {"id": "spiritualita_b", "cat": "spiritualita", "messages": [
    "Ho amici molto credenti e amici completamente atei. Guardando entrambi mi chiedo se la differenza vera sia nelle convinzioni o nel modo di stare nell'incertezza.",
    "La cosa che invidio a chi ha fede è la pace con cui affronta certi momenti. Ma non so se è davvero pace o è sospensione del dubbio.",
    "Pensi che si possa trovare lo stesso tipo di conforto senza credere in qualcosa di trascendente?",
  ]},
  {"id": "spiritualita_c", "cat": "spiritualita", "messages": [
    "Mia madre era molto religiosa. Io non lo sono. Eppure quando è morta ho pregato. Non so nemmeno a chi.",
    "Certi rituali hanno un senso anche senza credenza? O in quel momento stavo solo cercando qualcosa a cui aggrapparmi?",
    "Come si elabora il distacco da una tradizione in cui si è cresciuti senza sentirsi in colpa?",
  ]},

]

# ═══════════════════════════════════════════════════════════════════════════════
#  FOLLOWUP — messaggi di approfondimento usati quando Genesi risponde in modo ricco
# ═══════════════════════════════════════════════════════════════════════════════

FOLLOWUPS = [
    "Interessante. Puoi approfondire?",
    "Questo mi tocca. Cosa intendi esattamente?",
    "Non ci avevo pensato così. Dimmi di più.",
    "Hai ragione, ma mi chiedo — e in situazioni estreme?",
    "Come arrivi a questa conclusione?",
    "E nel tuo modo di vedere le persone, succede spesso?",
    "Questo mi fa pensare. Continua.",
    "Cosa ti fa dire questo?",
    "Capisco. Ma c'è anche un altro modo di vederlo?",
]


# ═══════════════════════════════════════════════════════════════════════════════
#  CLIENT HTTP
# ═══════════════════════════════════════════════════════════════════════════════

class DeepConvoClient:

    def __init__(self, email: str, password: str, pause: float, dry_run: bool):
        self.email    = email
        self.password = password
        self.pause    = pause
        self.dry_run  = dry_run
        self.token    = None

    def _request(self, method, url, payload=None, token=None, params=None):
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(payload).encode() if payload else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except Exception as ex:
            return 0, str(ex)

    def login(self) -> bool:
        status, body = self._request("POST", f"{BASE_URL}/auth/login",
                                     {"email": self.email, "password": self.password})
        if status == 200:
            self.token = json.loads(body).get("access_token")
            return bool(self.token)
        return False

    def send(self, message: str) -> str:
        if self.dry_run:
            return f"[DRY RUN] risposta simulata per: {message[:60]}"
        status, body = self._request("POST", f"{BASE_URL}/api/chat/",
                                     {"message": message}, token=self.token)
        if status == 401:
            self.login()
            status, body = self._request("POST", f"{BASE_URL}/api/chat/",
                                         {"message": message}, token=self.token)
        if status != 200:
            raise RuntimeError(f"Chat HTTP {status}")
        data = json.loads(body)
        return (data.get("response") or data.get("message") or "").strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  STATE MANAGEMENT — tracking temi già usati
# ═══════════════════════════════════════════════════════════════════════════════

def load_state(state_file: str) -> dict:
    if os.path.exists(state_file):
        try:
            with open(state_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"used_ids": [], "runs": 0, "last_run": None}

def save_state(state_file: str, state: dict):
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def pick_threads(state: dict, n: int) -> list:
    """Seleziona N thread: prima quelli mai usati, poi quelli usati meno di recente."""
    used = state.get("used_ids", [])
    all_ids = [t["id"] for t in THREADS]
    unused = [tid for tid in all_ids if tid not in used]
    if len(unused) >= n:
        return random.sample(unused, n)
    # Tutti usati almeno una volta: ricomincia dal pool completo
    if not unused:
        state["used_ids"] = []
        return random.sample(all_ids, min(n, len(all_ids)))
    # Mix: prendi tutti gli unused + qualcuno dagli usati
    extra_needed = n - len(unused)
    extra = random.sample(used, min(extra_needed, len(used)))
    selected = unused + extra
    random.shuffle(selected)
    return selected[:n]


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN RUN
# ═══════════════════════════════════════════════════════════════════════════════

def run(email: str, password: str, pause: float, n_themes: int,
        dry_run: bool, state_file: str):

    print(f"\n{'='*60}")
    print(f"  DEEP CONVERSATION TRAINING — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"  Account: {email}")
    print(f"  Temi: {n_themes}  |  Pausa: {pause}s  |  Dry-run: {dry_run}")
    print(f"{'='*60}\n")

    state  = load_state(state_file)
    client = DeepConvoClient(email, password, pause, dry_run)

    if not dry_run:
        if not client.login():
            print("✗ Login fallito — verifica credenziali")
            sys.exit(1)
        print("✓ Login OK\n")

    selected_ids = pick_threads(state, n_themes)
    threads_map  = {t["id"]: t for t in THREADS}

    total_messages = 0
    total_followups = 0
    start_time = time.time()

    for i, tid in enumerate(selected_ids, 1):
        thread = threads_map[tid]
        cat    = thread["cat"]
        msgs   = thread["messages"]

        print(f"\n[{i}/{n_themes}] TEMA: {cat.upper()} — thread: {tid}")
        print(f"  {len(msgs)} messaggi in questo thread")

        for j, msg in enumerate(msgs):
            elapsed = time.time() - start_time
            print(f"\n  → [{j+1}/{len(msgs)}] ({elapsed:.0f}s) Invio: {msg[:70]}{'...' if len(msg)>70 else ''}")

            try:
                response = client.send(msg)
                total_messages += 1
                resp_preview = response[:120].replace('\n', ' ')
                print(f"  ← Genesi ({len(response)} chars): {resp_preview}{'...' if len(response)>120 else ''}")

                # Followup automatico se risposta ricca (>300 chars)
                if len(response) > 300 and j < len(msgs) - 1:
                    fu = random.choice(FOLLOWUPS)
                    jitter = random.uniform(pause * 0.7, pause * 1.3)
                    if not dry_run:
                        time.sleep(jitter)
                    print(f"\n  → [followup] ({jitter:.0f}s) {fu}")
                    fu_response = client.send(fu)
                    total_followups += 1
                    print(f"  ← Genesi ({len(fu_response)} chars): {fu_response[:100]}...")

            except Exception as e:
                print(f"  ✗ Errore: {e}")

            # Pausa tra messaggi (con jitter ±30%)
            if j < len(msgs) - 1:
                jitter = random.uniform(pause * 0.7, pause * 1.3)
                print(f"  ⏸  pausa {jitter:.0f}s...")
                if not dry_run:
                    time.sleep(jitter)

        # Pausa più lunga tra temi diversi
        if i < len(selected_ids):
            inter_pause = pause * 1.5
            print(f"\n  ⏸  cambio tema — pausa {inter_pause:.0f}s...")
            if not dry_run:
                time.sleep(inter_pause)

        state["used_ids"].append(tid)

    # Fine run
    elapsed_total = time.time() - start_time
    state["runs"]     = state.get("runs", 0) + 1
    state["last_run"] = datetime.utcnow().isoformat()
    save_state(state_file, state)

    print(f"\n{'='*60}")
    print(f"  COMPLETATO in {elapsed_total/60:.1f} min")
    print(f"  Messaggi inviati: {total_messages} + {total_followups} followup")
    print(f"  Temi coperti: {', '.join(selected_ids)}")
    print(f"  Run totali: {state['runs']}")
    print(f"  Thread rimanenti non ancora usati: "
          f"{len([t for t in THREADS if t['id'] not in state['used_ids']])}")
    print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deep Conversation Training")
    parser.add_argument("--email",    default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PWD)
    parser.add_argument("--pause",    type=float, default=30,
                        help="Pausa base tra messaggi in secondi (default: 30)")
    parser.add_argument("--themes",   type=int, default=12,
                        help="Numero di temi per sessione (default: 12, ~1 ora)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Simula senza inviare messaggi reali")
    parser.add_argument("--state-file", default="memory/admin/deep_convo_state.json",
                        help="File per tracciare temi già usati")
    args = parser.parse_args()

    run(
        email=args.email,
        password=args.password,
        pause=args.pause,
        n_themes=args.themes,
        dry_run=args.dry_run,
        state_file=args.state_file,
    )
