"""
EMOJI FILTER - Genesi Core v2
Filtro emoji SOLO per TTS, non per chat
Le emoji sono ammesse nel testo ma non lette dal TTS
"""

import re
from typing import Optional
from core.log import log

class EmojiFilter:
    """
    Filtro emoji per TTS
    - Le emoji sono ammesse nel testo di chat
    - Vengono rimosse SOLO prima del TTS
    - Nessun filtro pre-chat
    """
    
    def __init__(self):
        # Pattern emoji Unicode
        self.emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticon
            "\U0001F300-\U0001F5FF"  # simboli & pictogrammi
            "\U0001F680-\U0001F6FF"  # trasporti & simboli mappe
            "\U0001F1E0-\U0001F1FF"  # flag (iOS)
            "\U00002702-\U000027B0"  # simboli vari
            "\U000024C2-\U0001F251" 
            "]+", flags=re.UNICODE
        )
        
        # Pattern emoji testuali (es. :smile:, 😊)
        self.textual_emoji_pattern = re.compile(r":[a-z_]+:|😊|😎|😂|❤️|👍|👎|🎉|🔥|💯")
    
    def filter_for_tts(self, text: str) -> str:
        """
        Rimuovi emoji SOLO per TTS
        
        Args:
            text: Testo con possibili emoji
            
        Returns:
            Testo senza emoji per TTS
        """
        try:
            # Rimuovi emoji Unicode
            filtered = self.emoji_pattern.sub("", text)
            
            # Rimuovi emoji testuali
            filtered = self.textual_emoji_pattern.sub("", filtered)
            
            # Pulisci spazi multipli
            filtered = re.sub(r"\s+", " ", filtered).strip()
            
            log("EMOJI_FILTER_TTS", original_length=len(text), filtered_length=len(filtered))
            return filtered
            
        except Exception as e:
            log("EMOJI_FILTER_ERROR", error=str(e))
            return text  # Fallback: testo originale
    
    def allow_in_chat(self, text: str) -> str:
        """
        Permetti emoji nella chat - nessun filtro
        
        Args:
            text: Testo della chat
            
        Returns:
            Testo originale con emoji
        """
        log("EMOJI_ALLOW_CHAT", length=len(text))
        return text
    
    def has_emoji(self, text: str) -> bool:
        """
        Verifica se il testo contiene emoji
        
        Args:
            text: Testo da verificare
            
        Returns:
            True se contiene emoji
        """
        has_unicode = bool(self.emoji_pattern.search(text))
        has_textual = bool(self.textual_emoji_pattern.search(text))
        
        return has_unicode or has_textual
    
    def get_emoji_count(self, text: str) -> int:
        """
        Conta emoji nel testo
        
        Args:
            text: Testo da analizzare
            
        Returns:
            Numero di emoji trovate
        """
        unicode_count = len(self.emoji_pattern.findall(text))
        textual_count = len(self.textual_emoji_pattern.findall(text))
        
        return unicode_count + textual_count

# Istanza globale
emoji_filter = EmojiFilter()
