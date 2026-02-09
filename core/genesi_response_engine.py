"""
GENESI RESPONSE ENGINE
Genera risposte testuali FINALI basate su intent LLM
Nessun testo viene prodotto dall'LLM - solo intent strutturato
"""

import re
from typing import Dict, Optional

class GenesiResponseEngine:
    """
    MOTORE DI RISPOSTA DI GENESI
    Solo template hard-coded, basati su intent LLM
    """
    
    def __init__(self):
        # TEMPLATE HARD-CODED PER OGNI INTENT
        self.intent_templates = {
            "greeting": [
                "Ciao. Come posso aiutarti?",
                "Ciao. Sono qui per te.",
                "Salve. Dimmi pure.",
                "Buongiorno. Come posso aiutarti?"
            ],
            
            "physical_discomfort": [
                "Mi dispiace, non è piacevole sentirsi così. Vuoi raccontarmi meglio cosa stai provando?",
                "Capisco che il disagio fisico può essere difficile. Sono qui con te.",
                "Mi dispiace che tu stia male. Possiamo parlarne con calma.",
                "Il dolore fisico può essere davvero fastidioso. Ti ascolto."
            ],
            
            "emotional_distress": [
                "Capisco. Possiamo prenderci un momento e parlarne.",
                "Mi dispiace che ti senti così. Sono qui per te.",
                "Capisco come ti senti. Ti ascolto con attenzione.",
                "È normale sentirsi così a volte. Sono qui con te."
            ],
            
            "acknowledgment": [
                "Va bene.",
                "Capisco.",
                "Perfetto.",
                "Ok."
            ],
            
            "question": [
                "È una buona domanda. Fammi riflettere un momento.",
                "Interessante. Cerchiamo di capire insieme.",
                "Buona domanda. Vediamo come possiamo rispondere.",
                "Mi poni una domanda interessante. Dimmi di più."
            ],
            
            "farewell": [
                "Ci sentiamo presto.",
                "A presto.",
                "Ciao e prenditi cura di te.",
                "Arrivederci."
            ],
            
            "generic": [
                "Ti ascolto.",
                "Sono qui con te.",
                "Capisco.",
                "Dimmi di più."
            ]
        }
        
        # INTENT RICONOSCIUTI
        self.valid_intents = set(self.intent_templates.keys())
        
        # PATTERN PER IDENTIFICARE INTENT DAL TESTO LLM (fallback)
        self.intent_patterns = {
            "greeting": [r"ciao", r"salve", r"buongiorno", r"buonasera"],
            "physical_discomfort": [r"male", r"dolore", r"mal di testa", r"mal di pancia", r"fastidio"],
            "emotional_distress": [r"triste", r"giù", r"depresso", r"ansia", r"preoccupato"],
            "acknowledgment": [r"ok", r"va bene", r"capisco", r"certo"],
            "question": [r"\?", r"come", r"perché", r"quando", r"dove"],
            "farewell": [r"arrivederci", r"ciao", r"addio", r"a presto"]
        }

    def generate_response_from_intent(self, intent_data: Dict) -> Dict:
        """
        Genera risposta testuale FINALE basata su intent LLM
        """
        print(f"[GENESI_ENGINE] Processing intent: {intent_data}", flush=True)
        
        # Estrai intent e confidence
        intent = intent_data.get("intent", "generic").lower().strip()
        confidence = intent_data.get("confidence", 0.5)
        
        # Valida intent
        if intent not in self.valid_intents:
            print(f"[GENESI_ENGINE] Invalid intent '{intent}', using generic", flush=True)
            intent = "generic"
        
        # Seleziona template basato su intent
        templates = self.intent_templates[intent]
        
        # Scegli template (sempre lo stesso per coerenza, o random per varietà)
        import random
        if confidence > 0.7:
            # High confidence: usa sempre il primo template (più diretto)
            response_text = templates[0]
        else:
            # Low confidence: usa random per varietà
            response_text = random.choice(templates)
        
        # Pulisci e valida risposta
        cleaned_response = self._clean_response(response_text)
        
        result = {
            "final_text": cleaned_response,
            "confidence": "ok",
            "style": "standard",
            "intent": intent,
            "llm_confidence": confidence
        }
        
        print(f"[GENESI_ENGINE] Generated: '{cleaned_response}'", flush=True)
        return result

    def generate_response_from_text(self, llm_text: str) -> Dict:
        """
        Fallback: estrai intent da testo LLM e genera risposta
        SCARTA IL TESTO LLM, USA SOLO L'INTENT
        """
        print(f"[GENESI_ENGINE] Extracting intent from LLM text: '{llm_text[:100]}...'", flush=True)
        
        # Identifica intent basato su pattern nel testo
        detected_intent = self._detect_intent_from_text(llm_text)
        
        # Genera risposta basata su intent detected
        intent_data = {
            "intent": detected_intent,
            "confidence": 0.5  # Default confidence per text fallback
        }
        
        return self.generate_response_from_intent(intent_data)

    def _detect_intent_from_text(self, text: str) -> str:
        """
        Detect intent from LLM text using patterns
        """
        text_lower = text.lower().strip()
        
        # Controlla pattern per ogni intent
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    print(f"[GENESI_ENGINE] Detected intent '{intent}' from pattern '{pattern}'", flush=True)
                    return intent
        
        # Default fallback
        print(f"[GENESI_ENGINE] No pattern matched, using generic", flush=True)
        return "generic"

    def _clean_response(self, text: str) -> str:
        """
        Pulisci e valida risposta finale
        """
        if not text:
            return "Ti ascolto."
        
        # Rimuovi caratteri problematici
        text = re.sub(r'[^\w\sàèéìòùÀÈÉÌÒÙ.,!?\'-]', '', text)
        
        # Rimuovi spazi multipli
        text = re.sub(r'\s+', ' ', text)
        
        # Trim
        text = text.strip()
        
        # Assicura che non sia vuoto
        if not text:
            return "Ti ascolto."
        
        # Lunghezza massima
        if len(text) > 200:
            text = text[:197] + "..."
        
        return text

    def validate_llm_output(self, llm_output: str) -> bool:
        """
        Verifica che LLM non stia producendo testo finale
        """
        # Se contiene frasi complete, è vietato
        if len(llm_output.split()) > 5:
            print(f"[GENESI_ENGINE] LLM producing too much text: {len(llm_output.split())} words", flush=True)
            return False
        
        # Se contiene caratteri vietati
        forbidden_chars = ['*', '🥰', '😘', '💋', '💕', '💖']
        if any(char in llm_output for char in forbidden_chars):
            print(f"[GENESI_ENGINE] LLM contains forbidden characters", flush=True)
            return False
        
        return True

# Istanza globale del motore
genesi_engine = GenesiResponseEngine()
