"""
Context Signal Analyzer - Dynamic Conversation Behavior Analysis
Analizza segnali contestuali per migliorare il comportamento conversazionale.
"""

from collections import Counter
from typing import List, Dict


class ContextSignalAnalyzer:
    """
    Analizzatore di segnali contestuali per conversazioni dinamiche.
    
    Rileva pattern comportamentali e genera segnali per il regolatore.
    """
    
    def analyze(self, recent_user_messages: List[str]) -> Dict[str, bool]:
        """
        Analizza messaggi utente recenti per rilevare segnali.
        
        Args:
            recent_user_messages: Ultimi 5 messaggi utente
            
        Returns:
            Dict[str, bool]: Segnali comportamentali rilevati
        """
        signals = {
            "avoid_repetition_comment": False,
            "increase_variation": False,
            "tone_soften": False
        }
        
        if not recent_user_messages:
            return signals
        
        # Normalizza messaggi per analisi
        normalized_messages = [msg.lower().strip() for msg in recent_user_messages if msg.strip()]
        
        # 1) Rileva ripetizioni utente >= 3 volte
        message_counter = Counter(normalized_messages)
        repeated_messages = {msg: count for msg, count in message_counter.items() if count >= 3}
        
        if repeated_messages:
            signals["avoid_repetition_comment"] = True
            signals["increase_variation"] = True
            signals["tone_soften"] = True
        
        # 2) Rileva pattern di frustrazione o insoddisfazione
        frustration_keywords = [
            "non capisco", "non funziona", "non mi piace", 
            "fastidioso", "frustrante", "noioso", "ripetitivo",
            "sempre la stessa", "di nuovo", "ancora"
        ]
        
        frustration_count = sum(1 for msg in normalized_messages 
                              for keyword in frustration_keywords 
                              if keyword in msg)
        
        if frustration_count >= 2:
            signals["tone_soften"] = True
            signals["increase_variation"] = True
        
        # 3) Rileva domande ripetute o confusion
        question_words = ["come", "perché", "cosa", "dove", "quando", "chi"]
        question_count = sum(1 for msg in normalized_messages 
                           if any(qword in msg for qword in question_words))
        
        if question_count >= 3:
            signals["increase_variation"] = True
        
        return signals
