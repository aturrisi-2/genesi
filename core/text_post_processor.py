"""
POST-PROCESSOR LINGUISTICO - Pulizia output per TTS e frontend
Rimuove metatesto teatrale, emoji, azioni sceniche e marcatori non vocali
"""

import re
from typing import Dict

class TextPostProcessor:
    """
    POST-PROCESSOR DETERMINISTICO PER OUTPUT LINGUISTICO
    Trasforma output LLM espressivo in testo parlato umano pulito
    """
    
    def __init__(self):
        # Pattern regex per rimuovere elementi non vocali
        self.patterns = [
            # Azioni tra asterischi: *adjusts sunglasses*, *adotta un tono*
            (r'\*[^*]*\*', ''),
            
            # Emoji Unicode (range principali)
            (r'[\U0001F600-\U0001F64F]', ''),  # Emoticon
            (r'[\U0001F300-\U0001F5FF]', ''),  # Simboli vari
            (r'[\U0001F680-\U0001F6FF]', ''),  # Transport e map
            (r'[\U0001F1E0-\U0001F1FF]', ''),  # Flag (inclusi)
            (r'[\U00002702-\U000027B0]', ''),  # Simboli vari
            (r'[\U000024C2-\U0001F251]', ''),  # Simboli vari
            
            # Descrizioni azioni in parentesi o quadre
            (r'\([^)]*\*(?:[^)]*\*)*[^)]*\)', ''),  # (azioni con *)
            (r'\[[^\]]*\*[^\]]*\]', ''),  # [azioni con *]
            (r'\([^)]*\)', ''),  # qualsiasi parentesi (fallback)
            
            # Virgolette narrative e descrizioni
            (r'"[^"]*\*[^"]*"[^"]*"', ''),  # "testo *azione* testo"
            
            # Punteggiatura multipla e spazi eccessivi
            (r'[.]{3,}', '.'),  # ... → .
            (r'[!]{2,}', '!'),  # !! → !
            (r'[?]{2,}', '?'),  # ?? → ?
            (r'\s+', ' '),  # spazi multipli → singolo
        ]
        
        # Pattern finali di pulizia
        self.cleanup_patterns = [
            (r'\s*\.\s*', '. '),  # spazi attorno a punti
            (r'\s*!\s*', '! '),  # spazi attorno a esclamazioni
            (r'\s*\?\s*', '? '),  # spazi attorno a interrogazioni
            (r'\s+$', ''),  # spazi finali
            (r'^\s+', ''),  # spazi iniziali
        ]
    
    def clean_response(self, text: str) -> str:
        """
        PULISCE IL TESTO DA METATESTO E ELEMENTI NON VOCALI
        Applicazione DETERMINISTICA e SILENZIOSA
        
        Args:
            text: Testo grezzo dall'LLM (potrebbe contenere metatesto)
            
        Returns:
            Testo pulito per TTS e frontend
        """
        if not text or not isinstance(text, str):
            return text
        
        original = text
        cleaned = text
        
        # 1. Rimuovi pattern principali (azioni, emoji, ecc.)
        for pattern, replacement in self.patterns:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.UNICODE)
        
        # 2. Pulizia finale della punteggiatura e spazi
        for pattern, replacement in self.cleanup_patterns:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.UNICODE)
        
        # 3. Verifica integrità (non deve essere vuoto se originale non era vuoto)
        if original.strip() and not cleaned.strip():
            # Fallback: rimuovi solo asterischi ed emoji più evidenti
            cleaned = re.sub(r'\*[^*]*\*', '', original)
            cleaned = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF]', '', cleaned)
            cleaned = cleaned.strip()
        
        return cleaned.strip()
    
    def process_api_response(self, response_data: Dict) -> Dict:
        """
        Processa una risposta API completa pulendo il campo testuale
        
        Args:
            response_data: Dizionario risposta API (con campo "response" o "final_text")
            
        Returns:
            Dizionario con testo pulito
        """
        # Copia per non modificare original
        processed = response_data.copy()
        
        # Pulisci il campo di risposta principale
        for field in ["response", "final_text", "text"]:
            if field in processed and processed[field]:
                processed[field] = self.clean_response(processed[field])
        
        return processed

# Istanza globale per uso in tutto il progetto
text_post_processor = TextPostProcessor()
