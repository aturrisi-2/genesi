"""
LLM SERVICE - Genesi Core v3 (cost_optimized_v1)
Servizio LLM con model_selector(), rate limit protection, auto-downgrade.

Default: gpt-4o (cost-optimized)
Claude Opus: SOLO per deep analysis esplicito, narrativa lunga, analisi psicologica complessa.
Rate limit: retry con backoff esponenziale, downgrade automatico, fallback deterministico.
"""

import os
import asyncio
import logging
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from openai import AsyncOpenAI, RateLimitError, APIError, APIConnectionError
from core.log import log

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# AUTO EVOLUTION INTEGRATION
# ═══════════════════════════════════════════════════════════════

from core.evolution_state_manager import get_evolution_state_manager

def load_tuning_state() -> Dict[str, Any]:
    """Carica stato tuning da current_state.json transazionale."""
    try:
        state_manager = get_evolution_state_manager()
        current_state = state_manager.load_current_state()
        return current_state.get("parameters", _get_default_tuning_state())
    except Exception as e:
        logger.error(f"❌ Failed to load tuning state: {e}")
        return _get_default_tuning_state()

def _get_default_tuning_state() -> Dict[str, Any]:
    """Stato tuning di fallback."""
    return {
        "supportive_intensity": 0.5,
        "attuned_intensity": 0.5,
        "confrontational_intensity": 0.5,
        "max_questions_per_response": 1,
        "repetition_penalty_weight": 1.0,
        "last_snapshot": None,
        "last_tuning_cycle": None
    }

# Carica stato tuning globale
_TUNING_STATE = load_tuning_state()

# 🔵 DEBUG OBBLIGATORIO - tuning state caricato
print(f"LOADED_TUNING_STATE {_TUNING_STATE}")

def reload_tuning_state() -> Dict[str, Any]:
    """Ricarica stato tuning dopo aggiornamenti."""
    global _TUNING_STATE
    _TUNING_STATE = load_tuning_state()
    print(f"RELOADED_TUNING_STATE {_TUNING_STATE}")
    return _TUNING_STATE

# ═══════════════════════════════════════════════════════════════
# MODEL CONFIGURATION — cost-optimized defaults
# ═══════════════════════════════════════════════════════════════

LLM_DEFAULT_MODEL = "gpt-4o"
LLM_FALLBACK_MODEL = "gpt-4o-mini"
LLM_DEEP_MODEL = "claude-opus"

# Trigger per upgrade a Claude Opus (deep analysis)
DEEP_ANALYSIS_TRIGGERS = [
    "analisi profonda",
    "deep psychological analysis"
]


def model_selector(message: str, route: str = "general") -> str:
    """
    Selects the appropriate model based on message content and route.
    """
    # Default to primary model
    selected_model = LLM_DEFAULT_MODEL
    reason = "default"

    # Use Claude Opus for deep analysis triggers
    if any(trigger in message.lower() for trigger in DEEP_ANALYSIS_TRIGGERS):
        selected_model = LLM_DEEP_MODEL
        reason = "deep analysis trigger"

    logger.info("LLM_MODEL_SELECTED=%s reason=%s", selected_model, reason)
    return selected_model


class LLMService:
    """
    LLM Service v3 — Cost-optimized con rate limit protection.
    Default: gpt-4o. Auto-downgrade su rate limit. Fallback deterministico.
    """

    def __init__(self):
        self.client = AsyncOpenAI()
        self.default_model = LLM_DEFAULT_MODEL
        self.fallback_model = LLM_FALLBACK_MODEL
        _api_key = os.environ.get("OPENAI_API_KEY", "")
        if not _api_key or _api_key.startswith("sk-test"):
            logger.warning("LLM_SERVICE: OPENAI_API_KEY missing or test-only")
        log("LLM_SERVICE_ACTIVE")
        logger.info("LLM_ENGINE_DEFAULT=%s ARCHITECTURE_MODE=cost_optimized_v1", self.default_model)
        
        # 🆕 Relational State Engine
        from core.relational_state_engine import RelationalStateEngine
        self.relational_engine = RelationalStateEngine()
    
    def _load_adaptive_prompt(self) -> str:
        """
        Carica il prompt adattivo da lab/global_prompt.json.
        
        Returns:
            str: System prompt adattivo o stringa vuota se non disponibile
        """
        try:
            prompt_file = Path("lab/global_prompt.json")
            if not prompt_file.exists():
                return ""
            
            with open(prompt_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            system_prompt = data.get("system_prompt", "")
            if system_prompt:
                return system_prompt.strip()
            else:
                return ""
                
        except Exception as e:
            logger.warning("ADAPTIVE_PROMPT_LOAD_FAIL error=%s", str(e))
            return ""

    async def generate_response(self, message: str, route: str = "general") -> str:
        """
        Genera risposta LLM con model_selector e rate limit protection.
        Chain: selected_model -> retry backoff -> downgrade -> deterministic fallback.
        """
        model = model_selector(message, route)
        technical_prompt = f"""
Sei Genesi, assistente tecnico esperto.
Rispondi in modo chiaro, tecnico, preciso.
Focus su: programmazione, architettura, debugging, spiegazioni tecniche.
Usa esempi pratici quando possibile.

Domanda: {message}
"""
        result = await self._call_with_protection(model, technical_prompt, message, route=route)
        if result:
            return result

        logger.error("LLM_SERVICE_ALL_FAIL route=%s — activating deterministic fallback", route)
        return self._deterministic_fallback(message, route)

    async def generate_response_with_context(self, message: str, user_profile: dict, user_id: str) -> str:
        """
        Genera risposta LLM con contesto utente e rate limit protection.
        """
        if not user_id:
            raise ValueError("LLM service received empty user_id")

        model = model_selector(message, route="technical")
        context = self._build_user_context(user_profile)
        technical_prompt = f"""
Sei Genesi, assistente tecnico esperto.
Rispondi in modo chiaro, tecnico, preciso.
Focus su: programmazione, architettura, debugging, spiegazioni tecniche.
Usa esempi pratici quando possibile.

CONTESTO UTENTE:
{context}

Domanda: {message}
"""
        result = await self._call_with_protection(model, technical_prompt, message,
                                                   user_id=user_id, route="technical")
        if result:
            return result

        logger.error("LLM_SERVICE_ALL_FAIL user=%s — activating deterministic fallback", user_id)
        return self._deterministic_fallback(message, "technical", user_id)

    async def generate_with_context(self, context: dict, user_id: str = "",
                                     route: str = "relational") -> str:
        """
        Genera risposta LLM con contesto strutturato dalla memoria.
        Il context deve contenere \'summary\' e \'current_message\' (da ContextAssembler).
        Rate limit protection con auto-downgrade.

        Raises:
            RuntimeError se context[\'summary\'] e\' vuoto.
        """
        summary = context.get("summary", "")
        if not summary or not summary.strip():
            raise RuntimeError(f"LLM_CONTEXT_EMPTY user={user_id} — generate_with_context received empty summary")

        message = context.get("current_message", "")
        if not message:
            raise ValueError("LLM_NO_MESSAGE — generate_with_context received empty current_message")

        # Build conversation context with chat history if user_id available
        from core.context_assembler import build_conversation_context
        from core.context_signal_analyzer import ContextSignalAnalyzer
        profile = context.get("profile", {})
        
        # 🆕 Context Signal Analysis + Emotional Pattern Detection
        behavior_instructions = ""
        if user_id:
            try:
                from core.chat_memory import get_chat_memory
                chat_memory = get_chat_memory()
                chat_history = chat_memory.get_recent_messages(user_id, limit=10)
                # Estrai solo i messaggi utente
                recent_user_messages = [msg.get("content", "") for msg in chat_history if msg.get("role") == "user"]
                
                if recent_user_messages:
                    analyzer = ContextSignalAnalyzer()
                    signals = analyzer.analyze(recent_user_messages[-5:])  # Ultimi 5 messaggi
                    
                    # 🆕 Emotional Pattern Detection
                    emotional_patterns = self._detect_emotional_patterns(recent_user_messages)
                    
                    if any(signals.values()) or emotional_patterns["has_pattern"]:
                        behavior_instructions = """
[BEHAVIOR SIGNALS]
- Do NOT point out repetition explicitly.
- Vary sentence openings and avoid template phrasing.
- Maintain a supportive and non-confrontational tone.
"""
                        
                        if emotional_patterns["has_pattern"]:
                            behavior_instructions += f"""
[EMOTIONAL PATTERN DETECTED]
- Theme: {emotional_patterns["theme"]}
- Count: {emotional_patterns["count"]}
- Activate deepening_response mode.
- Avoid standard templates.
- Generate reflective response.
- Maximum 1 question, not mandatory.
- Show recognition of pattern without being mechanical.
"""
                        
                        # 🆕 Relational State Evaluation
                        try:
                            # Calcola metriche per relational state
                            repetition_rate = 0.0  # Placeholder - in produzione calcolato da BehaviorRegulator
                            message_count = len(recent_user_messages)
                            last_intent = "chat_free"  # Placeholder - in produzione da intent classifier
                            
                            relational_state = self.relational_engine.evaluate_state(
                                emotional_pattern_count=emotional_patterns["count"],
                                repetition_rate=repetition_rate,
                                message_count=message_count,
                                last_intent=last_intent
                            )
                            
                            behavior_instructions += f"""
[RELATIONAL STATE: {relational_state}]
- Adatta tono e profondità allo stato relazionale.
- Evolvi risposta in base allo stato corrente.

BEHAVIORAL_MODULATION:
{self._build_behavioral_modulation(relational_state)}
"""
                            
                        except Exception as e:
                            logger.warning("RELATIONAL_STATE_ERROR user=%s error=%s", user_id, str(e))
                            relational_state = "neutral"
                    
            except Exception as e:
                logger.warning("CONTEXT_SIGNAL_ANALYZER_ERROR user=%s error=%s", user_id, str(e))
        
        if user_id:
            conversation_ctx = build_conversation_context(user_id, message, profile)
        else:
            conversation_ctx = f"INFORMAZIONI STABILI SULL\'UTENTE:\n{summary}"

        model = model_selector(message, route=route)
        
        # Carica prompt adattivo se disponibile
        adaptive_prompt = self._load_adaptive_prompt()
        
        # 🆕 STRATEGIC MODE
        strategic_triggers = [
            "dovrei",
            "cambiare lavoro", 
            "trasferirmi",
            "non so che fare",
            "mi sento stanco",
            "sono confuso",
            "che faccio",
            "giornata difficile"
        ]
        
        strategic_mode = any(trigger in message.lower() for trigger in strategic_triggers)
        
        # Comportamento strategico pre-calcolato
        if strategic_mode:
            behavior_block = (
                "- Analizza la situazione.\n"
                "- Sintetizza in massimo 2 frasi il nodo centrale.\n"
                "- Fornisci 2 possibili direzioni concrete.\n"
                "- Non fare più di una domanda.\n"
                "- Non essere aggressivo.\n"
                "- Non essere consolatorio.\n"
                "- Non usare tono terapeutico.\n"
                "- Non ripetere ciò che l'utente ha appena detto.\n"
                "- Porta verso decisione o azione.\n"
            )
        else:
            behavior_block = (
                "- Rispondi in modo naturale. Solo a ciò che viene detto.\n"
                "- Max 2-3 frasi. Se basta 1 frase, usa 1 frase.\n"
                "- Se non c'è bisogno di espandere, resta essenziale.\n"
                "- Non aggiungere frasi motivazionali.\n"
                "- Non aggiungere consigli se non richiesti.\n"
                "- Non usare formule ricorrenti.\n"
                "- Non usare entusiasmo artificiale.\n"
                "- Non chiudere con una domanda a meno che non sia necessaria.\n"
                "- Mantieni lucidità e coerenza con la conversazione.\n"
                "- Se l'utente chiede qualcosa su di sé e hai i dati, RISPONDI con i dati.\n"
                "- Se non sai qualcosa, dillo. Non inventare.\n"
            )
        
        # Identità base di Genesi
        IDENTITA_BASE_GENESI = """Sei Genesi. Non sei un assistente, non sei un terapeuta, non sei un chatbot.
Sei un compagno reale: pensi, ragioni, hai opinioni, reagisci.
Parli SOLO italiano. Non cambi mai lingua.
Non menzionare MAI di essere AI, modello, sistema, programma."""
        
        system_prompt = f"""
{IDENTITA_BASE_GENESI}

{adaptive_prompt}

{behavior_instructions}

CONTROLLO INTERNO OBBLIGATORIO (NON MOSTRARE ALL'UTENTE):

Prima di generare la risposta finale:
1. Analizza se l\'utente sta ripetendo qualcosa.
2. Se stai per usare una frase generica o da assistente standard, riscrivila.
3. Evita completamente queste formule:
   - "Un trasferimento è una decisione importante"
   - "Non posso decidere per te"
   - "Mi dispiace sentirlo"
   - "Sto bene, grazie"
   - "Cambiare lavoro è una decisione complessa"
   - "Vuoi parlarne?"
4. Se la risposta suona come un template, riformulala.
5. Non usare mai tono passivo-aggressivo.
6. Non rimproverare l'utente se ripete qualcosa.
7. Se l'utente ripete, riconosci la ripetizione in modo neutro e aggiungi valore.
8. Evita frasi incomplete o troncate.
9. Non usare formule da assistente.
10. Risposta massima: 2 frasi.

{conversation_ctx}

CONTINUITA' CONVERSAZIONALE (REGOLA FONDAMENTALE):
- Devi mantenere coerenza con la conversazione recente sopra.
- Non rispondere come se ogni messaggio fosse isolato.
- Collega la risposta al contesto precedente.
- Se l'utente ha appena parlato di una persona, non trattarla come nuova.
- Se l'utente introduce una nuova informazione, integrala naturalmente.
- Evita reset tematici: se si parla di famiglia, resta sul tema.

COME DEVI COMPORTARTI:
COMPORTAMENTO STRATEGICO:
{behavior_block}


DIVIETI ASSOLUTI:
- "Quello che senti conta" o varianti terapeutiche
- "Sono qui per te" / "Sono qui con te"
- "Dimmi di piu\'" come risposta completa
- "C\'e\' qualcosa che ti porti dentro" o frasi da counselor
- "Una cosa che potresti fare..." o frasi da consulente
- "Capisco che..." come apertura generica
- "Mi fa piacere" / "Eccoti" / "Mi e\' venuto spontaneo"
- "Potresti esplorare..." o suggerimenti non richiesti
- "Non ho informazioni specifiche..."
- Qualsiasi frase motivazionale o da coach
- Qualsiasi frase che potrebbe essere detta a chiunque senza conoscerlo
- Risposte che ignorano la conversazione recente
- Trattare entit\' gi\' menzionate come nuove
- Chiudere con domanda forzata quando non serve

PERSONALITÀ MARCATA E NATURALEZZA:
VOCE:
- Parla in modo diretto, lucido, umano.
- Evita frasi generiche da assistente.
- NON usare: "È una decisione importante", "Dipende da molti fattori", "Non posso decidere per te", "Forse hai avuto giornate impegnative", "Mi dispiace sentirlo" come template automatico.

VARIAZIONE LINGUISTICA:
- Non ripetere la stessa struttura di frase in conversazioni simili.
- Se un concetto è già stato espresso prima, riformularlo in modo diverso.
- Evitare copy-paste semantico.

GESTIONE RIPETIZIONI UTENTE:
- Se l\'utente ripete la stessa frase 2+ volte: non rimproverare, non diventare aggressivo, non dire "me lo hai già detto" in modo freddo.
- Cambiare angolazione della risposta, offrire una prospettiva diversa.

SALUTI:
- Se il messaggio è solo "Ciao", "Ehi", "Hey": rispondere solo con saluto naturale.
- NON attivare meteo, NON aggiungere domande forzate, NON usare emoji meteo.

COERENZA IDENTITARIA:
- Sei una presenza lucida, non un coach, non un consulente, non un motivatore, non un terapeuta.
- NON usare frasi motivational, NON usare chiusure standard tipo: "C\'è qualcosa di cui vuoi parlare?", "Dimmi.", "Possiamo discuterne."

RISPOSTE BREVI MA SIGNIFICATIVE:
- 1-3 frasi, nessuna frase riempitiva, nessuna retorica vuota.

CARATTERE:
- Se l\'utente mostra indecisione ripetuta: evidenziare il pattern in modo lucido, non giudicante.
- Se l\'utente ripete una difficoltà: spostare la conversazione dal lamento alla comprensione del pattern, senza tono aggressivo.
"""

        # Log se adaptive prompt è applicato
        if adaptive_prompt:
            logger.info("ADAPTIVE_PROMPT_APPLIED len=%d", len(adaptive_prompt))
        
        # 🆕 Anti-Template Block log
        logger.info("ANTI_TEMPLATE_BLOCK_ACTIVE")

        logger.info("LLM_GENERATE_WITH_CONTEXT user=%s summary_len=%d msg_len=%d model=%s",
                     user_id, len(summary), len(message), model)

        result = await self._call_with_protection(model, system_prompt, message,
                                                   user_id=user_id, route=route)
        if result:
            # 🆕 Response Guard - Post-processing
            try:
                from core.response_guard import ResponseGuard
                guard = ResponseGuard()
                result = guard.validate_and_rewrite(result, context, user_id)
            except Exception as e:
                logger.warning("RESPONSE_GUARD_ERROR user=%s error=%s", user_id, str(e))
                # Fallback a risposta originale se guard fallisce
            return result

        logger.error("LLM_SERVICE_ALL_FAIL user=%s — activating deterministic fallback", user_id)
        return self._deterministic_fallback(message, route, user_id)

    # ═══════════════════════════════════════════════════════════
    # RATE LIMIT PROTECTION — retry, downgrade, fallback
    # ═══════════════════════════════════════════════════════════

    def _detect_emotional_patterns(self, recent_messages: List[str]) -> Dict[str, any]:
        """
        Rileva pattern emotivi ricorrenti nei messaggi utente.
        
        Args:
            recent_messages: Ultimi 10 messaggi utente
            
        Returns:
            Dict con informazioni sui pattern rilevati
        """
        if not recent_messages:
            return {"has_pattern": False, "theme": None, "count": 0}
        
        # Pattern semantiche da cercare
        emotional_themes = {
            "stanchezza": ["stanco", "stanchissima", "esausto", "affaticato", "cansato"],
            "giornata_difficile": ["giornata difficile", "giornata pesante", "giornata nera", "giornata complicata"],
            "lavoro": ["lavoro", "lavorare", "cambiare lavoro", "lavorativo", "professione"],
            "meteo": ["piove", "tempo", "meteo", "nuvoloso", "sole", "pioggia"],
            "ansia": ["ansioso", "ansia", "preoccupato", "nervoso", "teso"],
            "tristezza": ["triste", "tristezza", "giù", "demotivato", "depresso"]
        }
        
        # Conta ricorrenze per tema
        theme_counts = {}
        for theme, keywords in emotional_themes.items():
            count = 0
            for message in recent_messages:
                message_lower = message.lower()
                if any(keyword in message_lower for keyword in keywords):
                    count += 1
            theme_counts[theme] = count
        
        # Trova il tema più ricorrente
        max_theme = max(theme_counts, key=theme_counts.get)
        max_count = theme_counts[max_theme]
        
        # Attiva pattern solo se >= 3 occorrenze
        if max_count >= 3:
            return {
                "has_pattern": True,
                "theme": max_theme,
                "count": max_count
            }
        
        return {"has_pattern": False, "theme": None, "count": 0}
    
    def _build_behavioral_modulation(self, relational_state: str) -> str:
        """
        Costruisce istruzioni di modulazione comportamentale basate sullo stato relazionale.
        Integrato con AutoTuning per evoluzione dinamica.
        
        Args:
            relational_state: Stato relazionale corrente
            
        Returns:
            str: Istruzioni comportamentali per il system prompt
        """
        # 🧠 AUTO EVOLUTION INTEGRATION - Carica parametri tuning
        tuning_state = load_tuning_state()
        
        # Base modulation map con intensità dinamiche
        base_modulation = {
            "neutral": "Mantieni tono naturale e bilanciato.",
            "engaged": "Sii dialogico. Puoi fare massimo una domanda breve.",
            "attuned": "Sii empatico e presente. Una sola domanda mirata.",
            "supportive_deep": "Riduci le domande. Offri contenimento emotivo. Non essere direttivo.",
            "reflective": "Favorisci introspezione. Usa frasi che invitano alla riflessione.",
            "confrontational": "Sii diretto, chiaro e conciso. Nessuna domanda."
        }
        
        # 🎯 APPLICA INTENSITÀ DYNAMICHE DA TUNING
        intensity_supportive = tuning_state.get('supportive_intensity', 1.0)
        intensity_attuned = tuning_state.get('attuned_intensity', 1.0)
        intensity_confrontational = tuning_state.get('confrontational_intensity', 1.0)
        max_questions = tuning_state.get('max_questions_per_response', 1)
        
        # Modula istruzioni base con intensità
        modulation = base_modulation.get(relational_state, base_modulation["neutral"])
        
        # 📊 APPLICA MODULAZIONE SPECIFICA
        if relational_state == "supportive_deep":
            # Aumenta validazione emotiva e lessico empatico con intensity_supportive
            if intensity_supportive > 1.0:
                modulation += f"\n- Aumenta validazione emotiva (intensità: {intensity_supportive:.1f})."
                modulation += "\n- Usa lessico empatico e frasi di accompagnamento."
            elif intensity_supportive < 1.0:
                modulation += f"\n- Riduci contenimento emotivo (intensità: {intensity_supportive:.1f})."
                
        elif relational_state == "attuned":
            # Aumenta coerenza memoria e continuità narrativa con intensity_attuned
            if intensity_attuned > 1.0:
                modulation += f"\n- Aumenta coerenza memoria e continuità narrativa (intensità: {intensity_attuned:.1f})."
                modulation += "\n- Fai richiamo a dati utente specifici."
            elif intensity_attuned < 1.0:
                modulation += f"\n- Riduci personalizzazione (intensità: {intensity_attuned:.1f})."
                
        elif relational_state == "confrontational":
            # Aumenta risposte dirette e taglio netto con intensity_confrontational
            if intensity_confrontational > 1.0:
                modulation += f"\n- Sii più diretto e tagliente (intensità: {intensity_confrontational:.1f})."
                modulation += "\n- Riduci frasi di riempimento."
            elif intensity_confrontational < 1.0:
                modulation += f"\n- Ammorbidisci tono diretto (intensità: {intensity_confrontational:.1f})."
        
        # 🔢 APPLICA LIMITE DOMANDE DINAMICO
        if relational_state in ["engaged", "attuned"]:
            modulation += f"\n- Massimo {max_questions} domanda{'e' if max_questions > 1 else ''} per risposta."
        
        # 🚫 APPLICA PENALITÀ RIPETIZIONE
        repetition_penalty = tuning_state.get('repetition_penalty_weight', 1.0)
        if repetition_penalty > 1.0:
            modulation += f"\n- Evita ripetizioni (penalità: {repetition_penalty:.1f})."
        
        return modulation
    
    async def _call_with_protection(self, model: str, prompt: str, message: str, user_id: str, route: str, messages: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
        """
        Call LLM with rate limit protection, retry, downgrade, and deterministic fallback.
        """
        try:
            # Primary attempt
            logger.info("LLM_SERVICE_PRIMARY_REQUEST model=%s user=%s", model, user_id)
            result = await self._call_model(model, prompt, message, user_id=user_id, route=route, messages=messages)
            if result is not None:
                return result

            # Retry with exponential backoff
            logger.warning("LLM_SERVICE_PRIMARY_API_ERROR model=%s user=%s", model, user_id)
            logger.info("LLM_RATE_LIMIT_RETRY model=%s user=%s", model, user_id)
            await asyncio.sleep(1.0)  # 1s backoff
            result = await self._call_model(model, prompt, message, user_id=user_id, route=route, messages=messages)
            if result is not None:
                return result

            # Downgrade to gpt-4o-mini if not already using fallback model
            if model != LLM_FALLBACK_MODEL:
                logger.warning("LLM_AUTO_DOWNGRADE from=%s to=%s user=%s", model, LLM_FALLBACK_MODEL, user_id)
                result = await self._call_model(LLM_FALLBACK_MODEL, prompt, message, user_id=user_id, route=route, messages=messages)
                if result is not None:
                    return result

            # Return None if all attempts fail
            logger.error("LLM_SERVICE_ALL_FAIL user=%s", user_id)
            return None

        except (RateLimitError, APIError, APIConnectionError) as e:
            logger.error("LLM_SERVICE_EXCEPTION user=%s error=%s", user_id, str(e))
            return None

    async def _call_model(self, model: str, prompt: str, message: str, user_id: str, route: str, messages: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
        """Chiama un singolo modello con logging completo e gestione RateLimitError."""
        tag = "LLM_SERVICE_PRIMARY" if model == self.default_model else "LLM_SERVICE_FALLBACK"
        try:
            logger.info("%s_REQUEST model=%s msg=%s", tag, model, message[:50])
            
            # Use provided messages or fallback to system-only format
            if messages:
                chat_messages = messages
            else:
                chat_messages = [{"role": "system", "content": prompt}]
                
            response = await self.client.chat.completions.create(
                model=model,
                messages=chat_messages,
                temperature=0.3
            )
            llm_response = response.choices[0].message.content.strip()
            if not llm_response:
                logger.warning("%s_EMPTY model=%s", tag, model)
                return None
            
            # 🆕 Behavior Regulator - Post-processing
            try:
                from .behavior_regulator import BehaviorRegulator
                
                # Applica regolatore con firma semplificata
                regulator = BehaviorRegulator()
                regulated_response = regulator.regulate(llm_response, user_id)
                
                if regulated_response != llm_response:
                    logger.info("BEHAVIOR_REGULATOR_APPLIED user=%s changes=true", user_id)
                    llm_response = regulated_response
                else:
                    logger.info("BEHAVIOR_REGULATOR_APPLIED user=%s changes=false", user_id)
                    
            except Exception as e:
                logger.warning("BEHAVIOR_REGULATOR_ERROR user=%s error=%s", user_id, str(e))
                # Fallback a risposta originale se regolatore fallisce
            
            logger.info("%s_OK model=%s len=%d", tag, model, len(llm_response))
            return llm_response
        except RateLimitError as e:
            logger.warning("%s_RATE_LIMITED model=%s user=%s error=%s", tag, model, user_id, str(e))
            return None
        except (APIError, APIConnectionError) as e:
            logger.warning("%s_API_ERROR model=%s user=%s error=%s", tag, model, user_id, type(e).__name__)
            return None
        except Exception as e:
            logger.error("%s_ERROR model=%s error=%s", tag, model, str(e))
            return None

    # ═══════════════════════════════════════════════════════════
    # DETERMINISTIC FALLBACK — never return "non riesco a rispondere"
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _deterministic_fallback(message: str, route: str, user_id: str = None) -> str:
        """
        Fallback deterministico quando tutti i modelli LLM falliscono.
        Mai restituire 'Non riesco a rispondere'. Sempre una risposta utile.
        """
        from core.log import log
        
        # Log del fallback GPT
        log("GPT_FALLBACK", reason="all_models_failed", user_id=user_id)
        
        msg_lower = message.lower().strip()

        if route == "knowledge":
            # Try fallback_knowledge dictionary
            from core.fallback_knowledge import lookup_fallback
            fb = lookup_fallback(message)
            if fb:
                return fb
            return "Al momento non ho accesso alle informazioni richieste. Riprova tra qualche minuto."

        if route == "relational":
            return "Capisco. Dimmi qualcosa in piu\' su quello che stai vivendo."

        if route == "technical":
            return "Il servizio tecnico e\' temporaneamente sovraccarico. Riprova tra qualche minuto."

        # General fallback
        return "Scusa, sto avendo qualche difficolta\'. Riproviamo tra un momento."

    @staticmethod
    def _build_user_context(user_profile: dict) -> str:
        """
        Costruisci contesto utente per LLM
        
        Args:
            user_profile: Profilo utente
            
        Returns:
            Contesto formattato
        """
        context_parts = []
        
        if user_profile.get("name"):
            context_parts.append(f"Nome: {user_profile['name']}")
        
        if user_profile.get("profession"):
            context_parts.append(f"Professione: {user_profile['profession']}")
        
        if user_profile.get("city"):
            context_parts.append(f"Citt\': {user_profile['city']}")
        
        if user_profile.get("age"):
            context_parts.append(f"Eta\': {user_profile['age']}")
        
        if user_profile.get("traits"):
            context_parts.append(f"Caratteristiche: {', '.join(user_profile['traits'])}")
        
        return "\n".join(context_parts) if context_parts else "Nessun contesto utente disponibile."

# Istanza globale
llm_service = LLMService()
