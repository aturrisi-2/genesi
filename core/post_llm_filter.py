"""
POST-LLM HUMAN FILTER
Filtra e sanifica risposte LLM per comportamento umano stabile
"""

import re
from typing import Dict, Optional

from core.language_guard import language_guard

class PostLLMFilter:
    """
    FILTRO POST-LLM PER COMPORTAMENTO UMANO STABILE
    Rimuove contaminazioni linguistiche, teatralità e inappropriatenza
    """
    
    def __init__(self):
        # Pattern linguistici inappropriati - FORZATO
        self.inappropriate_patterns = [
            # TUTTO l'inglese - ZERO TOLLERANZA
            r'\b(the|and|for|are|but|not|you|all|can|had|her|was|one|our|out|day|get|has|him|his|how|man|new|now|old|see|two|way|who|boy|did|its|let|put|say|she|too|use)\b',
            r'\b(hello|hey|hi|good morning|good evening|good afternoon|good night|good bye|bye|goodbye)\b',
            r'\b(what|how|why|when|where|who|which|where|when|why|what|who)\b',
            r'\b(thank you|thanks|gracias|merci|thank|thx|please|sorry|excuse me|pardon|forgive)\b',
            r'\b(amazing|awesome|great|wonderful|fantastic|perfect|excellent|really|actually|literally|basically|seriously|definitely)\b',
            r'\b(february|january|march|april|may|june|july|august|september|october|november|december)\b',
            r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
            r'\b(adjusts|smile|wink|giggle|laugh|frown|nod|shrug|stares|looks|glances|peers)\b',
            r'\b(caridad|charity|amor|love|like|enjoy|kiss|bacio|baci|beso|besos|hug|cuddle)\b',
            r'\b(hola|¿qué|lo siento|buenos días|adiós|hasta luego)\b',
            
            # Teatralità - ELIMINAZIONE COMPLETA
            r'\*[^*]*\*',  # Azioni tra asterischi
            r'\([^)]*\)',  # Azioni in parentesi
            r'\[[^\]]*\]',  # Azioni in quadre
            r'\{[^}]*\}',  # Azioni in graffe
            
            # RIMOSSO: Emoji e simboli - PERMESSI in display_text
            # Le emoji vengono gestite da sanitize_for_tts() solo per TTS
            # r'[\U0001F600-\U0001F64F]',  # Emoticoni
            # r'[\U0001F300-\U0001F5FF]',  # Simboli vari
            # r'[\U0001F680-\U0001F6FF]',  # Trasporti e simboli
            # r'[\U0001F1E0-\U0001F1FF]',  # Bandiere
            # r'[\U00002600-\U000026FF]',  # Simboli vari
            # r'[\U00002700-\U000027BF]',  # Dingbats
            
            # Affermazioni mediche inappropriate
            r'\b(non preoccuparti|tranquillo|calmati|relax)\b',
            r'\b(stai bene|sarai tutto bene|ti guarirò|guarirai)\b',
            r'\b(ho la soluzione|ti posso aiutare|posso curarti)\b',
            r'\b(non ti preoccupare|non ti preoccupare)\b',
            
            # Affermazioni affettive inappropriate
            r'\b(ti voglio bene|ti adoro|sei speciale)\b',
            r'\b(un bacio|un abbraccio|ti stringo)\b',
            r'\b(carissimo|carissima|tesoro|dolcezza)\b',
            
            # Descrizioni teatrali
            r'\b(esprime|mostra|manifesta|dimostra)\b',
            r'\b(curioso|interessato|sorpreso|scioccato)\b',
            r'\b(adotta|assume|indossa)\b',
            r'\b(festoso|entusiasta|eccitato)\b',
        ]
        
        # Fallback costruttivi - MAI "Mi dispiace"
        self.fallback_responses = {
            "identity": [
                "Sono Genesi, la tua assistente personale.",
                "Sono qui per aiutarti.",
                "Genesi al tuo servizio."
            ],
            "emotional_distress": [
                "Sono qui con te. Non sei solo.",
                "Posso aiutarti in questo momento difficile.",
                "Ascolto quello che stai vivendo."
            ],
            "general_fallback": [
                "Cerchiamo di affrontare questo insieme.",
                "Possiamo trovare una soluzione.",
                "Sono qui per supportarti."
            ]
        }
    
    def filter_response(self, response: str, context: Optional[Dict] = None) -> str:
        """
        FILTRA E SANIFICA RISPOSTA LLM - CON LANGUAGE GUARD
        
        Args:
            response: Risposta LLM originale
            context: Contesto della conversazione (intent, user state, etc.)
            
        Returns:
            Risposta filtrata e umana o fallback solo se necessario
        """
        if not response or not isinstance(response, str):
            return self._get_empathetic_fallback(context)
        
        # Usa language_guard centralizzato
        guard_result = language_guard.check_and_clean(response, context)
        
        if guard_result["is_clean"]:
            # Testo pulito, ritorna direttamente
            print(f"[POST_LLM_FILTER] CLEAN: '{response[:50]}...'", flush=True)
            return guard_result["cleaned_text"]
        
        # Testo contaminato, tenta rigenerazione
        print(f"[POST_LLM_FILTER] CONTAMINATED: {guard_result['issues']}", flush=True)
        
        # Aggiungi user_message al context per la rigenerazione
        if context:
            context["user_message"] = context.get("user_message", "")
        
        regenerated = self._attempt_regeneration(context, response)
        
        if regenerated and regenerated != self._get_empathetic_fallback(context):
            print(f"[POST_LLM_FILTER] REGENERATED: '{regenerated[:50]}...'", flush=True)
            return regenerated
        else:
            print(f"[POST_LLM_FILTER] FALLBACK: All attempts failed", flush=True)
            return self._get_empathetic_fallback(context)
    
    def _attempt_regeneration(self, context: Optional[Dict], original_response: str) -> str:
        """
        Tenta di rigenerare la risposta usando language_guard
        """
        try:
            # Usa language_guard per generare risposta semplice
            if context:
                simple_response = language_guard.generate_simple_response(context)
                if simple_response:
                    return simple_response
        except Exception as e:
            print(f"[POST_LLM_FILTER] Regeneration failed: {e}", flush=True)
        
        # Solo se tutto fallisce, fallback
        return self._get_empathetic_fallback(context)
    
    def _generate_simple_historical_response(self, message: str) -> str:
        """
        Genera risposta storica semplice in italiano
        """
        message_lower = message.lower()
        
        # Pattern comuni per persone storiche
        if "chi è" in message_lower or "chi era" in message_lower:
            if "napoleone" in message_lower:
                return "Napoleone Bonaparte fu un imperatore francese che conquisto gran parte dell'Europa nei primi anni dell'Ottocento."
            elif "alessandro" in message_lower and "magno" in message_lower:
                return "Alessandro Magno fu un re macedone che creò il più grande impero del mondo antico, conquistando persino l'impero persiano."
            elif "giulio cesare" in message_lower:
                return "Giulio Cesare fu un generale e statista romano che giocò un ruolo cruciale nella transizione dalla Repubblica all'Impero."
        
        return None
    
    def _has_any_contamination(self, text: str) -> bool:
        """
        Verifica contaminazione FORZATA - ZERO TOLLERANZA
        """
        # Qualsiasi asterisco, parentesi, quadra, graffa
        if '*' in text or '(' in text or '[' in text or '{' in text:
            return True
        
        # Qualsiasi emoji
        if any(ord(char) >= 0x1F600 and ord(char) <= 0x1F64F for char in text):
            return True
        
        # Qualsiasi parola inglese comune - SOLO se predominante
        english_words = ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use', 'hello', 'what', 'how', 'why', 'when', 'where', 'who', 'which', 'thank', 'thanks', 'please', 'sorry', 'amazing', 'awesome', 'great', 'wonderful', 'fantastic', 'perfect', 'excellent', 'really', 'actually', 'literally', 'basically', 'seriously', 'definitely']
        
        words = text.lower().split()
        english_count = sum(1 for word in words if word in english_words)
        
        # Blocca solo se >30% delle parole sono inglesi
        if len(words) > 0 and (english_count / len(words)) > 0.3:
            return True
        
        return False
    
    def _is_pure_italian(self, text: str) -> bool:
        """
        Verifica che il testo sia italiano puro
        """
        # Caratteri italiani validi
        italian_chars = set('abcdefghijklmnopqrstuvwxyzàèéìíòóùABCDEFGHIJKLMNOPQRSTUVWXYZÀÈÉÌÍÒÓÙ\'.,!?;: ')
        
        for char in text:
            if char not in italian_chars:
                return False
        
        # Verifica che ci siano parole italiane
        italian_words = ['il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'uno', 'una', 'dei', 'degli', 'delle', 'del', 'dello', 'della', 'e', 'o', 'ma', 'per', 'con', 'su', 'da', 'in', 'a', 'che', 'chi', 'come', 'quando', 'dove', 'perché', 'non', 'si', 'no', 'sì', 'questo', 'quella', 'quello', 'questa', 'questi', 'quelle']
        
        words = text.lower().split()
        italian_count = sum(1 for word in words if word in italian_words)
        
        # Almeno 30% delle parole devono essere italiane
        return len(words) > 0 and (italian_count / len(words)) >= 0.3
    
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
