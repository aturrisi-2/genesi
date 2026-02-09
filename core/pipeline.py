"""
PIPELINE UNICA DETERMINISTICA
UNA request → UNA risposta finale
Nessuna chiamata duplicata
"""

from typing import Dict, List, Optional
import json
from core.local_llm import LocalLLM
from core.llm import generate_response as llm_generate
from core.genesi_response_engine import genesi_engine
from core.tools import resolve_tools
from core.intent_router import intent_router
from core.verified_knowledge import verified_knowledge

class Pipeline:
    """
    PIPELINE UNICA - DETERMINISTICA E UMANA
    UN SOLO PERCORSO PER MESSAGGIO
    """
    
    def __init__(self):
        self.local_llm = LocalLLM()
    
    async def process_message(
        self,
        user_message: str,
        cognitive_state,
        recent_memories: List[Dict],
        relevant_memories: List[Dict],
        tone,
        intent: Dict,
        document_context: Optional[Dict] = None
    ) -> Dict:
        """
        PIPELINE OBBLIGATORIA CON ROUTING DETERMINISTICO:
        1. Intent Router classifica il messaggio
        2. Routing decide la fonte dati
        3. UN SOLO modulo genera contenuto
        4. Contenuto assegnato a final_text
        """
        print(f"[PIPELINE] Processing: '{user_message[:50]}...'", flush=True)
        
        # 1. INTENT ROUTING DETERMINISTICO
        routing_info = intent_router.get_routing_info(user_message)
        print(f"[INTENT_ROUTED] type={routing_info['intent']} source={routing_info['source']} block_creative={routing_info['block_creative_llm']}", flush=True)
        
        # 2. GENERAZIONE CONTENUTO BASATA SU ROUTING
        final_text = await self._generate_content_with_routing(
            routing_info, user_message, cognitive_state, tone
        )
        
        # 3. ASSEGNA A final_text
        result = {
            "final_text": final_text,
            "confidence": "ok",
            "style": "psychological" if routing_info['intent'] == "emotional_support" else "standard",
            "path": routing_info['source'],
            "intent": routing_info['intent'],
            "routing_info": routing_info
        }
        
        print(f"[PIPELINE] final_text=\"{final_text}\"", flush=True)
        return result
    
    def _proactor_decide_path(self, user_message: str, cognitive_state, intent: Dict) -> Dict:
        """
        PROACTOR: Decide il percorso UNA SOLA VOLTA
        NON genera testo conversazionale
        Restituisce solo decisione strutturata
        """
        msg = user_message.strip()
        msg_lower = msg.lower()
        
        # BLOCCO INPUT VUOTO O MINIMO
        if not msg or len(msg.strip()) < 2:
            return {
                "path": "fallback",
                "reason": "empty_input",
                "confidence": 0.0
            }
        
        # BLOCCO RIPETIZIONI E CARATTERI SPURII
        if self._is_noise_input(msg):
            return {
                "path": "fallback", 
                "reason": "noise_input",
                "confidence": 0.0
            }
        
        # PRIORITÀ 1: PersonalPlex (canale umano principale)
        # REGOLA D'ORO: MAI chiamare LLM per testare disponibilità
        # Se è configurato → usalo, altrimenti fallback
        if self.local_llm.is_available():
            print(f"[PIPELINE] Using PersonalPlex (configured)", flush=True)
            return {
                "path": "personalplex",
                "reason": "personalplex_primary",
                "confidence": 0.9
            }
        else:
            print(f"[PIPELINE] PersonalPlex not configured", flush=True)
        
        # PRIORITÀ 2: GPT per supporto cognitivo
        # REGOLA D'ORO: MAI chiamare LLM per testare disponibilità
        # Se è configurato → usalo, altrimenti fallback
        print(f"[PIPELINE] Using GPT (configured)", flush=True)
        return {
            "path": "gpt",
            "reason": "gpt_cognitive_support",
            "confidence": 0.7
        }
        
        # PRIORITÀ 3: Tools per domande fattuali
        if self._is_factual_question(msg):
            print(f"[PIPELINE] Factual question detected", flush=True)
            return {
                "path": "tools",
                "reason": "factual_question",
                "confidence": 0.8
            }
        
        # PRIORITÀ 4: Fallback Genesi
        print(f"[PIPELINE] Using Genesi fallback", flush=True)
        return {
            "path": "fallback",
            "reason": "no_primary_available",
            "confidence": 0.5
        }
    
    async def _generate_content_with_routing(
        self, 
        routing_info: Dict, 
        user_message: str, 
        cognitive_state, 
        tone
    ) -> str:
        """
        GENERAZIONE CONTENUTO BASATA SU ROUTING DETERMINISTICO
        Blocca LLM creativo per domande mediche/storiche/fattuali
        """
        intent_type = routing_info['intent']
        source = routing_info['source']
        
        print(f"[PIPELINE] Generating content for intent={intent_type} source={source}", flush=True)
        
        # Chat libera → PersonalPlex creativo
        if intent_type == "chat_free":
            if self.local_llm.is_available():
                print(f"[PIPELINE] Using PersonalPlex for chat_free", flush=True)
                response = self.local_llm.generate_chat_response(user_message)
                if response and len(response.strip()) > 0:
                    return response.strip()
            
            # Fallback Genesi
            return self._genesi_fallback(user_message)
        
        # Supporto emotivo → ramo psicologico
        elif intent_type == "emotional_support":
            print(f"[PIPELINE] Routing to psychological support", flush=True)
            result = genesi_engine.generate_response_from_text(user_message)
            return result["final_text"]
        
        # Info mediche → fonte verificata
        elif intent_type == "medical_info":
            print(f"[PIPELINE] Using verified medical knowledge", flush=True)
            medical_data = verified_knowledge.get_medical_info(user_message)
            
            if medical_data.get("verified", False):
                content = medical_data.get("content", "")
                disclaimer = medical_data.get("disclaimer", "")
                
                # Aggiungi disclaimer se presente
                if disclaimer and content:
                    content = f"{content} {disclaimer}"
                
                return content
            else:
                return medical_data.get("content", "Per questioni mediche consulta un professionista.")
        
        # Info storiche → fonte verificata
        elif intent_type == "historical_info":
            print(f"[PIPELINE] Using verified historical knowledge", flush=True)
            historical_data = verified_knowledge.get_historical_info(user_message)
            
            if historical_data.get("verified", False):
                return historical_data.get("content", "Informazione storica non disponibile.")
            else:
                return historical_data.get("content", "Non ho informazioni specifiche su questo argomento storico.")
        
        # Weather → API
        elif intent_type == "weather":
            print(f"[PIPELINE] Using weather API", flush=True)
            try:
                tool_result = await resolve_tools(user_message)
                if tool_result and tool_result.get("data") and not tool_result["data"].get("error"):
                    return self._tools_template(tool_result)
            except Exception as e:
                print(f"[PIPELINE] Weather API error: {e}", flush=True)
            
            return "Non riesco a ottenere informazioni meteo in questo momento."
        
        # News → API
        elif intent_type == "news":
            print(f"[PIPELINE] Using news API", flush=True)
            try:
                tool_result = await resolve_tools(user_message)
                if tool_result and tool_result.get("data") and not tool_result["data"].get("error"):
                    return self._tools_template(tool_result)
            except Exception as e:
                print(f"[PIPELINE] News API error: {e}", flush=True)
            
            return "Non riesco a ottenere notizie in questo momento."
        
        # Fallback
        else:
            print(f"[PIPELINE] Using fallback for intent={intent_type}", flush=True)
            return self._genesi_fallback(user_message)
    
    def _genesi_fallback(self, user_message: str) -> str:
        """
        Fallback Genesi - sempre umano
        """
        print(f"[PIPELINE] using Genesi fallback", flush=True)
        
        # Estrai intent da testo per Genesi engine
        result = genesi_engine.generate_response_from_text(user_message)
        return result["final_text"]
    
    def _build_gpt_intent_prompt(self, user_message: str) -> str:
        """
        Build prompt per GPT intent extraction
        """
        sections = []
        
        sections.append(f"MESSAGGIO:\n{user_message}")
        
        sections.append(
            "ISTRUZIONI:\n"
            "- Analizza SOLO l'intent del messaggio\n"
            "- NON scrivere frasi complete\n"
            "- Rispondi SOLO in questo formato JSON:\n"
            '{\n'
            '  "intent": "greeting|physical_discomfort|emotional_distress|acknowledgment|question|farewell|generic",\n'
            '  "confidence": 0.0-1.0\n'
            '}'
        )
        
        return "\n\n".join(sections)
    
    def _tools_template(self, tool_result: dict) -> str:
        """
        Template diretto per dati tools
        """
        tool_type = tool_result.get("tool_type")
        data = tool_result.get("data", {})

        if tool_type == "meteo":
            city = data.get("city", "la tua zona")
            current = data.get("current", {})
            if not current:
                return "Non riesco a ottenere informazioni meteo."
            
            temp = current.get("temp", "")
            desc = current.get("description", "")
            return f"A {city} ci sono {temp}°C con {desc}."
        
        elif tool_type == "news":
            articles = data.get("articles", [])
            if not articles:
                return "Non riesco a ottenere notizie."
            
            title = articles[0].get("title", "").strip()
            return f"Notizia principale: {title}"
        
        return "Informazione non disponibile."
    
    def _is_noise_input(self, msg: str) -> bool:
        """
        Verifica se l'input è rumore/nonsense
        """
        msg_clean = msg.strip().lower()
        
        # Input troppo corto
        if len(msg_clean) < 3:
            return True
        
        # Solo caratteri ripetuti
        if len(set(msg_clean.replace(' ', ''))) < 3 and len(msg_clean) > 5:
            return True
        
        # Troppe parole identiche
        words = msg_clean.split()
        if len(words) > 3 and len(set(words)) < 2:
            return True
        
        return False
    
    def _is_factual_question(self, msg: str) -> bool:
        """
        Verifica se è una domanda fattuale
        """
        msg_lower = msg.lower()
        
        factual_keywords = [
            "meteo", "tempo fa", "temperatura", "previsioni", "piove",
            "notizie", "notizia", "news", "successo oggi", "cosa è successo",
            "quanto costa", "quando è", "dove si trova", "come funziona",
            "cos'è", "cosa significa", "chi è", "traduzione", "calcola"
        ]
        
        return any(kw in msg_lower for kw in factual_keywords)

# Istanza globale della pipeline
pipeline = Pipeline()
