"""
NUOVA PIPELINE CHIRURGICA - Flusso obbligatorio
USER MESSAGE → GPT-mini → PROACTOR → Motore → POST_FILTER → TTS
"""

from typing import Dict, List, Optional, Any
from core.proactor import proactor
from core.engines import engine_registry
from core.intent_engine import IntentEngine
from core.post_llm_filter import post_llm_filter
from core.language_guard import language_guard

class SurgicalPipeline:
    """
    PIPELINE CHIRURGICA - Flusso obbligatorio e deterministico
    
    FLUSSO FISSO:
    1. GPT-mini (IntentEngine) → Classifica intent
    2. PROACTOR → Decide motore
    3. Motore → Genera risposta
    4. POST_FILTER → Pulisce (solo sicurezza)
    5. TTS (immutato)
    
    NESSUNA deviazione ammessa
    """
    
    def __init__(self):
        self.intent_engine = IntentEngine()
        
    async def process_message(
        self,
        user_message: str,
        cognitive_state,
        recent_memories: List[Dict],
        relevant_memories: List[Dict],
        tone,
        intent: Dict,
        document_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        PROCESSO CHIRURGICO OBBLIGATORIO
        """
        print(f"[SURGICAL_PIPELINE] Starting: '{user_message[:50]}...'", flush=True)
        
        # 1. GPT-MINI - Classificazione intent (se non già fornita)
        if not intent or not intent.get("type"):
            print(f"[SURGICAL_PIPELINE] Step 1: GPT-mini classification", flush=True)
            print(f"[DEBUG_INTENT] raw_message={user_message}", flush=True)
            intent = self.intent_engine.decide(
                user_message,
                cognitive_state.user,
                cognitive_state,
                recent_memories,
                relevant_memories,
                tone
            )
            print(f"[DEBUG_INTENT] classified_intent={intent.get('type', 'unknown')}", flush=True)
        else:
            print(f"[SURGICAL_PIPELINE] Step 1: Using provided intent", flush=True)
            print(f"[DEBUG_INTENT] provided_intent={intent.get('type', 'unknown')}", flush=True)
        
        intent_type = intent.get("type", "chat_free")
        print(f"[SURGICAL_PIPELINE] Intent classified: {intent_type}", flush=True)
        print(f"[DEBUG_INTENT] final_intent_type={intent_type}", flush=True)
        
        # 2. PROACTOR - Decisione motore
        print(f"[SURGICAL_PIPELINE] Step 2: PROACTOR decision", flush=True)
        print(f"[DEBUG_PROACTOR] received_intent={intent_type}", flush=True)
        proactor_decision = proactor.decide_engine(intent_type, user_message, {
            "user_state": cognitive_state,
            "recent_memories": recent_memories,
            "tone": tone,
            "document_context": document_context
        })
        print(f"[DEBUG_PROACTOR] decision={proactor_decision}", flush=True)
        
        engine_type = proactor_decision["engine"].value
        action = proactor_decision["action"]
        params = proactor_decision["params"]
        
        print(f"[DEBUG_PROACTOR] selected_engine={engine_type}", flush=True)
        print(f"[DEBUG_PROACTOR] action={action}", flush=True)
        
        print(f"[SURGICAL_PIPELINE] Engine selected: {engine_type}, action: {action}", flush=True)
        
        # 3. MOTORE - Generazione risposta
        print(f"[SURGICAL_PIPELINE] Step 3: Engine generation", flush=True)
        
        if action == "safe_fallback":
            # Fallback sicuro per richieste bloccate
            final_text = "Non posso aiutarti con questa richiesta."
        else:
            try:
                # Generazione con motore specifico
                final_text = await engine_registry.generate_with_engine(
                    engine_type=engine_type,
                    message=user_message,
                    params={**params, "intent_type": intent_type},
                    context={
                        "user_id": getattr(cognitive_state.user, 'id', 'unknown'),
                        "user_message": user_message,
                        "intent": intent,
                        "cognitive_state": cognitive_state,
                        "recent_memories": recent_memories,
                        "tone": tone
                    }
                )
                
                if not final_text or len(final_text.strip()) < 3:
                    print(f"[SURGICAL_PIPELINE] Engine returned empty, using fallback", flush=True)
                    print(f"[DEBUG_FALLBACK] reason=engine_empty_response", flush=True)
                    final_text = "Cerchiamo di trovare una soluzione insieme."
                    
            except Exception as e:
                print(f"[SURGICAL_PIPELINE] Engine error: {e}", flush=True)
                # Prova motore successivo
                final_text = await self._try_fallback_engine(user_message, intent_type, params)
        
        print(f"[SURGICAL_PIPELINE] Generated: '{final_text[:50]}...'", flush=True)
        
        # 4. POST-FILTER - Pulizia sicurezza (NON normalizzatore)
        print(f"[SURGICAL_PIPELINE] Step 4: Post-filter safety", flush=True)
        
        # Language guard come sicurezza
        guard_result = language_guard.check_and_clean(final_text, {
            "intent": intent_type,
            "user_message": user_message
        })
        
        if guard_result["is_clean"]:
            filtered_text = guard_result["cleaned_text"]
        else:
            # Se contaminato, PULISCE NON SOSTITUISCE
            print(f"[SURGICAL_PIPELINE] Contamination detected: {guard_result['issues']}", flush=True)
            
            # 1. Tentativo di pulizia NON distruttiva
            cleaned_text = self._clean_response_safely(final_text, guard_result['issues'], intent_type)
            
            if cleaned_text and len(cleaned_text.strip()) > 3:
                print(f"[SURGICAL_PIPELINE] Cleaned successfully", flush=True)
                filtered_text = cleaned_text
            else:
                # 2. Solo se pulizia fallisce completamente, rigenera
                print(f"[SURGICAL_PIPELINE] Cleaning failed, regenerating", flush=True)
                filtered_text = await self._regenerate_response_safely(user_message, intent_type)
        
        print(f"[SURGICAL_PIPELINE] Filtered: '{filtered_text[:50]}...'", flush=True)
        
        # 5. TTS - Immutato (gestito dall'esterno)
        print(f"[SURGICAL_PIPELINE] Step 5: Ready for TTS", flush=True)
        
        # Costruisci risultato finale
        result = {
            "final_text": filtered_text,
            "intent": intent,
            "engine_used": engine_type,
            "proactor_decision": proactor_decision,
            "original_generated": final_text,
            "filtered": filtered_text != final_text,
            "pipeline": "surgical"
        }
        
        print(f"[SURGICAL_PIPELINE] Completed successfully", flush=True)
        return result
    
    async def _try_fallback_engine(self, message: str, intent_type: str, params: Dict[str, Any]) -> str:
        """
        Prova motore di fallback se quello principale fallisce
        MAI zittisce l'utente
        """
        print(f"[SURGICAL_PIPELINE] Trying fallback engine", flush=True)
        
        try:
            # Fallback a PersonalPlex per la maggior parte dei casi
            if intent_type != "chat_free":
                fallback_params = {
                    "temperature": 0.7,
                    "max_tokens": 60,
                    "mode": "safe_fallback"
                }
                
                response = await engine_registry.generate_with_engine(
                    engine_type="personalplex",
                    message=message,
                    params=fallback_params,
                    context={"intent_type": intent_type}
                )
                
                if response and len(response.strip()) > 3:
                    return response
        except Exception as e:
            print(f"[SURGICAL_PIPELINE] Fallback engine also failed: {e}", flush=True)
        
        # Ultimo fallback - risposta generica ma non vuota
        print(f"[DEBUG_FALLBACK] reason=final_fallback_engine_failed", flush=True)
        return "Cerchiamo di affrontare questo insieme. C'è altro che posso fare per aiutarti?"
    
    def _clean_response_safely(self, text: str, issues: List[str], intent_type: str = "") -> str:
        """
        Pulizia NON distruttiva del testo
        Rimuove solo contaminazioni, preserva il significato
        EMOJI CONSENTITI in chat libera
        """
        if not text:
            return ""
        
        cleaned = text
        
        # Rimuovi emoji SOLO in contesti specialistici, non in chat libera
        if "emoji" in issues and intent_type != "chat_free":
            import re
            # Rimuovi emoji comuni
            emoji_pattern = re.compile(
                "["
                "\U0001F600-\U0001F64F"  # emoticons
                "\U0001F300-\U0001F5FF"  # symbols & pictographs
                "\U0001F680-\U0001F6FF"  # transport & map symbols
                "\U0001F1E0-\U0001F1FF"  # flags (iOS)
                "\U00002702-\U000027B0"
                "\U000024C2-\U0001F251"
                "]+", flags=re.UNICODE
            )
            cleaned = emoji_pattern.sub(r'', cleaned)
        
        # Rimuovi azioni teatrali (*smile*, *giggle*) - SEMPRE
        if "theatricality" in issues:
            import re
            # Rimuovi testo tra asterischi
            theatrical_pattern = re.compile(r'\*[^*]*\*', re.IGNORECASE)
            cleaned = theatrical_pattern.sub('', cleaned)
        
        # Rimuovi caratteri non italiani - SEMPRE
        if "invalid_chars" in issues:
            import re
            # Mantieni solo caratteri italiani validi
            italian_pattern = re.compile(r'[^a-zA-ZàèéìíòóùÀÈÉÌÍÒÓÙ\s.,!?;:\'-]', re.UNICODE)
            cleaned = italian_pattern.sub('', cleaned)
        
        # Normalizza spazi
        cleaned = ' '.join(cleaned.split())
        
        return cleaned.strip()
    
    async def _regenerate_response_safely(self, user_message: str, intent_type: str) -> str:
        """
        Rigenera risposta solo se pulizia fallisce completamente
        Usa prompt correttivo per evitare contaminazione
        """
        try:
            # Prompt correttivo per evitare problemi
            if intent_type == "chat_free":
                prompt = f"Rispondi in modo semplice e diretto a: {user_message}\n\nImportante: rispondi solo in italiano, senza emoji, senza azioni tra asterischi, senza teatralità."
            elif intent_type == "medical_info":
                prompt = f"Rispondi con empatia ma senza consigli medici specifici a: {user_message}\n\nImportante: rispondi solo in italiano, senza emoji, senza azioni tra asterischi, senza teatralità."
            elif intent_type == "emotional_support":
                prompt = f"Rispondi con supporto emotivo a: {user_message}\n\nImportante: rispondi solo in italiano, senza emoji, senza azioni tra asterischi, senza teatralità."
            else:
                prompt = f"Rispondi in modo informativo a: {user_message}\n\nImportante: rispondi solo in italiano, senza emoji, senza azioni tra asterischi, senza teatralità."
            
            # Usa GPT-full per rigenerazione sicura
            from core.engines import engine_registry
            response = await engine_registry.generate_with_engine(
                engine_type="gpt_full",
                message=prompt,
                params={"temperature": 0.3, "max_tokens": 100},
                context={"regeneration": True}
            )
            
            if response and len(response.strip()) > 3:
                return response.strip()
            else:
                # Ultimo fallback - ma costruttivo
                return "Posso aiutarti in altro modo?"
                
        except Exception as e:
            print(f"[SURGICAL_PIPELINE] Regeneration failed: {e}", flush=True)
            # Fallback finale costruttivo
            return "Cerchiamo un approccio diverso."

# Istanza globale
surgical_pipeline = SurgicalPipeline()
