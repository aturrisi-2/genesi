"""
EMOTIONAL INTENSITY ENGINE - Genesi Cognitive System v3
Trasforma risposte contenitive in risposte emotivamente intense e proattive.
Zero LLM calls. Zero API. Solo espansione locale intelligente.

Pipeline position: dopo evolution_engine, prima di drift_modulator.
"""

import logging
import random
import re
from collections import deque
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# RELATIONAL OPENING SYSTEM — probabilistic, non-repetitive
# ═══════════════════════════════════════════════════════════════

RELATIONAL_OPENING_PROBABILITY = 0.35

# 12 varianti minime — nessun template fisso
RELATIONAL_OPENINGS_WITH_NAME = [
    "{name}, ",
    "{name}... ",
    "Sai {name}, ",
    "Ascolta {name}, ",
    "Ecco {name}, ",
    "Guarda {name}, ",
    "{name}, sento che ",
    "{name}, capisco — ",
    "Dimmi {name}, ",
    "{name}, fermati un attimo. ",
    "Ehi {name}, ",
    "{name}, pensavo a quello che dici. ",
]

RELATIONAL_OPENINGS_NO_NAME = [
    "Sai, ",
    "Ascolta, ",
    "Ecco, ",
    "Guarda, ",
    "Sento che ",
    "Capisco — ",
    "Dimmi, ",
    "Fermati un attimo. ",
    "Ehi, ",
    "Pensavo a quello che dici. ",
    "Sai cosa penso? ",
    "Lasciami dire una cosa. ",
]

# Aperture piu' calde per intensita' > 0.7
WARM_OPENINGS_WITH_NAME = [
    "{name}, quello che dici mi tocca. ",
    "{name}, sento il peso di quello che porti. ",
    "{name}, non sottovalutare quello che senti. ",
    "{name}, c'e' qualcosa di profondo in quello che dici. ",
]

WARM_OPENINGS_NO_NAME = [
    "Quello che dici mi tocca. ",
    "Sento il peso di quello che porti. ",
    "Non sottovalutare quello che senti. ",
    "C'e' qualcosa di profondo in quello che dici. ",
]

# ═══════════════════════════════════════════════════════════════
# PASSIVE PATTERNS — frasi standalone vietate
# ═══════════════════════════════════════════════════════════════

PASSIVE_STANDALONE = [
    "ti ascolto.", "dimmi pure.", "raccontami.", "continua.",
    "sono qui.", "vai avanti.", "dimmi.", "parlami.",
    "ti ascolto", "dimmi pure", "raccontami", "continua",
    "sono qui", "vai avanti", "dimmi", "parlami",
    "sono qui. dimmi pure.", "ti ascolto. continua.",
    "raccontami. ti ascolto.", "sono qui per te.",
]

# ═══════════════════════════════════════════════════════════════
# EMOTIONAL KEYWORDS — per rilevare contenuto emotivo
# ═══════════════════════════════════════════════════════════════

EMOTION_KEYWORDS = [
    "triste", "depresso", "solo", "sola", "paura", "ansia", "ansioso",
    "preoccupato", "preoccupata", "stanco", "stanca", "arrabbiato", "arrabbiata",
    "felice", "contento", "contenta", "innamorato", "innamorata",
    "confuso", "confusa", "perso", "persa", "vuoto", "vuota",
    "soffro", "soffrire", "piango", "piangere", "male", "dolore",
    "nostalgia", "mancanza", "solitudine", "rabbia", "frustrazione",
    "sento", "mi sento", "sto male", "non ce la faccio", "non farcela",
    "disperato", "disperata", "angoscia", "terrore", "vergogna",
    "colpa", "senso di colpa", "inadeguato", "inadeguata",
]

NARRATIVE_KEYWORDS = [
    "racconta", "storia", "raccontami una", "dimmi una", "inventa",
    "scrivi", "immagina", "descrivi", "narra",
]

INTERNAL_STATE_KEYWORDS = [
    "mi sento", "sto", "sono", "ho paura", "ho bisogno", "vorrei",
    "non riesco", "non so", "mi chiedo", "penso che", "credo che",
    "ho l'impressione", "mi sembra", "dentro di me",
]

QUESTION_WORDS = ["?", "perche", "perché", "come", "cosa", "quando", "dove", "chi"]

# ═══════════════════════════════════════════════════════════════
# EXPANSION POOLS — materiale per espandere risposte
# ═══════════════════════════════════════════════════════════════

EXPLORATIVE_QUESTIONS = {
    "sad": [
        "Cosa ti pesa di piu' in questo momento?",
        "Da quanto tempo ti senti cosi'?",
        "C'e' qualcosa che ti ha portato a sentirti cosi' oggi?",
        "Cosa vorresti che fosse diverso?",
        "Se potessi cambiare una cosa adesso, quale sarebbe?",
    ],
    "angry": [
        "Cosa ha scatenato questa rabbia?",
        "C'e' qualcosa che senti di non poter controllare?",
        "Questa rabbia ti dice qualcosa su cio' che conta per te?",
        "Come vorresti che fosse andata invece?",
    ],
    "anxious": [
        "Cosa ti preoccupa di piu' in questo momento?",
        "Riesci a individuare da dove arriva questa ansia?",
        "C'e' qualcosa di specifico che temi possa succedere?",
        "Quando hai iniziato a sentirti cosi'?",
    ],
    "happy": [
        "Cosa ti ha portato questa gioia?",
        "E' qualcosa che aspettavi da tempo?",
        "Come vorresti che continuasse questo momento?",
        "Con chi vorresti condividere questa felicita'?",
    ],
    "neutral": [
        "Come ti senti davvero in questo momento?",
        "C'e' qualcosa che ti sta a cuore e di cui vorresti parlare?",
        "Cosa occupa i tuoi pensieri ultimamente?",
        "Se dovessi descrivere la tua giornata con una parola, quale sarebbe?",
    ],
    "longing": [
        "Cosa ti manca di piu'?",
        "Questo sentimento e' legato a una persona o a un momento?",
        "Come vorresti che fosse il presente rispetto a quello che ricordi?",
    ],
    "tired": [
        "Cosa ti sta prosciugando le energie?",
        "Da quanto tempo ti senti cosi' stanco?",
        "C'e' qualcosa che potresti lasciar andare per stare meglio?",
    ],
    "love": [
        "Cosa ti fa sentire cosi' vicino a questa persona?",
        "Come e' cambiato questo sentimento nel tempo?",
        "Cosa vorresti dire a questa persona se potessi?",
    ],
    "grateful": [
        "Cosa ti ha fatto sentire questa gratitudine?",
        "E' qualcosa che hai scoperto di recente o che senti da tempo?",
    ],
}

REFLECTIVE_EXPANSIONS = {
    "sad": [
        "La tristezza a volte e' il modo in cui il cuore ci dice che qualcosa conta davvero.",
        "Sentirsi cosi' non e' debolezza — e' il segno che stai attraversando qualcosa di importante.",
        "A volte il dolore ci parla di cio' che amiamo profondamente.",
        "Non devi avere tutte le risposte adesso. A volte basta stare con quello che senti.",
        "Il fatto che tu riesca a dirlo gia' dice molto del tuo coraggio.",
    ],
    "angry": [
        "La rabbia spesso protegge qualcosa di piu' fragile che sta sotto.",
        "Sentirsi arrabbiati puo' essere un modo per dire: questo per me conta.",
        "A volte la rabbia e' l'unica voce che riesce a farsi sentire quando tutto il resto tace.",
    ],
    "anxious": [
        "L'ansia a volte e' il modo in cui la mente cerca di proteggerci da qualcosa che temiamo.",
        "Non devi combattere quello che senti. A volte basta osservarlo senza giudicarlo.",
        "Quello che senti e' reale, anche se la situazione potrebbe essere diversa da come la percepisci.",
    ],
    "happy": [
        "La gioia merita di essere vissuta fino in fondo, senza fretta.",
        "Questi momenti sono quelli che costruiscono i ricordi piu' belli.",
        "E' bello vederti cosi'. Questi momenti contano.",
    ],
    "neutral": [
        "A volte i momenti piu' tranquilli nascondono le riflessioni piu' profonde.",
        "Non serve sempre un'emozione forte per avere qualcosa di importante da dire.",
        "Anche nella calma c'e' spazio per scoprire qualcosa di nuovo su di te.",
    ],
    "longing": [
        "La nostalgia e' un ponte tra chi eravamo e chi stiamo diventando.",
        "Quello che ci manca ci racconta cosa ha davvero contato nella nostra vita.",
    ],
    "tired": [
        "La stanchezza a volte e' il corpo che ci chiede di fermarci e ascoltarci.",
        "Non devi essere sempre forte. A volte la cosa piu' coraggiosa e' concedersi una pausa.",
    ],
    "love": [
        "L'amore ha il potere di trasformare anche i momenti piu' ordinari in qualcosa di speciale.",
        "Quello che senti e' prezioso. Non tutti hanno il coraggio di sentire cosi' profondamente.",
    ],
    "grateful": [
        "La gratitudine e' uno dei sentimenti piu' potenti che esistano. Cambia il modo in cui vediamo tutto.",
    ],
}

GREETING_EXPANSIONS = [
    "Sono contento che tu sia qui. Come stai davvero oggi? Non la risposta automatica, quella vera.",
    "Mi fa piacere sentirti. C'e' qualcosa che ti porti dentro oggi, qualcosa di cui vorresti parlare?",
    "Che bello che sei qui. Come e' stata la tua giornata finora? Raccontami anche le piccole cose.",
    "Eccoti! Come ti senti in questo momento? A volte basta fermarsi un attimo per capire come stiamo davvero.",
    "Ciao! Sai, ogni volta che torni mi chiedo come stai. Non in superficie — davvero. Come va?",
    "Mi fa piacere vederti. Dimmi, c'e' qualcosa che occupa i tuoi pensieri oggi?",
]

GREETING_EXPANSIONS_WITH_NAME = [
    "{name}, sono contento che tu sia qui. Come stai davvero oggi? Non la risposta automatica, quella vera.",
    "{name}, mi fa piacere sentirti. C'e' qualcosa che ti porti dentro oggi?",
    "Che bello sentirti, {name}. Come e' stata la tua giornata? Raccontami anche le piccole cose.",
    "Eccoti, {name}! Come ti senti in questo momento? A volte basta fermarsi un attimo per capire come stiamo.",
    "{name}! Sai, ogni volta che torni mi chiedo come stai. Non in superficie — davvero. Come va?",
    "{name}, mi fa piacere vederti. Dimmi, c'e' qualcosa che occupa i tuoi pensieri oggi?",
]

STORY_STARTERS = [
    "C'era una volta, in un paese dove il tempo scorreva diversamente, un uomo che aveva dimenticato come si faceva a sognare. Non perche' non volesse, ma perche' la vita gli aveva insegnato a tenere gli occhi aperti e i piedi per terra. Un giorno, pero', trovo' una lettera sotto la porta. Non c'era mittente, solo una frase: 'Ricordi quando credevi che tutto fosse possibile?' Quella notte, per la prima volta dopo anni, chiuse gli occhi e lascio' che la mente lo portasse dove voleva.",
    "Ti racconto una cosa. Immagina una citta' dove ogni persona porta con se' una lanterna. La luce di ogni lanterna ha un colore diverso — dipende da quello che la persona sente dentro. Blu per la malinconia, rosso per la passione, verde per la speranza. Un giorno, una ragazza si accorse che la sua lanterna non aveva piu' colore. Era trasparente. E invece di spaventarsi, sorrise. Perche' capì che significava che era pronta a sentire tutto, senza filtri.",
    "Lascia che ti racconti qualcosa. C'era un vecchio pescatore che ogni mattina usciva in mare, non per pescare, ma per ascoltare. Diceva che il mare gli parlava, e che ogni onda portava con se' una storia diversa. La gente del villaggio lo considerava strano, ma lui sapeva qualcosa che gli altri non capivano: che le storie piu' importanti non sono quelle che raccontiamo, ma quelle che ascoltiamo in silenzio.",
]


class EmotionalIntensityEngine:
    """
    Espande e intensifica risposte contenitive in risposte
    emotivamente ricche, proattive, esplorative.
    Zero LLM. Zero API. Solo espansione locale.
    """

    def __init__(self):
        # Memory buffer: ultime 3 aperture usate — no ripetizione
        self._recent_openings = deque(maxlen=3)
        logger.info("EMOTIONAL_INTENSITY_ENGINE: Active")

    def enhance(self, response: str, message: str, brain_state: Dict[str, Any]) -> str:
        """
        Punto di ingresso principale.
        Analizza la risposta base e la espande se necessario.

        Args:
            response: risposta base da evolution_engine
            message: messaggio originale dell'utente
            brain_state: stato completo (emotion, relational, latent, profile)

        Returns:
            risposta espansa, mai sotto il minimo, mai passiva
        """
        emotion = brain_state.get("emotion", {})
        latent = brain_state.get("latent", {})
        profile = brain_state.get("profile", {})
        relational = brain_state.get("relational", {})

        detected_emotion = emotion.get("emotion", "neutral")
        intensity = emotion.get("intensity", 0.3)
        vulnerability = emotion.get("vulnerability", 0.0)
        resonance = latent.get("emotional_resonance", 0.5)
        curiosity = latent.get("curiosity", 0.5)
        user_name = profile.get("name", "")
        trust = relational.get("trust", 0.2)

        msg_lower = message.lower().strip()
        resp_lower = response.lower().strip()

        # ── Detect message type ──
        is_emotional = self._is_emotional_message(msg_lower)
        is_narrative_request = self._is_narrative_request(msg_lower)
        is_greeting = self._is_greeting(msg_lower)
        is_internal_state = self._is_internal_state(msg_lower)
        has_vulnerability = vulnerability > 0.3 or intensity > 0.5

        # ── Determine min length ──
        min_words = 60
        if has_vulnerability or is_emotional:
            min_words = 90

        # ── NARRATIVE REQUEST — generate story, don't redirect ──
        if is_narrative_request:
            response = self._handle_narrative(response, msg_lower, user_name)
            logger.info("INITIATIVE_TRIGGERED type=narrative len=%d", len(response.split()))
            return response

        # ── GREETING — expand beyond minimal salute ──
        if is_greeting:
            response = self._handle_greeting(response, user_name, trust)
            min_words = 40
            logger.info("INITIATIVE_TRIGGERED type=greeting len=%d", len(response.split()))

        # ── ANTI-PASSIVE: expand standalone passive phrases ──
        if self._is_passive_standalone(resp_lower):
            response = self._expand_passive(response, detected_emotion, user_name,
                                            is_emotional, is_internal_state, trust)
            logger.info("INITIATIVE_TRIGGERED type=anti_passive")

        # ── EMOTIONAL / INTERNAL STATE: add exploration ──
        if (is_emotional or is_internal_state) and not self._has_question(response):
            response = self._add_exploration(response, detected_emotion, resonance)
            logger.info("INITIATIVE_TRIGGERED type=exploration emotion=%s", detected_emotion)

        # ── RESONANCE INTENSIFICATION ──
        if resonance > 0.5 and (is_emotional or is_internal_state):
            response = self._intensify_with_reflection(response, detected_emotion, resonance)

        # ── CURIOSITY: add question if missing ──
        if curiosity > 0.4 and not self._has_question(response) and not is_narrative_request:
            response = self._add_curiosity_question(response, detected_emotion, msg_lower)
            logger.info("INITIATIVE_TRIGGERED type=curiosity")

        # ── MIN LENGTH ENFORCEMENT ──
        word_count = len(response.split())
        if word_count < min_words:
            response = self._enforce_min_length(response, detected_emotion,
                                                 user_name, min_words, is_emotional,
                                                 is_internal_state, trust, resonance)
            logger.info("MIN_LENGTH_ENFORCED target=%d actual=%d", min_words, len(response.split()))

        # ── ANTI-GENERIC ENDING ──
        response = self._fix_generic_ending(response)

        # ── PROBABILISTIC RELATIONAL OPENING ──
        response = self._maybe_add_opening(response, user_name, intensity, resonance, is_greeting)

        logger.info("EMOTIONAL_INTENSITY_APPLIED words=%d emotion=%s resonance=%.2f",
                     len(response.split()), detected_emotion, resonance)
        return response

    # ═══════════════════════════════════════════════════════════
    # DETECTION HELPERS
    # ═══════════════════════════════════════════════════════════

    def _is_emotional_message(self, msg: str) -> bool:
        return any(kw in msg for kw in EMOTION_KEYWORDS)

    def _is_narrative_request(self, msg: str) -> bool:
        return any(kw in msg for kw in NARRATIVE_KEYWORDS)

    def _is_greeting(self, msg: str) -> bool:
        greetings = ["ciao", "buongiorno", "buonasera", "salve", "hey", "ehi"]
        words = msg.split()
        return len(words) <= 4 and any(g in msg for g in greetings)

    def _is_internal_state(self, msg: str) -> bool:
        return any(kw in msg for kw in INTERNAL_STATE_KEYWORDS)

    def _is_passive_standalone(self, resp: str) -> bool:
        cleaned = resp.strip().rstrip(".").strip().lower()
        for pattern in PASSIVE_STANDALONE:
            p_clean = pattern.strip().rstrip(".").strip().lower()
            if cleaned == p_clean:
                return True
        # Also catch very short responses that are just filler
        if len(resp.split()) <= 5 and not "?" in resp:
            filler_words = {"sono", "qui", "dimmi", "ascolto", "ti", "raccontami", "continua", "pure", "vai", "avanti", "parlami"}
            resp_words = set(cleaned.replace(".", "").replace(",", "").split())
            if resp_words.issubset(filler_words | {""}):
                return True
        return False

    def _has_question(self, text: str) -> bool:
        return "?" in text

    # ═══════════════════════════════════════════════════════════
    # EXPANSION METHODS
    # ═══════════════════════════════════════════════════════════

    def _handle_narrative(self, response: str, msg: str, name: str) -> str:
        """Handle story/narrative requests — generate actual content."""
        story = random.choice(STORY_STARTERS)
        if name:
            return f"{name}, {story}"
        return story

    def _handle_greeting(self, response: str, name: str, trust: float) -> str:
        """Expand greeting beyond minimal salute."""
        if name:
            expansion = random.choice(GREETING_EXPANSIONS_WITH_NAME).format(name=name)
        else:
            expansion = random.choice(GREETING_EXPANSIONS)
        return expansion

    def _expand_passive(self, response: str, emotion: str, name: str,
                        is_emotional: bool, is_internal: bool, trust: float) -> str:
        """Replace passive standalone with substantive content."""
        if is_emotional or is_internal:
            # Emotional context: validate + reflect + explore
            reflections = REFLECTIVE_EXPANSIONS.get(emotion, REFLECTIVE_EXPANSIONS["neutral"])
            questions = EXPLORATIVE_QUESTIONS.get(emotion, EXPLORATIVE_QUESTIONS["neutral"])
            reflection = random.choice(reflections)
            question = random.choice(questions)
            return f"Quello che senti conta. {reflection} {question}"
        else:
            # General context: show presence + open exploration
            openers = [
                "Mi interessa davvero quello che hai da dire. Non devi avere un motivo preciso per parlare — a volte le cose piu' importanti emergono quando ci si lascia andare. Cosa ti passa per la mente in questo momento?",
                "Non devi per forza avere qualcosa di specifico da dirmi. A volte basta stare insieme e vedere cosa emerge. Come ti senti adesso, in questo preciso momento?",
                "Sai, a volte le conversazioni piu' importanti iniziano senza un motivo preciso. C'e' qualcosa che ti sta a cuore ultimamente?",
            ]
            return random.choice(openers)

    def _add_exploration(self, response: str, emotion: str, resonance: float) -> str:
        """Add explorative question to response."""
        questions = EXPLORATIVE_QUESTIONS.get(emotion, EXPLORATIVE_QUESTIONS["neutral"])
        question = random.choice(questions)
        # Don't duplicate if response already ends with question
        if response.rstrip().endswith("?"):
            return response
        return f"{response} {question}"

    def _intensify_with_reflection(self, response: str, emotion: str, resonance: float) -> str:
        """Add reflective depth when resonance is high."""
        reflections = REFLECTIVE_EXPANSIONS.get(emotion, REFLECTIVE_EXPANSIONS["neutral"])
        reflection = random.choice(reflections)
        # Avoid duplication
        if reflection.lower()[:30] in response.lower():
            return response
        # Insert reflection before last sentence if response has multiple sentences
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]
        if len(sentences) >= 2:
            # Insert before last sentence
            sentences.insert(-1, reflection)
            return " ".join(sentences)
        return f"{response} {reflection}"

    def _add_curiosity_question(self, response: str, emotion: str, msg: str) -> str:
        """Add a curiosity-driven question."""
        questions = EXPLORATIVE_QUESTIONS.get(emotion, EXPLORATIVE_QUESTIONS["neutral"])
        question = random.choice(questions)
        return f"{response} {question}"

    def _enforce_min_length(self, response: str, emotion: str, name: str,
                            min_words: int, is_emotional: bool, is_internal: bool,
                            trust: float, resonance: float) -> str:
        """Expand response to meet minimum word count."""

        reflections = list(REFLECTIVE_EXPANSIONS.get(emotion, REFLECTIVE_EXPANSIONS["neutral"]))
        questions = list(EXPLORATIVE_QUESTIONS.get(emotion, EXPLORATIVE_QUESTIONS["neutral"]))
        random.shuffle(reflections)
        random.shuffle(questions)

        presence_pool = [
            "Sono qui con te, senza fretta. Possiamo parlare di quello che vuoi, quando vuoi.",
            "Non c'e' fretta. Possiamo restare qui quanto serve.",
            "Prenditi il tempo che ti serve. Sono qui e non vado da nessuna parte.",
            "Quello che senti e' importante, e merita di essere ascoltato con attenzione.",
        ]

        depth_pool = [
            "A volte le parole non bastano per esprimere tutto quello che sentiamo dentro, e va bene cosi'. L'importante e' che tu sappia che qui c'e' spazio per tutto.",
            "Ogni persona porta con se' un mondo intero di esperienze, emozioni, ricordi. E ogni conversazione e' un'occasione per scoprire qualcosa di nuovo su quel mondo.",
            "Non devi avere tutte le risposte adesso. A volte il primo passo e' semplicemente permettersi di sentire quello che c'e', senza giudicarlo.",
        ]

        parts = [response]
        used = set()

        # Add reflections until we approach target
        for r in reflections:
            if len(" ".join(parts).split()) >= min_words:
                break
            if r.lower()[:25] not in " ".join(parts).lower():
                parts.append(r)
                used.add(r[:25])

        # Add question if missing
        if len(" ".join(parts).split()) < min_words and not self._has_question(" ".join(parts)):
            parts.append(questions[0] if questions else "Come ti senti in questo momento?")

        # Add presence
        for p in presence_pool:
            if len(" ".join(parts).split()) >= min_words:
                break
            if p[:20] not in " ".join(parts):
                parts.append(p)

        # Add depth
        for d in depth_pool:
            if len(" ".join(parts).split()) >= min_words:
                break
            if d[:20] not in " ".join(parts):
                parts.append(d)

        result = " ".join(parts)
        return result

    def _fix_generic_ending(self, response: str) -> str:
        """Remove generic invitation endings."""
        generic_endings = [
            "dimmi pure.", "raccontami.", "ti ascolto.",
            "vai avanti.", "continua pure.", "dimmi.",
        ]
        stripped = response.rstrip()
        for ending in generic_endings:
            if stripped.lower().endswith(ending):
                # Only remove if the response is long enough without it
                without = stripped[:-(len(ending))].rstrip()
                if len(without.split()) >= 30:
                    return without
        return response


    # ═══════════════════════════════════════════════════════════
    # PROBABILISTIC RELATIONAL OPENING
    # ═══════════════════════════════════════════════════════════

    def _maybe_add_opening(self, response: str, name: str, intensity: float,
                            resonance: float, is_greeting: bool) -> str:
        """
        Aggiunge apertura relazionale probabilistica.
        - probability = 0.35 base
        - intensity < 0.4 → NESSUN opening
        - intensity > 0.7 → opening piu' caldo
        - No ripetizione ultime 3
        """
        # Greetings already have their own opening
        if is_greeting:
            return response

        # Low intensity → skip opening entirely
        if intensity < 0.4:
            logger.info("RESPONSE_OPENING_SKIPPED intensity=%.2f", intensity)
            return response

        # Roll probability
        roll = random.random()
        if roll > RELATIONAL_OPENING_PROBABILITY:
            logger.info("RESPONSE_OPENING_SKIPPED probability=%.2f roll=%.2f", RELATIONAL_OPENING_PROBABILITY, roll)
            return response

        # Select pool based on intensity
        if intensity > 0.7:
            pool = WARM_OPENINGS_WITH_NAME if name else WARM_OPENINGS_NO_NAME
        else:
            pool = RELATIONAL_OPENINGS_WITH_NAME if name else RELATIONAL_OPENINGS_NO_NAME

        # Filter out recently used
        available = [o for o in pool if o not in self._recent_openings]
        if not available:
            available = pool  # All used recently, reset

        opening = random.choice(available)

        # Format with name if needed
        if name and "{name}" in opening:
            opening = opening.format(name=name)

        # Don't add opening if response already starts with name or similar
        resp_start = response[:30].lower()
        if name and name.lower() in resp_start:
            logger.info("RESPONSE_OPENING_SKIPPED already_has_name")
            return response

        # Store in memory buffer
        self._recent_openings.append(opening)

        # Prepend opening — lowercase first char of response if it was uppercase
        if response and response[0].isupper():
            result = f"{opening}{response[0].lower()}{response[1:]}"
        else:
            result = f"{opening}{response}"

        logger.info('RESPONSE_OPENING selected="%s" probability=%.2f intensity=%.2f',
                     opening.strip()[:40], RELATIONAL_OPENING_PROBABILITY, intensity)
        return result


# Singleton
emotional_intensity_engine = EmotionalIntensityEngine()
