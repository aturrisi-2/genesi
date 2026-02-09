"""
LANGUAGE GUARD - Blocco duro centralizzato per lingua italiana
Impedisce qualsiasi risposta in inglese o con contaminazioni linguistiche
"""

import re
from typing import Dict, Optional

class LanguageGuard:
    """
    GUARDIA LINGUISTICA CENTRALIZZATA
    - Blocca inglese
    - Forza italiano
    - Rigenera se necessario
    """
    
    def __init__(self):
        # Pattern inglese aggressivi
        self.english_patterns = [
            # Parole comuni - blocco se >20%
            r'\b(the|and|for|are|but|not|you|all|can|had|her|was|one|our|out|day|get|has|him|his|how|man|new|now|old|see|two|way|who|boy|did|its|let|put|say|she|too|use)\b',
            # Saluti e frasi comuni
            r'\b(hello|hey|hi|good morning|good evening|good afternoon|good night|good bye|bye|goodbye)\b',
            # Domande
            r'\b(what|how|why|when|where|who|which|where|when|why|what|who)\b',
            # Ringraziamenti
            r'\b(thank you|thanks|gracias|merci|thank|thx|please|sorry|excuse me|pardon|forgive)\b',
            # Aggettivi e avverbi comuni
            r'\b(amazing|awesome|great|wonderful|fantastic|perfect|excellent|really|actually|literally|basically|seriously|definitely)\b',
            # Mesi e giorni
            r'\b(february|january|march|april|may|june|july|august|september|october|november|december)\b',
            r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
            # Azioni teatrali
            r'\b(adjusts|smile|wink|giggle|laugh|frown|nod|shrug|stares|looks|glances|peers)\b',
            # Altre lingue
            r'\b(hola|¿qué|lo siento|buenos días|adiós|hasta luego)\b',
        ]
        
        # Pattern teatrali
        self.theatrical_patterns = [
            r'\*[^*]*\*',  # Azioni tra asterischi
            r'\([^)]*\)',  # Azioni in parentesi
            r'\[[^\]]*\]',  # Azioni in quadre
            r'\{[^}]*\}',  # Azioni in graffe
        ]
        
        # Emoji ranges
        self.emoji_patterns = [
            r'[\U0001F600-\U0001F64F]',  # Emoticoni
            r'[\U0001F300-\U0001F5FF]',  # Simboli vari
            r'[\U0001F680-\U0001F6FF]',  # Trasporti e simboli
            r'[\U0001F1E0-\U0001F1FF]',  # Bandiere
            r'[\U00002600-\U000026FF]',  # Simboli vari
            r'[\U00002700-\U000027BF]',  # Dingbats
        ]
    
    def check_and_clean(self, text: str, context: Optional[Dict] = None) -> Dict:
        """
        Verifica e pulisce il testo
        
        Returns:
            Dict con:
            - is_clean: bool
            - cleaned_text: str
            - issues: list
            - should_fallback: bool
        """
        if not text or not isinstance(text, str):
            return {
                "is_clean": False,
                "cleaned_text": "",
                "issues": ["empty_or_invalid"],
                "should_fallback": True
            }
        
        original = text
        cleaned = text
        issues = []
        
        # 1. Rimuovi pattern teatrali
        for pattern in self.theatrical_patterns:
            if re.search(pattern, cleaned, re.IGNORECASE):
                issues.append("theatrical_actions")
                cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # 2. Rimuovi emoji
        for pattern in self.emoji_patterns:
            if re.search(pattern, cleaned):
                issues.append("emoji")
                cleaned = re.sub(pattern, '', cleaned)
        
        # 3. Pulisci spazi
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # 4. Verifica contaminazione inglese
        english_ratio = self._get_english_ratio(cleaned)
        if english_ratio > 0.2:  # >20% inglese
            issues.append(f"english_contamination_{english_ratio:.0%}")
        
        # 5. Verifica caratteri validi
        if not self._has_valid_characters(cleaned):
            issues.append("invalid_characters")
        
        # 6. Verifica lunghezza
        if len(cleaned) < 3:
            issues.append("too_short")
        
        # Determina se è pulito
        is_clean = len(issues) == 0 and len(cleaned) >= 3
        
        # Determina se serve fallback
        should_fallback = not is_clean or english_ratio > 0.5
        
        return {
            "is_clean": is_clean,
            "cleaned_text": cleaned,
            "issues": issues,
            "should_fallback": should_fallback,
            "english_ratio": english_ratio,
            "original": original
        }
    
    def _get_english_ratio(self, text: str) -> float:
        """
        Calcola il rapporto di parole inglesi nel testo
        """
        if not text:
            return 0.0
        
        words = text.lower().split()
        if not words:
            return 0.0
        
        english_count = 0
        for pattern in self.english_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            english_count += len(matches)
        
        return english_count / len(words) if len(words) > 0 else 0.0
    
    def _has_valid_characters(self, text: str) -> bool:
        """
        Verifica che il testo abbia solo caratteri italiani validi
        """
        # Caratteri italiani validi
        italian_chars = set('abcdefghijklmnopqrstuvwxyzàèéìíòóùABCDEFGHIJKLMNOPQRSTUVWXYZÀÈÉÌÍÒÓÙ\'.,!?;: ')
        
        for char in text:
            if char not in italian_chars:
                return False
        
        return True
    
    def generate_simple_response(self, context: Optional[Dict]) -> str:
        """
        Genera una risposta semplice in italiano quando tutto fallisce
        """
        intent = context.get('intent', 'general') if context else 'general'
        message = context.get('user_message', '') if context else ''
        
        message_lower = message.lower()
        
        # Risposte semplici per intent comuni
        if intent == 'historical_info':
            if "napoleone" in message_lower:
                return "Napoleone fu un grande imperatore francese del XIX secolo."
            elif "alessandro" in message_lower and "magno" in message_lower:
                return "Alessandro Magno fu un conquistatore che creò un vasto impero."
            elif "giulio cesare" in message_lower:
                return "Giulio Cesare fu un importante generale e politico romano."
            else:
                return "Non posso fornire dettagli storici in questo momento."
        
        elif intent == 'medical_info':
            return "Per questioni mediche e sempre meglio consultare un professionista."
        
        elif intent == 'weather':
            return "Non riesco a ottenere informazioni meteo in questo momento."
        
        elif intent == 'news':
            return "Non posso accedere alle notizie in questo momento."
        
        elif intent == 'other':
            return "Non posso rispondere a questa domanda in questo momento."
        
        # Fallback generico
        return "Mi dispiace, non posso aiutarti con questa richiesta."

# Istanza globale
language_guard = LanguageGuard()
