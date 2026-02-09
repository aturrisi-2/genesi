"""
POST-LLM HUMAN FILTER
Filtra e sanifica risposte LLM per comportamento umano stabile
"""

import re
from typing import Dict, Optional

class PostLLMFilter:
    """
    FILTRO POST-LLM PER COMPORTAMENTO UMANO STABILE
    Rimuove contaminazioni linguistiche, teatralità e inappropriatenza
    """
    
    def __init__(self):
        # Pattern linguistici inappropriati
        self.inappropriate_patterns = [
            # Lingua non italiana
            r'\b(hola|hello|hey|hi|good morning|good evening)\b',
            r'\b(¿qué|what|how|why|when|where)\b',
            r'\b(thank you|thanks|gracias|merci)\b',
            r'\b(lo siento|sorry|excuse me)\b',
            r'\b(buenos días|good night)\b',
            r'\b(caridad|charity|amor|love)\b',
            r'\b(kiss|bacio|baci|beso|besos)\b',
            
            # Teatralità inappropriata
            r'\*[^*]*\*',  # Azioni tra asterischi
            r'\([^)]*\)',  # Azioni in parentesi
            r'\[[^\]]*\]',  # Azioni in quadre
            
            # Emoji
            r'[\U0001F600-\U0001F64F]',  # Emoticoni
            r'[\U0001F300-\U0001F5FF]',  # Simboli vari
            r'[\U0001F680-\U0001F6FF]',  # Trasporti e simboli
            r'[\U0001F1E0-\U0001F1FF]',  # Bandiere
            
            # Affermazioni mediche inappropriate
            r'\b(non preoccuparti|tranquillo|calmati)\b',
            r'\b(stai bene|sarai tutto bene|ti guarirò)\b',
            r'\b(ho la soluzione|ti posso aiutare|posso curarti)\b',
            
            # Affermazioni affettive inappropriate in contesto medico
            r'\b(ti voglio bene|ti adoro|sei speciale)\b',
            r'\b(un bacio|un abbraccio|ti stringo)\b',
        ]
        
        # Fallback empatici per contesti specifici
        self.empathetic_fallbacks = {
            "medical_distress": [
                "Mi dispiace che tu stia male. Se il dolore è intenso o persistente, è importante consultare un medico.",
                "Capisco che ti preoccupi. Per problemi di salute è sempre meglio rivolgersi a un professionista.",
                "Sento che questo momento è difficile. Non posso fare diagnosi, ma ti incoraggio a cercare aiuto medico se necessario."
            ],
            "emotional_distress": [
                "Mi dispiace che tu ti senta così. Possiamo restare un momento su questo, se vuoi.",
                "Capisco che questo sia un momento difficile. Sono qui per ascoltarti.",
                "Sento il peso di quello che stai vivendo. Non sei solo in questo."
            ],
            "general_fallback": [
                "Mi dispiace, non riesco a rispondere come vorrei in questo momento.",
                "Capisco la tua domanda, ma non ho una risposta adeguata ora.",
                "Mi dispiace, non posso aiutarti come meriti in questo momento."
            ]
        }
    
    def filter_response(self, response: str, context: Optional[Dict] = None) -> str:
        """
        FILTRA E SANIFICA RISPOSTA LLM
        
        Args:
            response: Risposta LLM originale
            context: Contesto della conversazione (intent, user state, etc.)
            
        Returns:
            Risposta filtrata e umana
        """
        if not response or not isinstance(response, str):
            return self._get_empathetic_fallback(context)
        
        original = response
        
        # 1. Rimuovi pattern inappropriati
        filtered = response
        for pattern in self.inappropriate_patterns:
            filtered = re.sub(pattern, '', filtered, flags=re.IGNORECASE)
        
        # 2. Pulisci spazi multipli
        filtered = re.sub(r'\s+', ' ', filtered).strip()
        
        # 3. Verifica se la risposta è ancora valida
        if len(filtered) < 10:  # Troppo corta dopo filtraggio
            return self._get_empathetic_fallback(context)
        
        # 4. Verifica contaminazione linguistica
        if self._has_language_contamination(filtered):
            return self._get_empathetic_fallback(context)
        
        # 5. Verifica appropriatezza contestuale
        if context and not self._is_contextually_appropriate(filtered, context):
            return self._get_empathetic_fallback(context)
        
        # Log del filtraggio
        if original != filtered:
            print(f"[POST_LLM_FILTER] Original: '{original[:50]}...'")
            print(f"[POST_LLM_FILTER] Filtered: '{filtered[:50]}...'")
        
        return filtered
    
    def _has_language_contamination(self, text: str) -> bool:
        """
        Verifica contaminazione linguistica
        """
        # Pattern per lingue non italiane
        non_italian_patterns = [
            r'\b(hello|hey|hi|what|how|why|when|where|thank|thanks|sorry|love|kiss)\b',
            r'\b(¿qué|hola|buenos|gracias|lo siento|caridad)\b'
        ]
        
        for pattern in non_italian_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _is_contextually_appropriate(self, text: str, context: Dict) -> bool:
        """
        Verifica appropriatezza contestuale
        """
        intent = context.get('intent', '')
        
        # Contesto medico: verifica appropriatezza
        if intent == 'medical_info':
            # Non deve contenere promesse o diagnosi
            inappropriate_medical = [
                r'\b(stai bene|sarai tutto bene|ti guarirò)\b',
                r'\b(ho la soluzione|posso curarti)\b'
            ]
            
            for pattern in inappropriate_medical:
                if re.search(pattern, text, re.IGNORECASE):
                    return False
        
        # Contesto emotivo: verifica empatia vs teatralità
        if intent == 'emotional_support':
            # Non deve essere teatrale
            if re.search(r'\*[^*]*\*', text):
                return False
        
        return True
    
    def _get_empathetic_fallback(self, context: Optional[Dict] = None) -> str:
        """
        GENERA FALLBACK EMPATICO CONTESTUALE
        """
        if not context:
            context = {}
        
        intent = context.get('intent', '')
        user_state = context.get('user_state', {})
        
        # Scegli fallback appropriato
        if intent == 'medical_info':
            return self._select_fallback(self.empathetic_fallbacks['medical_distress'])
        elif intent == 'emotional_support':
            return self._select_fallback(self.empathetic_fallbacks['emotional_distress'])
        else:
            return self._select_fallback(self.empathetic_fallbacks['general_fallback'])
    
    def _select_fallback(self, fallback_list: list) -> str:
        """
        Seleziona fallback dalla lista (semplice rotazione)
        """
        import hashlib
        import time
        
        # Semplice pseudo-casualità basata su tempo
        index = int(time.time()) % len(fallback_list)
        return fallback_list[index]

# Istanza globale
post_llm_filter = PostLLMFilter()
