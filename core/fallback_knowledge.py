"""
FALLBACK KNOWLEDGE - Genesi Cognitive System
Dizionario deterministico per risposte fattuali minime quando LLM non e' disponibile.
Zero GPT. Zero API. Solo fatti verificati.
"""

import logging

logger = logging.getLogger(__name__)

# Dizionario di conoscenza fattuale minima.
# Chiavi: keyword normalizzate (lowercase). Valori: risposta fattuale breve.
KNOWLEDGE_DB = {
    "pressione arteriosa": (
        "La pressione arteriosa e' la forza esercitata dal sangue sulle pareti delle arterie. "
        "I valori normali sono circa 120/80 mmHg. Valori superiori a 140/90 mmHg indicano ipertensione. "
        "E' importante misurarla regolarmente e consultare un medico per valori anomali."
    ),
    "capitale germania": (
        "La capitale della Germania e' Berlino. "
        "E' la citta' piu' grande del paese con circa 3,7 milioni di abitanti."
    ),
    "capitale francia": (
        "La capitale della Francia e' Parigi. "
        "E' la citta' piu' grande del paese con circa 2,1 milioni di abitanti nell'area urbana."
    ),
    "sistema solare": (
        "Il sistema solare e' composto dal Sole e da otto pianeti: "
        "Mercurio, Venere, Terra, Marte, Giove, Saturno, Urano e Nettuno. "
        "Include anche pianeti nani come Plutone, asteroidi, comete e satelliti naturali."
    ),
    "capitale italia": (
        "La capitale dell'Italia e' Roma. "
        "E' la citta' piu' grande del paese con circa 2,8 milioni di abitanti."
    ),
    "fotosintesi": (
        "La fotosintesi e' il processo con cui le piante convertono luce solare, acqua e anidride carbonica "
        "in glucosio e ossigeno. Avviene nei cloroplasti grazie alla clorofilla."
    ),
    "dna": (
        "Il DNA (acido desossiribonucleico) e' la molecola che contiene le informazioni genetiche "
        "di tutti gli organismi viventi. Ha una struttura a doppia elica scoperta da Watson e Crick nel 1953."
    ),
    "acqua": (
        "L'acqua e' una molecola composta da due atomi di idrogeno e uno di ossigeno (H2O). "
        "Bolle a 100 gradi C e congela a 0 gradi C a pressione atmosferica standard."
    ),
}

# Pattern di matching per domande fattuali
FACTUAL_TRIGGERS = [
    "cos'e'", "cos'è", "che cos'e'", "che cos'è",
    "definisci", "che capitale", "quanto e'", "quanto è",
    "cosa significa",
]


def lookup_fallback(message: str) -> str:
    """
    Cerca una risposta fattuale nel dizionario interno.
    Ritorna stringa vuota se nessun match trovato.
    Matching: tutte le parole della chiave devono essere presenti nel messaggio.
    """
    msg_lower = message.lower().strip()

    # Verifica che sia una domanda fattuale
    if not any(trigger in msg_lower for trigger in FACTUAL_TRIGGERS):
        return ""

    # Cerca match nel dizionario — tutte le parole della chiave devono essere nel messaggio
    msg_words = set(msg_lower.split())
    for key, answer in KNOWLEDGE_DB.items():
        key_words = set(key.split())
        if key_words.issubset(msg_words):
            logger.info("FALLBACK_KNOWLEDGE_HIT key=%s msg=%s", key, msg_lower[:60])
            return answer

    logger.info("FALLBACK_KNOWLEDGE_MISS msg=%s", msg_lower[:60])
    return ""
