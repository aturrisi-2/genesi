"""
CURIOSITY ENGINE - Genesi Cognitive System v3
Motore di curiosità selettiva e mirata.
Analizza il messaggio utente, calcola curiosity_score,
genera domande esplorative specifiche al contenuto.
Zero LLM. Zero API. Solo analisi locale e pattern neurali.

Pipeline position: dopo evolution_engine, prima di emotional_intensity_engine.
"""

import logging
import random
import re
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# TRIGGER PATTERNS — attivano modalità esplorativa
# ═══════════════════════════════════════════════════════════════

# Ambivalenza: messaggi che esprimono conflitto interno
AMBIVALENCE_PATTERNS = [
    "non so se", "non so cosa", "da una parte", "dall'altra",
    "vorrei ma", "dovrei ma", "forse si forse no", "non sono sicuro",
    "non sono sicura", "non saprei", "e' complicato", "e' complesso",
    "non riesco a decidere", "sono indeciso", "sono indecisa",
    "mi sento diviso", "mi sento divisa", "due parti di me",
    "una parte di me", "vorrei e non vorrei",
]

# Vulnerabilità implicita: fragilità non dichiarata esplicitamente
VULNERABILITY_PATTERNS = [
    "non ce la faccio", "non farcela", "non riesco", "mi sento perso",
    "mi sento persa", "non so cosa voglio", "non so chi sono",
    "mi sento sbagliato", "mi sento sbagliata", "non valgo",
    "non sono abbastanza", "mi sento inadeguato", "mi sento inadeguata",
    "ho paura di", "temo di", "mi vergogno", "non merito",
    "sono un fallimento", "non ho speranza", "non vedo via d'uscita",
    "mi sento intrappolato", "mi sento intrappolata",
    "non so come andare avanti", "sono bloccato", "sono bloccata",
]

# Frasi identitarie: crisi di identità o direzione
IDENTITY_PATTERNS = [
    "non so cosa voglio", "non so chi sono", "mi sento perso",
    "mi sento persa", "ho perso me stesso", "ho perso me stessa",
    "non mi riconosco", "non so dove sto andando", "non ho direzione",
    "non so piu' chi sono", "chi sono davvero", "cosa voglio davvero",
    "non so cosa fare della mia vita", "mi sento senza identita'",
    "sto cambiando", "non sono piu' quello di prima",
]

# Stato emotivo vago: emozioni non definite
VAGUE_EMOTION_PATTERNS = [
    "mi sento strano", "mi sento strana", "non so come mi sento",
    "mi sento vuoto", "mi sento vuota", "confuso", "confusa",
    "un po' cosi'", "non saprei dire", "qualcosa non va",
    "c'e' qualcosa", "mi sento diverso", "mi sento diversa",
    "non sto bene ma non so perche'", "mi sento off",
    "mi sento sospeso", "mi sento sospesa", "in un limbo",
    "non so spiegare", "e' una sensazione", "sento qualcosa",
]

# Stopwords per estrazione semantica
STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
    "di", "del", "dello", "della", "dei", "degli", "delle",
    "a", "al", "allo", "alla", "ai", "agli", "alle",
    "da", "dal", "dallo", "dalla", "dai", "dagli", "dalle",
    "in", "nel", "nello", "nella", "nei", "negli", "nelle",
    "su", "sul", "sullo", "sulla", "sui", "sugli", "sulle",
    "con", "per", "tra", "fra", "e", "o", "ma", "che", "chi",
    "non", "mi", "ti", "si", "ci", "vi", "ne", "lo", "me", "te",
    "se", "come", "cosa", "dove", "quando", "quanto", "quale",
    "sono", "sei", "siamo", "siete", "ho", "hai", "ha",
    "abbiamo", "avete", "hanno", "essere", "avere", "fare",
    "sto", "stai", "sta", "stiamo", "state", "stanno",
    "questo", "questa", "questi", "queste", "quello", "quella",
    "mio", "mia", "miei", "mie", "tuo", "tua", "tuoi", "tue",
    "suo", "sua", "suoi", "sue", "nostro", "nostra",
    "molto", "poco", "tanto", "troppo", "tutto", "niente",
    "piu'", "piu", "meno", "anche", "ancora", "sempre", "mai",
    "gia'", "gia", "poi", "ora", "adesso", "qui", "li'", "la'",
    "pero'", "pero", "quindi", "allora", "cosi'", "cosi",
    "proprio", "solo", "soltanto", "davvero", "veramente",
    "forse", "magari", "comunque", "invece", "oppure",
    "sento", "sentire", "dire", "detto", "fatto", "volta",
    "po'", "po", "un po'", "un po",
}

# Intent concreti che NON devono attivare curiosità
CONCRETE_INTENTS = [
    "che ore sono", "che ora e'", "che giorno e'", "che data e'",
    "meteo", "previsioni", "notizie", "news",
    "come ti chiami", "chi sei", "cosa sei",
    "ricordi", "ti ricordi", "cosa sai di me",
]

# ═══════════════════════════════════════════════════════════════
# NEURAL QUESTION TEMPLATES — pattern specifici per tipo
# ═══════════════════════════════════════════════════════════════

# Ogni template ha {keyword} placeholder per parola semantica dal messaggio

TEMPORAL_QUESTIONS = [
    "Da quanto tempo senti questa sensazione legata a {keyword}?",
    "Quando e' iniziato questo senso di {keyword}?",
    "E' qualcosa che senti da poco o ti accompagna da tempo, questo {keyword}?",
    "C'e' stato un momento preciso in cui hai iniziato a sentirti cosi' riguardo a {keyword}?",
]

ORIGIN_QUESTIONS = [
    "C'e' stato qualcosa che ha acceso questo stato di {keyword}?",
    "Riesci a risalire a cosa ha innescato questa sensazione di {keyword}?",
    "Cosa e' successo prima che iniziassi a sentirti cosi' — c'e' un evento legato a {keyword}?",
    "Questo senso di {keyword} e' arrivato all'improvviso o si e' costruito nel tempo?",
]

DIFFERENTIATION_QUESTIONS = [
    "Quando dici {keyword}, e' piu' una stanchezza interiore o una perdita di direzione?",
    "Quello che chiami {keyword} — lo senti piu' nel corpo o nella mente?",
    "Se dovessi dare un colore a questo {keyword}, quale sarebbe?",
    "Questo {keyword} che descrivi — somiglia piu' a una pausa forzata o a un vuoto?",
]

IMPACT_QUESTIONS = [
    "In quale momento della giornata senti di piu' questo {keyword}?",
    "Come influisce questo {keyword} sulle tue giornate, concretamente?",
    "C'e' qualcosa che riesce ad alleviare questo senso di {keyword}, anche solo per un momento?",
    "Questo {keyword} cambia il modo in cui ti relazioni con le persone intorno a te?",
]

CONFLICT_QUESTIONS = [
    "C'e' una parte di te che vuole qualcosa di diverso rispetto a questo {keyword}?",
    "Se potessi scegliere, cosa vorresti al posto di questo {keyword}?",
    "Senti che c'e' un conflitto dentro di te riguardo a {keyword}?",
    "Cosa ti trattiene dal cambiare questa situazione legata a {keyword}?",
]

# Pool completo per selezione random per tipo
QUESTION_POOLS = {
    "temporal": TEMPORAL_QUESTIONS,
    "origin": ORIGIN_QUESTIONS,
    "differentiation": DIFFERENTIATION_QUESTIONS,
    "impact": IMPACT_QUESTIONS,
    "conflict": CONFLICT_QUESTIONS,
}

# Domande fallback senza keyword (per quando l'estrazione semantica non trova nulla)
FALLBACK_QUESTIONS = {
    "temporal": [
        "Da quanto tempo ti senti cosi'?",
        "E' qualcosa di recente o ti accompagna da un po'?",
    ],
    "origin": [
        "Riesci a individuare cosa ha innescato questa sensazione?",
        "C'e' stato un momento preciso in cui e' iniziato?",
    ],
    "differentiation": [
        "Se dovessi descrivere quello che senti con una sola parola, quale sarebbe?",
        "Quello che provi — e' piu' qualcosa che senti nel corpo o nella mente?",
    ],
    "impact": [
        "Come sta influenzando le tue giornate, concretamente?",
        "C'e' un momento della giornata in cui lo senti di piu'?",
    ],
    "conflict": [
        "C'e' una parte di te che vorrebbe qualcosa di diverso?",
        "Senti che dentro di te c'e' un conflitto su questo?",
    ],
}


class CuriosityEngine:
    """
    Motore di curiosità selettiva.
    Analizza il messaggio, calcola curiosity_score,
    inietta domande esplorative specifiche al contenuto.
    Zero LLM. Zero API.
    """

    def __init__(self):
        logger.info("CURIOSITY_ENGINE: Active")

    def inject(self, response: str, message: str, brain_state: Dict[str, Any]) -> str:
        """
        Punto di ingresso principale.
        Analizza il messaggio, calcola curiosity_score,
        inietta domanda esplorativa se appropriato.

        Args:
            response: risposta base da evolution_engine
            message: messaggio originale dell'utente
            brain_state: stato completo

        Returns:
            risposta con eventuale domanda esplorativa iniettata
        """
        msg_lower = message.lower().strip()

        # Skip concrete/tool intents
        if self._is_concrete(msg_lower):
            return response

        # Calculate curiosity score
        score, triggers = self._calculate_curiosity_score(msg_lower, brain_state)

        if score < 0.3:
            return response

        # Extract semantic keywords from user message
        keywords = self._extract_semantic_keywords(msg_lower)

        # Select question type based on triggers
        question_type = self._select_question_type(triggers, msg_lower)

        # Generate targeted question
        question = self._generate_question(question_type, keywords, msg_lower)

        if not question:
            return response

        # Check if response already contains a question
        if self._has_specific_question(response):
            # Response already has a question — don't stack
            logger.info("CURIOSITY_SKIP already_has_question score=%.2f", score)
            return response

        # Inject question into response
        result = self._inject_question(response, question, score)

        logger.info("CURIOSITY_INJECTED score=%.2f type=%s keywords=%s",
                     score, question_type, keywords[:3])
        return result

    # ═══════════════════════════════════════════════════════════
    # SCORING
    # ═══════════════════════════════════════════════════════════

    def _calculate_curiosity_score(self, msg: str,
                                    brain_state: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        Calcola curiosity_score (0.0-1.0) e lista di trigger attivati.
        """
        score = 0.0
        triggers = []

        # Ambivalence
        if any(p in msg for p in AMBIVALENCE_PATTERNS):
            score += 0.35
            triggers.append("ambivalence")

        # Vulnerability
        if any(p in msg for p in VULNERABILITY_PATTERNS):
            score += 0.30
            triggers.append("vulnerability")

        # Identity crisis
        if any(p in msg for p in IDENTITY_PATTERNS):
            score += 0.35
            triggers.append("identity")

        # Vague emotion
        if any(p in msg for p in VAGUE_EMOTION_PATTERNS):
            score += 0.30
            triggers.append("vague_emotion")

        # Latent state curiosity boost
        latent = brain_state.get("latent", {})
        latent_curiosity = latent.get("curiosity", 0.5)
        if latent_curiosity > 0.5:
            score += 0.10
            triggers.append("latent_curiosity")

        # Emotional resonance boost
        resonance = latent.get("emotional_resonance", 0.5)
        if resonance > 0.5:
            score += 0.05

        # Message length bonus (longer = more to explore)
        words = msg.split()
        if len(words) > 10:
            score += 0.05
        if len(words) > 20:
            score += 0.05

        # Emotion intensity from brain
        emotion = brain_state.get("emotion", {})
        intensity = emotion.get("intensity", 0.3)
        if intensity > 0.5:
            score += 0.10
            triggers.append("high_intensity")

        return min(1.0, score), triggers

    # ═══════════════════════════════════════════════════════════
    # SEMANTIC EXTRACTION
    # ═══════════════════════════════════════════════════════════

    def _extract_semantic_keywords(self, msg: str) -> List[str]:
        """
        Estrae parole semanticamente significative dal messaggio.
        Rimuove stopwords, punteggiatura, parole troppo corte.
        """
        # Clean punctuation
        cleaned = re.sub(r'[^\w\s\']', ' ', msg)
        words = cleaned.split()

        # Filter
        keywords = []
        for w in words:
            w_clean = w.strip().lower()
            if len(w_clean) < 3:
                continue
            if w_clean in STOPWORDS:
                continue
            keywords.append(w_clean)

        # Deduplicate preserving order
        seen = set()
        unique = []
        for k in keywords:
            if k not in seen:
                seen.add(k)
                unique.append(k)

        return unique

    # ═══════════════════════════════════════════════════════════
    # QUESTION TYPE SELECTION
    # ═══════════════════════════════════════════════════════════

    def _select_question_type(self, triggers: List[str], msg: str) -> str:
        """
        Seleziona il tipo di domanda neurale basato sui trigger.
        """
        # Priority mapping
        if "ambivalence" in triggers:
            return random.choice(["conflict", "differentiation"])
        if "identity" in triggers:
            return random.choice(["origin", "temporal", "conflict"])
        if "vulnerability" in triggers:
            return random.choice(["temporal", "origin", "impact"])
        if "vague_emotion" in triggers:
            return random.choice(["differentiation", "temporal", "impact"])
        if "high_intensity" in triggers:
            return random.choice(["origin", "impact"])

        # Default
        return random.choice(["temporal", "origin", "differentiation", "impact", "conflict"])

    # ═══════════════════════════════════════════════════════════
    # QUESTION GENERATION
    # ═══════════════════════════════════════════════════════════

    def _generate_question(self, q_type: str, keywords: List[str],
                            msg: str) -> Optional[str]:
        """
        Genera domanda esplorativa specifica.
        Usa keyword dal messaggio per personalizzare.
        """
        pool = QUESTION_POOLS.get(q_type, TEMPORAL_QUESTIONS)
        fallback_pool = FALLBACK_QUESTIONS.get(q_type, FALLBACK_QUESTIONS["temporal"])

        if keywords:
            # Pick best keyword (prefer emotionally loaded ones)
            keyword = self._pick_best_keyword(keywords, msg)
            template = random.choice(pool)
            try:
                question = template.format(keyword=keyword)
                return question
            except (KeyError, IndexError):
                pass

        # Fallback: no keyword available
        return random.choice(fallback_pool)

    def _pick_best_keyword(self, keywords: List[str], msg: str) -> str:
        """
        Seleziona la keyword più significativa.
        Preferisce parole emotive e identitarie.
        """
        # Emotional priority words
        emotional_words = {
            "vuoto", "vuota", "perso", "persa", "solo", "sola",
            "paura", "ansia", "rabbia", "tristezza", "dolore",
            "confuso", "confusa", "stanco", "stanca", "bloccato", "bloccata",
            "inadeguato", "inadeguata", "sbagliato", "sbagliata",
            "depresso", "depressa", "angoscia", "terrore", "vergogna",
            "colpa", "frustrazione", "solitudine", "mancanza", "nostalgia",
            "intrappolato", "intrappolata", "sospeso", "sospesa",
            "fallimento", "speranza", "direzione", "identita'",
            "cambiamento", "perdita", "separazione", "abbandono",
        }

        # Check for emotional keywords first
        for kw in keywords:
            if kw in emotional_words:
                return kw

        # Then pick longest keyword (usually more specific)
        if keywords:
            return max(keywords, key=len)

        return "questo"

    # ═══════════════════════════════════════════════════════════
    # INJECTION
    # ═══════════════════════════════════════════════════════════

    def _inject_question(self, response: str, question: str, score: float) -> str:
        """
        Inietta la domanda nella risposta.
        Se score > 0.6: riformula la parte finale con la domanda.
        Se score 0.3-0.6: appende la domanda.
        """
        response = response.rstrip()

        if score > 0.6:
            # High curiosity: replace generic ending if present
            response = self._replace_generic_ending(response, question)
        else:
            # Moderate curiosity: append
            if not response.endswith("?"):
                response = f"{response} {question}"

        return response

    def _replace_generic_ending(self, response: str, question: str) -> str:
        """
        Sostituisce la parte finale generica con la domanda mirata.
        """
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', response)

        if len(sentences) <= 1:
            return f"{response} {question}"

        # Check if last sentence is generic
        last = sentences[-1].strip().lower()
        generic_markers = [
            "dimmi", "raccontami", "ti ascolto", "sono qui",
            "parlami", "continua", "vai avanti",
            "vuoi raccontarmi", "come ti senti",
        ]

        if any(g in last for g in generic_markers):
            # Replace last sentence with targeted question
            sentences[-1] = question
            return " ".join(sentences)

        # Not generic: just append
        return f"{response} {question}"

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _is_concrete(self, msg: str) -> bool:
        """Rileva intent concreti che non necessitano curiosità."""
        return any(c in msg for c in CONCRETE_INTENTS)

    def _has_specific_question(self, text: str) -> bool:
        """
        Verifica se il testo contiene già una domanda specifica (non generica).
        """
        if "?" not in text:
            return False

        # Extract questions
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for s in sentences:
            if "?" in s:
                s_lower = s.lower()
                # Check if it's a generic question
                generic = [
                    "come ti senti?", "vuoi raccontarmi?", "dimmi pure?",
                    "come stai?", "vuoi parlarne?", "cosa ne pensi?",
                ]
                if not any(g in s_lower for g in generic):
                    # Has a non-generic question
                    return True
        return False

    def get_info(self) -> dict:
        """Informazioni configurazione Curiosity Engine."""
        return {
            "engine": "curiosity_engine",
            "trigger_types": ["ambivalence", "vulnerability", "identity", "vague_emotion"],
            "question_types": list(QUESTION_POOLS.keys()),
            "provider": "local",
            "llm_calls": 0,
        }


# Singleton
curiosity_engine = CuriosityEngine()
