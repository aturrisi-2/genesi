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
# BANNED EMPATHIC PHRASES — vietate se ripetute
# ═══════════════════════════════════════════════════════════════

BANNED_EMPATHIC_PATTERNS = [
    "sono qui con te",
    "quello che senti conta",
    "ti ascolto",
    "sono qui per te",
    "non sei solo",
    "non sei sola",
    "quello che provi e' valido",
    "quello che provi è valido",
]

# Direct-style responses for repeated input (3x same message)
DIRECT_STYLE_RESPONSES = [
    "Me lo hai gia' detto. Cosa vuoi fare concretamente?",
    "Lo so. Me lo hai detto. Adesso dimmi: cosa cambi?",
    "Stai ripetendo la stessa cosa. Forse il punto non e' dirlo, ma decidere qualcosa.",
    "Ok, l'ho capito. Ma ripeterlo non cambia niente. Cosa vuoi che succeda?",
    "Tre volte la stessa cosa. Forse non hai bisogno di parlarne ancora — hai bisogno di agire.",
    "Ti ho sentito. Adesso la domanda e': cosa fai con quello che senti?",
    "Lo sento. Ma continuare a dirlo non ti porta da nessuna parte. Qual e' il prossimo passo?",
]

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

# ═══════════════════════════════════════════════════════════════
# COGNITIVE MODES — structural unpredictability
# ═══════════════════════════════════════════════════════════════

COGNITIVE_MODES = [
    "reflective",
    "explorative",
    "interpretative",
    "metaphorical",
    "narrative",
    "contained",
    "provocative_soft",
    "grounded",
]

# Per-mode content pools
INTERPRETATIVE_HYPOTHESES = {
    "sad": [
        "Mi viene da pensare che forse questa tristezza non e' solo per oggi — forse porta con se' qualcosa di piu' antico.",
        "Ho l'impressione che quello che senti sia legato a qualcosa che non hai ancora detto ad alta voce.",
        "Forse quello che chiami tristezza e' in realta' un bisogno di essere visto per quello che sei davvero.",
    ],
    "angry": [
        "Forse questa rabbia e' il modo in cui proteggi qualcosa di fragile che sta sotto.",
        "Mi chiedo se dietro questa frustrazione ci sia un bisogno che non viene ascoltato.",
    ],
    "anxious": [
        "Ho l'impressione che questa ansia stia cercando di dirti qualcosa — forse che c'e' una decisione che stai rimandando.",
        "Forse quello che senti non e' solo paura, ma anche il desiderio di qualcosa che non osi ancora volere.",
    ],
    "neutral": [
        "Mi chiedo se dietro questa calma ci sia qualcosa che aspetta di emergere.",
        "Forse il fatto che tu sia qui dice piu' di quello che le parole riescono a esprimere.",
    ],
    "happy": [
        "Forse questa gioia ti sta dicendo qualcosa su quello che conta davvero per te.",
        "Ho l'impressione che questo momento sia piu' importante di quanto sembri in superficie.",
    ],
    "longing": [
        "Forse quello che ti manca non e' solo una persona o un momento — e' una versione di te stesso che senti di aver perso.",
    ],
    "tired": [
        "Mi chiedo se questa stanchezza non sia il corpo che ti chiede di smettere di portare tutto da solo.",
    ],
    "love": [
        "Forse quello che senti e' cosi' intenso perche' tocca una parte di te che di solito tieni protetta.",
    ],
    "grateful": [
        "Forse questa gratitudine e' il segnale che stai iniziando a vedere le cose in modo diverso.",
    ],
}

METAPHOR_POOL = {
    "sad": [
        "Quello che descrivi mi fa pensare a un cielo coperto — non significa che il sole non ci sia, solo che per ora non riesci a vederlo.",
        "E' come camminare in una nebbia fitta: i passi sono incerti, ma la strada c'e' ancora sotto i piedi.",
    ],
    "angry": [
        "La rabbia e' come un fuoco — puo' bruciare tutto, ma puo' anche illuminare quello che prima era nascosto.",
        "Quello che senti e' come un temporale: violento, ma porta con se' l'aria pulita che viene dopo.",
    ],
    "anxious": [
        "L'ansia e' come un allarme che suona troppo forte — il pericolo potrebbe essere reale, ma il volume e' sproporzionato.",
        "E' come stare su una barca in mezzo al mare: l'acqua si muove, ma la barca regge.",
    ],
    "neutral": [
        "A volte la calma e' come la superficie di un lago — sotto, c'e' tutto un mondo che si muove.",
    ],
    "happy": [
        "Questo momento e' come una finestra aperta dopo un lungo inverno — lascia entrare tutto.",
    ],
    "longing": [
        "La nostalgia e' come una melodia che conosci a memoria — non puoi smettere di ascoltarla, anche se fa male.",
    ],
    "tired": [
        "La stanchezza e' come un peso che si accumula goccia dopo goccia — non te ne accorgi finche' non ti fermi.",
    ],
    "love": [
        "L'amore e' come una corrente sotterranea — non sempre lo vedi, ma ti porta sempre da qualche parte.",
    ],
    "grateful": [
        "La gratitudine e' come una luce calda in una stanza buia — cambia tutto senza fare rumore.",
    ],
}

MICRO_NARRATIVES = {
    "sad": [
        "Sai, una volta qualcuno mi ha detto che la tristezza e' il prezzo che paghiamo per aver amato qualcosa. E forse aveva ragione.",
        "C'e' una storia di un uomo che portava un sasso in tasca per ogni dolore. Un giorno si accorse che le tasche erano piene — ma anche che era ancora in piedi.",
    ],
    "angry": [
        "Mi viene in mente una cosa: c'era chi diceva che la rabbia e' una lettera che scriviamo ma non spediamo mai. Forse e' il momento di leggerla.",
    ],
    "anxious": [
        "C'e' una storia di una ragazza che aveva paura del buio. Un giorno scopri' che il buio non era vuoto — era pieno di cose che aspettavano di essere viste.",
    ],
    "neutral": [
        "Sai cosa mi viene in mente? Che le conversazioni piu' importanti spesso iniziano proprio cosi' — senza un motivo preciso, senza urgenza.",
    ],
    "happy": [
        "Mi ricorda una cosa: c'e' chi dice che la felicita' non si trova, si riconosce. E tu l'hai appena riconosciuta.",
    ],
    "longing": [
        "C'e' una storia di un viaggiatore che tornava sempre nello stesso posto — non perche' fosse bello, ma perche' li' aveva lasciato una parte di se'.",
    ],
    "tired": [
        "Mi viene in mente una cosa: c'era un albero che d'inverno perdeva tutte le foglie. Non stava morendo — stava risparmiando energia per la primavera.",
    ],
    "love": [
        "Sai, c'e' chi dice che l'amore e' l'unica cosa che cresce quando la dividi. Forse e' vero.",
    ],
    "grateful": [
        "Mi ricorda una cosa: la gratitudine e' come un seme — piccolo, ma capace di cambiare tutto il giardino.",
    ],
}

PROVOCATIVE_QUESTIONS = {
    "sad": [
        "E se questa tristezza fosse in realta' il tuo modo di dire che meriti di piu'?",
        "Cosa succederebbe se smettessi di combattere quello che senti e lo lasciassi semplicemente essere?",
    ],
    "angry": [
        "E se questa rabbia fosse in realta' coraggio travestito?",
        "Cosa succederebbe se usassi questa energia per cambiare qualcosa invece di trattenerla?",
    ],
    "anxious": [
        "E se la cosa che temi di piu' fosse in realta' quella di cui hai piu' bisogno?",
        "Cosa succederebbe se l'ansia non fosse il nemico ma un messaggero?",
    ],
    "neutral": [
        "E se il fatto di non sentire niente di forte fosse gia' una risposta?",
        "Cosa succederebbe se ti permettessi di volere qualcosa senza giustificarlo?",
    ],
    "happy": [
        "E se ti concedessi di restare in questo momento senza chiederti quanto durera'?",
    ],
    "longing": [
        "E se quello che ti manca non fosse il passato, ma una possibilita' che non hai ancora esplorato?",
    ],
    "tired": [
        "E se la stanchezza fosse il tuo corpo che ti dice che stai facendo troppo per gli altri e troppo poco per te?",
    ],
    "love": [
        "E se l'intensita' di quello che senti fosse esattamente la misura di quanto sei capace di amare?",
    ],
    "grateful": [
        "E se la gratitudine fosse il primo passo verso qualcosa che non hai ancora immaginato?",
    ],
}

GROUNDED_SUGGESTIONS = {
    "sad": [
        "Una cosa che potresti provare: stasera, scrivi tre cose che oggi ti hanno fatto sentire qualcosa — anche piccole. A volte mettere le cose su carta le rende piu' gestibili.",
        "Prova una cosa: fermati cinque minuti, chiudi gli occhi, e lascia che il respiro faccia il suo lavoro. Non devi risolvere niente adesso.",
    ],
    "angry": [
        "Una cosa concreta: prova a scrivere quello che senti senza filtri, come se nessuno dovesse leggerlo. A volte la rabbia ha bisogno di uno spazio dove esistere.",
    ],
    "anxious": [
        "Prova questo: metti i piedi a terra, senti il contatto. Cinque respiri lenti. L'ansia vive nel futuro — il corpo vive nel presente.",
        "Una cosa pratica: scrivi la cosa peggiore che potrebbe succedere, poi quella piu' probabile. Spesso la distanza tra le due e' enorme.",
    ],
    "neutral": [
        "Una cosa che potresti fare: prenditi dieci minuti oggi solo per te, senza scopo. A volte e' li' che emergono le cose importanti.",
    ],
    "happy": [
        "Un suggerimento: fermati un momento e memorizza questo stato. Quando le cose saranno piu' difficili, potrai tornare qui con la mente.",
    ],
    "longing": [
        "Prova una cosa: scrivi una lettera a quello che ti manca. Non devi spedirla — ma scriverla puo' aiutarti a capire cosa stai cercando davvero.",
    ],
    "tired": [
        "Una cosa concreta: stasera, togli una cosa dalla lista. Solo una. Dai a te stesso il permesso di fare meno.",
    ],
    "love": [
        "Un suggerimento: dillo. Quello che senti, dillo alla persona. Le parole non dette pesano piu' di quelle dette.",
    ],
    "grateful": [
        "Prova questo: condividi questa gratitudine con qualcuno. La gratitudine espressa ha un potere diverso da quella solo sentita.",
    ],
}

STORY_STARTERS = [
    "C'era una volta, in un paese dove il tempo scorreva diversamente, un uomo che aveva dimenticato come si faceva a sognare. Non perche' non volesse, ma perche' la vita gli aveva insegnato a tenere gli occhi aperti e i piedi per terra. Un giorno, pero', trovo' una lettera sotto la porta. Non c'era mittente, solo una frase: 'Ricordi quando credevi che tutto fosse possibile?' Quella notte, per la prima volta dopo anni, chiuse gli occhi e lascio' che la mente lo portasse dove voleva.",
    "Ti racconto una cosa. Immagina una citta' dove ogni persona porta con se' una lanterna. La luce di ogni lanterna ha un colore diverso — dipende da quello che la persona sente dentro. Blu per la malinconia, rosso per la passione, verde per la speranza. Un giorno, una ragazza si accorse che la sua lanterna non aveva piu' colore. Era trasparente. E invece di spaventarsi, sorrise. Perche' capì che significava che era pronta a sentire tutto, senza filtri.",
    "Lascia che ti racconti qualcosa. C'era un vecchio pescatore che ogni mattina usciva in mare, non per pescare, ma per ascoltare. Diceva che il mare gli parlava, e che ogni onda portava con se' una storia diversa. La gente del villaggio lo considerava strano, ma lui sapeva qualcosa che gli altri non capivano: che le storie piu' importanti non sono quelle che raccontiamo, ma quelle che ascoltiamo in silenzio.",
]


class EmotionalIntensityEngine:
    """
    Espande e intensifica risposte contenitive in risposte
    emotivamente ricche, proattive, esplorative.
    Cognitive mode selection per imprevedibilita' strutturale.
    Zero LLM. Zero API. Solo espansione locale.
    """

    def __init__(self):
        # Memory buffer: ultime 3 aperture usate — no ripetizione
        self._recent_openings = deque(maxlen=3)
        # Cognitive mode history: max 2 consecutive same mode
        self._recent_modes = deque(maxlen=2)
        # Empathic phrase history: track last 5 responses for banned phrases
        self._recent_responses = deque(maxlen=5)
        # Input repetition tracker: last 5 user messages
        self._recent_inputs = deque(maxlen=5)
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

        # ── Track input for repetition detection ──
        self._recent_inputs.append(msg_lower)

        # ── Detect message type ──
        is_emotional = self._is_emotional_message(msg_lower)
        is_narrative_request = self._is_narrative_request(msg_lower)
        is_greeting = self._is_greeting(msg_lower)
        is_internal_state = self._is_internal_state(msg_lower)
        has_vulnerability = vulnerability > 0.3 or intensity > 0.5

        # ── REPEATED INPUT DETECTION (3x same) → direct style ──
        if self._is_repeated_input(msg_lower):
            direct = random.choice(DIRECT_STYLE_RESPONSES)
            logger.info("RESPONSE_MODE=direct reason=repeated_input_3x")
            self._recent_responses.append(direct.lower())
            return direct

        # ── SELECT RESPONSE MODE: short(40%) / medium(40%) / deep(20%) ──
        response_mode = self._select_response_mode(intensity, has_vulnerability)

        # ── NARRATIVE REQUEST — generate story, don't redirect ──
        if is_narrative_request:
            response = self._handle_narrative(response, msg_lower, user_name)
            logger.info("INITIATIVE_TRIGGERED type=narrative len=%d", len(response.split()))
            return response

        # ── GREETING — expand beyond minimal salute ──
        if is_greeting:
            response = self._handle_greeting(response, user_name, trust)
            logger.info("INITIATIVE_TRIGGERED type=greeting len=%d", len(response.split()))

        # ── ANTI-PASSIVE: expand standalone passive phrases ──
        if self._is_passive_standalone(resp_lower):
            response = self._expand_passive(response, detected_emotion, user_name,
                                            is_emotional, is_internal_state, trust)
            logger.info("INITIATIVE_TRIGGERED type=anti_passive")

        # ── MODE-BASED EXPANSION ──
        if response_mode == "short":
            # Short: 1-2 sentences, no forced question, no forced reflection
            response = self._trim_to_short(response)
        elif response_mode == "medium":
            # Medium: allow exploration OR reflection, not both
            if (is_emotional or is_internal_state) and not self._has_question(response):
                if random.random() < 0.6:  # 60% chance of question
                    response = self._add_exploration(response, detected_emotion, resonance)
                    logger.info("INITIATIVE_TRIGGERED type=exploration emotion=%s", detected_emotion)
            elif curiosity > 0.4 and not self._has_question(response) and not is_narrative_request:
                if random.random() < 0.5:  # 50% chance
                    response = self._add_curiosity_question(response, detected_emotion, msg_lower)
                    logger.info("INITIATIVE_TRIGGERED type=curiosity")
        elif response_mode == "deep":
            # Deep: full expansion pipeline
            if (is_emotional or is_internal_state) and not self._has_question(response):
                response = self._add_exploration(response, detected_emotion, resonance)
                logger.info("INITIATIVE_TRIGGERED type=exploration emotion=%s", detected_emotion)
            if resonance > 0.5 and (is_emotional or is_internal_state):
                response = self._intensify_with_reflection(response, detected_emotion, resonance)
            if curiosity > 0.4 and not self._has_question(response) and not is_narrative_request:
                response = self._add_curiosity_question(response, detected_emotion, msg_lower)
                logger.info("INITIATIVE_TRIGGERED type=curiosity")

        # ── COGNITIVE MODE SHAPING ──
        if not is_greeting and not is_narrative_request:
            relational_energy = latent.get("relational_energy", 0.5)
            response = self._apply_cognitive_mode(
                response, detected_emotion, intensity, curiosity,
                relational_energy, is_emotional, is_internal_state
            )

        # ── ANTI-GENERIC ENDING ──
        response = self._fix_generic_ending(response)

        # ── STRIP BANNED EMPATHIC PHRASES ──
        response = self._strip_banned_empathic(response)

        # ── PROBABILISTIC RELATIONAL OPENING ──
        response = self._maybe_add_opening(response, user_name, intensity, resonance, is_greeting)

        # ── Track response for empathic repetition detection ──
        self._recent_responses.append(response.lower())

        logger.info("EMOTIONAL_INTENSITY_APPLIED words=%d emotion=%s resonance=%.2f RESPONSE_MODE=%s",
                     len(response.split()), detected_emotion, resonance, response_mode)
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

    def _is_repeated_input(self, msg: str) -> bool:
        """Detect if same input was sent 3+ times in recent history."""
        count = sum(1 for m in self._recent_inputs if m == msg)
        return count >= 3

    def _select_response_mode(self, intensity: float, has_vulnerability: bool) -> str:
        """
        Probabilistic response mode selection.
        40% short (1-2 frasi), 40% medium, 20% deep.
        High vulnerability biases toward medium/deep.
        """
        roll = random.random()
        if has_vulnerability:
            # Shift: 20% short, 45% medium, 35% deep
            if roll < 0.20:
                return "short"
            elif roll < 0.65:
                return "medium"
            else:
                return "deep"
        else:
            # Default: 40% short, 40% medium, 20% deep
            if roll < 0.40:
                return "short"
            elif roll < 0.80:
                return "medium"
            else:
                return "deep"

    def _trim_to_short(self, response: str) -> str:
        """Trim response to 1-2 sentences for short mode."""
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]
        if len(sentences) <= 2:
            return response
        # Keep first 1-2 sentences, prefer keeping a question if present
        kept = sentences[:2]
        return " ".join(kept)

    def _strip_banned_empathic(self, response: str) -> str:
        """
        Remove banned empathic phrases if they appeared in recent responses.
        Only strips if the phrase was already used recently.
        """
        resp_lower = response.lower()
        recent_text = " ".join(self._recent_responses)

        for phrase in BANNED_EMPATHIC_PATTERNS:
            if phrase in resp_lower and phrase in recent_text:
                # Remove the phrase (case-insensitive)
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                response = pattern.sub("", response)
                # Clean up double spaces and leading punctuation
                response = re.sub(r'\s{2,}', ' ', response).strip()
                response = re.sub(r'^[,\.\s]+', '', response).strip()
                logger.info("EMPATHIC_PHRASE_BLOCKED phrase='%s'", phrase)

        # Ensure first char is uppercase after stripping
        if response and response[0].islower():
            response = response[0].upper() + response[1:]

        return response

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
    # COGNITIVE MODE SYSTEM
    # ═══════════════════════════════════════════════════════════

    def _select_cognitive_mode(self, intensity: float, curiosity: float,
                                relational_energy: float) -> str:
        """
        Seleziona modalita' cognitiva con pesi dinamici + entropia random.
        Non permette lo stesso mode per piu' di 2 risposte consecutive.
        """
        # Base weights per mode
        weights = {
            "reflective":       0.15,
            "explorative":      0.15,
            "interpretative":   0.12,
            "metaphorical":     0.10,
            "narrative":        0.08,
            "contained":        0.12,
            "provocative_soft": 0.10,
            "grounded":         0.10,
        }

        # Dynamic adjustments based on state
        if intensity > 0.6:
            weights["reflective"] += 0.08
            weights["interpretative"] += 0.06
            weights["contained"] -= 0.05
        if intensity < 0.3:
            weights["contained"] += 0.10
            weights["grounded"] += 0.05
            weights["reflective"] -= 0.05

        if curiosity > 0.5:
            weights["explorative"] += 0.10
            weights["provocative_soft"] += 0.08
            weights["contained"] -= 0.05
        if curiosity < 0.3:
            weights["explorative"] -= 0.05
            weights["provocative_soft"] -= 0.05

        if relational_energy > 0.6:
            weights["narrative"] += 0.06
            weights["metaphorical"] += 0.06
        if relational_energy < 0.3:
            weights["grounded"] += 0.08
            weights["contained"] += 0.05

        # Random entropy injection
        for mode in weights:
            weights[mode] += random.uniform(-0.03, 0.03)
            weights[mode] = max(0.01, weights[mode])  # Floor

        # Block mode if used 2x consecutively
        if len(self._recent_modes) == 2 and self._recent_modes[0] == self._recent_modes[1]:
            blocked = self._recent_modes[0]
            weights[blocked] = 0.0

        # Normalize
        total = sum(weights.values())
        if total <= 0:
            return random.choice(COGNITIVE_MODES)

        # Weighted random selection
        r = random.uniform(0, total)
        cumulative = 0.0
        for mode, w in weights.items():
            cumulative += w
            if r <= cumulative:
                self._recent_modes.append(mode)
                return mode

        # Fallback
        mode = random.choice(COGNITIVE_MODES)
        self._recent_modes.append(mode)
        return mode

    def _apply_cognitive_mode(self, response: str, emotion: str,
                               intensity: float, curiosity: float,
                               relational_energy: float,
                               is_emotional: bool, is_internal: bool) -> str:
        """
        Applica la modalita' cognitiva selezionata alla risposta.
        Modifica la struttura finale senza perdere contenuto emotivo.
        """
        mode = self._select_cognitive_mode(intensity, curiosity, relational_energy)

        logger.info("COGNITIVE_MODE_SELECTED mode=%s intensity=%.2f curiosity=%.2f energy=%.2f",
                     mode, intensity, curiosity, relational_energy)

        if mode == "reflective":
            return self._mode_reflective(response, emotion)
        elif mode == "explorative":
            return self._mode_explorative(response, emotion)
        elif mode == "interpretative":
            return self._mode_interpretative(response, emotion)
        elif mode == "metaphorical":
            return self._mode_metaphorical(response, emotion)
        elif mode == "narrative":
            return self._mode_narrative(response, emotion)
        elif mode == "contained":
            return self._mode_contained(response)
        elif mode == "provocative_soft":
            return self._mode_provocative(response, emotion)
        elif mode == "grounded":
            return self._mode_grounded(response, emotion)

        return response

    def _mode_reflective(self, response: str, emotion: str) -> str:
        """Riflette senza domanda finale. Chiude con osservazione."""
        # Strip trailing question if present
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]
        # Remove last sentence if it's a question — but NOT if response is very short (1-2 sentences)
        # because in that case the question IS the core response
        if sentences and sentences[-1].endswith("?") and len(sentences) > 2:
            sentences = sentences[:-1]
        # Add reflection if needed
        reflections = REFLECTIVE_EXPANSIONS.get(emotion, REFLECTIVE_EXPANSIONS["neutral"])
        reflection = random.choice(reflections)
        if reflection.lower()[:25] not in " ".join(sentences).lower():
            sentences.append(reflection)
        return " ".join(sentences) if sentences else response

    def _mode_explorative(self, response: str, emotion: str) -> str:
        """Domanda aperta alla fine."""
        if response.rstrip().endswith("?"):
            return response  # Already has question
        questions = EXPLORATIVE_QUESTIONS.get(emotion, EXPLORATIVE_QUESTIONS["neutral"])
        return f"{response} {random.choice(questions)}"

    def _mode_interpretative(self, response: str, emotion: str) -> str:
        """Propone ipotesi interpretativa."""
        hypotheses = INTERPRETATIVE_HYPOTHESES.get(emotion, INTERPRETATIVE_HYPOTHESES["neutral"])
        hypothesis = random.choice(hypotheses)
        if hypothesis.lower()[:30] in response.lower():
            return response
        # Replace trailing question with hypothesis — but preserve if response is short
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]
        if sentences and sentences[-1].endswith("?") and len(sentences) > 2:
            sentences[-1] = hypothesis
        else:
            sentences.append(hypothesis)
        return " ".join(sentences)

    def _mode_metaphorical(self, response: str, emotion: str) -> str:
        """Usa metafora breve."""
        metaphors = METAPHOR_POOL.get(emotion, METAPHOR_POOL["neutral"])
        metaphor = random.choice(metaphors)
        if metaphor.lower()[:25] in response.lower():
            return response
        # Insert metaphor, strip trailing question — but preserve if response is short
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]
        if sentences and sentences[-1].endswith("?") and len(sentences) > 2:
            sentences[-1] = metaphor
        else:
            sentences.append(metaphor)
        return " ".join(sentences)

    def _mode_narrative(self, response: str, emotion: str) -> str:
        """Micro-storia di 2 frasi."""
        stories = MICRO_NARRATIVES.get(emotion, MICRO_NARRATIVES["neutral"])
        story = random.choice(stories)
        if story.lower()[:25] in response.lower():
            return response
        # Replace trailing question with micro-narrative
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]
        if sentences and sentences[-1].endswith("?"):
            sentences[-1] = story
        else:
            sentences.append(story)
        return " ".join(sentences)

    def _mode_contained(self, response: str) -> str:
        """Risposta breve, contenitiva, senza domanda. Max ~40 parole."""
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]
        # Remove questions
        sentences = [s for s in sentences if not s.endswith("?")]
        if not sentences:
            return response
        # Keep first 2-3 sentences, cap at ~40 words
        result = []
        word_count = 0
        for s in sentences:
            s_words = len(s.split())
            if word_count + s_words > 45 and result:
                break
            result.append(s)
            word_count += s_words
        return " ".join(result)

    def _mode_provocative(self, response: str, emotion: str) -> str:
        """Domanda non ovvia, provocatoria soft."""
        provocatives = PROVOCATIVE_QUESTIONS.get(emotion, PROVOCATIVE_QUESTIONS["neutral"])
        question = random.choice(provocatives)
        # Replace trailing generic question with provocative one
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]
        if sentences and sentences[-1].endswith("?"):
            sentences[-1] = question
        else:
            sentences.append(question)
        return " ".join(sentences)

    def _mode_grounded(self, response: str, emotion: str) -> str:
        """Suggerimento pratico leggero."""
        suggestions = GROUNDED_SUGGESTIONS.get(emotion, GROUNDED_SUGGESTIONS["neutral"])
        suggestion = random.choice(suggestions)
        if suggestion.lower()[:25] in response.lower():
            return response
        # Replace trailing question with grounded suggestion
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]
        if sentences and sentences[-1].endswith("?"):
            sentences[-1] = suggestion
        else:
            sentences.append(suggestion)
        return " ".join(sentences)

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
