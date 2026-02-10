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
import re

def sanitize_for_tts(text: str) -> str:
    """
    Funzione GLOBALE per sanificare il testo prima del TTS
    Rimuove emoji e simboli non pronunciabili
    """
    if not text:
        return ""
    
    # Rimuovi tutte le emoji
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
    
    # Rimuovi emoji
    cleaned = emoji_pattern.sub('', text)
    
    # Rimuovi caratteri decorativi
    decorative_pattern = re.compile(r'[★☆♦♠♣♥❤️💔💕💞💓💗💖💘💝💟☀️☁️☂️☃️⭐💫✨⚡🔥💥💢💦💧💤💨🕳️💤💢💯💢💢]')
    cleaned = decorative_pattern.sub('', cleaned)
    
    # Rimuovi simboli matematici e tecnici
    tech_pattern = re.compile(r'[±×÷≠≤≥∞∑∏∫∂∇∆∇∂∫]')
    cleaned = tech_pattern.sub('', cleaned)
    
    # Normalizza spazi
    cleaned = ' '.join(cleaned.split())
    
    return cleaned.strip()

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
        
        # Rimuovi emoji dai log per evitare crash encoding su Windows
        safe_log_text = ''.join(c if ord(c) < 128 else '?' for c in final_text)
        print(f"[SURGICAL_PIPELINE] Generated: '{safe_log_text[:50]}...'", flush=True)
        
        # 4. POST-FILTER - Pulizia sicurezza (NON normalizzatore)
        print(f"[SURGICAL_PIPELINE] Step 4: Post-filter safety", flush=True)
        
        # Costruisci display_text e tts_text con logiche DIVERSE
        display_text = self._build_display_text(final_text, intent_type)
        tts_text = await self._build_tts_text(final_text, intent_type, user_message)
        
        # Rimuovi emoji dai log per evitare crash encoding su Windows
        safe_display_log = ''.join(c if ord(c) < 128 else '?' for c in display_text)
        safe_tts_log = ''.join(c if ord(c) < 128 else '?' for c in tts_text)
        
        print(f"[SURGICAL_PIPELINE] Display: '{safe_display_log[:50]}...'", flush=True)
        print(f"[SURGICAL_PIPELINE] TTS: '{safe_tts_log[:50]}...'", flush=True)
        
        # 5. TTS - Immutato (gestito dall'esterno)
        print(f"[SURGICAL_PIPELINE] Step 5: Ready for TTS", flush=True)
        
        # Costruisci risultato finale con DUE CAMPI DISTINTI
        result = {
            "display_text": display_text,  # SOLO per UI (con emoji)
            "tts_text": tts_text,         # SOLO per TTS (senza emoji)
            "intent": intent,
            "engine_used": engine_type,
            "proactor_decision": proactor_decision,
            "original_generated": final_text,
            "filtered": tts_text != final_text,
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
    
    def _build_display_text(self, raw_text: str, intent_type: str) -> str:
        """
        Costruisce display_text per UI con emoji e markdown
        - Rimuove solo inglese e emoticon ASCII
        - MANTIENE emoji unicode
        - MANTIENE markdown
        """
        import re
        
        if not raw_text:
            return raw_text
        
        display_text = raw_text.strip()
        
        # 1. Rimuovi emoticon ASCII (:D, :), :P, ;), ecc.)
        ascii_emoticons = [
            r':D', r':\)', r':P', r';\)', r':-D', r':-\)', r':-P', r';-\)',
            r':-o', r':-O', r':o', r':O', r':-\\', r':\\', r':-/', r':/',
            r':\'\(', r':\'\(', r':-\'\(', r':-\'\('
        ]
        
        for emoticon in ascii_emoticons:
            display_text = re.sub(emoticon, '', display_text, flags=re.IGNORECASE)
        
        # 2. Rimuovi frasi inglesi comuni
        english_patterns = [
            r'\b(hello|hi|hey|good morning|good evening|good afternoon|good night|bye|goodbye)\b',
            r'\b(thank you|thanks|please|sorry|excuse me|pardon)\b',
            r'\b(amazing|awesome|great|wonderful|fantastic|perfect|excellent|really|actually|literally)\b',
            r'\b(how are you|what\'s up|how\'s it going)\b'
        ]
        
        for pattern in english_patterns:
            display_text = re.sub(pattern, '', display_text, flags=re.IGNORECASE)
        
        # 3. Rimuovi parole inglesi singole (ma mantieni italiano)
        # Solo parole inglesi molto comuni e sicure
        english_words = [
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 
            'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 
            'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use'
        ]
        
        for word in english_words:
            # Rimuovi solo se è una parola intera
            display_text = re.sub(r'\b' + re.escape(word) + r'\b', '', display_text, flags=re.IGNORECASE)
        
        # 4. Pulizia spazi multipli
        display_text = re.sub(r'\s+', ' ', display_text).strip()
        
        return display_text
    
    async def _build_tts_text(self, raw_text: str, intent_type: str, user_message: str) -> str:
        """
        Costruisce tts_text per sintesi vocale
        - Rimuove TUTTO ciò che non è parlabile
        - Rimuove emoji, markdown, simboli
        - Rimuove inglese e emoticon ASCII
        """
        import re
        
        if not raw_text:
            return raw_text
        
        tts_text = raw_text.strip()
        
        # 1. Rimuovi TUTTE le emoji unicode
        emoji_patterns = [
            r'[\U0001F600-\U0001F64F]',  # Emoticoni
            r'[\U0001F300-\U0001F5FF]',  # Simboli vari
            r'[\U0001F680-\U0001F6FF]',  # Trasporti e simboli
            r'[\U0001F1E0-\U0001F1FF]',  # Bandiere
            r'[\U00002600-\U000026FF]',  # Simboli vari
            r'[\U00002700-\U000027BF]',  # Dingbats
        ]
        
        for pattern in emoji_patterns:
            tts_text = re.sub(pattern, '', tts_text)
        
        # 2. Rimuovi markdown
        tts_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', tts_text)  # **bold**
        tts_text = re.sub(r'__([^_]+)__', r'\1', tts_text)      # __underline__
        tts_text = re.sub(r'##\s*', '', tts_text)               # ## headers
        tts_text = re.sub(r'^\s*[-*+]\s*', '', tts_text, flags=re.MULTILINE)  # bullet points
        tts_text = re.sub(r'^\s*\d+\.\s*', '', tts_text, flags=re.MULTILINE)  # numbered lists
        
        # 3. Rimuovi emoticon ASCII
        ascii_emoticons = [
            r':D', r':\)', r':P', r';\)', r':-D', r':-\)', r':-P', r';-\)',
            r':-o', r':-O', r':o', r':O', r':-\\', r':\\', r':-/', r':/',
            r':\'\(', r':\'\(', r':-\'\(', r':-\'\('
        ]
        
        for emoticon in ascii_emoticons:
            tts_text = re.sub(emoticon, '', tts_text, flags=re.IGNORECASE)
        
        # 4. Rimuovi frasi inglesi
        english_patterns = [
            r'\b(hello|hi|hey|good morning|good evening|good afternoon|good night|bye|goodbye)\b',
            r'\b(thank you|thanks|please|sorry|excuse me|pardon)\b',
            r'\b(amazing|awesome|great|wonderful|fantastic|perfect|excellent|really|actually|literally)\b',
            r'\b(how are you|what\'s up|how\'s it going)\b'
        ]
        
        for pattern in english_patterns:
            tts_text = re.sub(pattern, '', tts_text, flags=re.IGNORECASE)
        
        # 5. Rimuovi parole inglesi
        english_words = [
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 
            'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 
            'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use'
        ]
        
        for word in english_words:
            tts_text = re.sub(r'\b' + re.escape(word) + r'\b', '', tts_text, flags=re.IGNORECASE)
        
        # 6. Rimuovi simboli non parlabili
        tts_text = re.sub(r'[^\w\s\.,!?;:]', ' ', tts_text)  # Solo caratteri parlabili
        
        # 7. Pulizia spazi multipli
        tts_text = re.sub(r'\s+', ' ', tts_text).strip()
        
        # 8. Language guard come sicurezza finale
        guard_result = language_guard.check_and_clean(tts_text, {
            "intent": intent_type,
            "user_message": user_message
        })
        
        if not guard_result["is_clean"]:
            print(f"[SURGICAL_PIPELINE] TTS Contamination detected: {guard_result['issues']}", flush=True)
            cleaned_text = self._clean_response_safely(tts_text, guard_result['issues'], intent_type)
            if cleaned_text and len(cleaned_text.strip()) > 3:
                tts_text = cleaned_text
            else:
                print(f"[SURGICAL_PIPELINE] TTS Cleaning failed, using fallback", flush=True)
                tts_text = await self._regenerate_response_safely(user_message, intent_type)
        else:
            tts_text = guard_result["cleaned_text"]
        
        return tts_text
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
