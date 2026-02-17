"""
Behavior Regulator Layer - Post-Processing LLM Responses
Sistema di regolazione comportamentale isolato e deterministico.
"""

import hashlib
from typing import List


class BehaviorRegulator:
    """
    Regolatore comportamentale per risposte LLM.
    
    Interviene post-processing per migliorare qualità conversazionale
    senza modificare architettura o routing.
    """
    
    def __init__(self):
        # Blacklist frasi -> sostituzioni
        self.blacklist_map = {
            "Un cambiamento importante": "È una decisione che pesa.",
            "Non posso decidere per te": "La scelta è tua.",
            "Forse stai attraversando": "Potrebbe essere che",
            "Non ho accesso diretto ai dati meteo": "Al momento non posso verificare il meteo.",
            "Me lo hai già detto": "Sì, lo ricordo.",
            "Lo so, me lo hai già detto": "Sì, lo hai già condiviso."
        }
        
        # Varianze apertura deterministiche
        self.opening_variants = [
            "A volte",
            "In certi casi",
            "Generalmente",
            "Di solito",
            "Spesso"
        ]
        
        # Saluti naturali per anti-meteo-saluto
        self.natural_greetings = [
            "Ciao! Come va?",
            "Ehi! Tutto bene?",
            "Ciao! Come stai?",
            "Salve! Come va oggi?",
            "Ciao! Come ti senti?"
        ]
    
    def regulate(self, response: str, user_id: str) -> str:
        """
        Regola la risposta LLM applicando tutte le regole.
        
        Args:
            response: Risposta LLM da regolare
            user_id: ID utente
            
        Returns:
            str: Risposta regolata
        """
        regulated = response
        
        # 1) Blacklist Frasi
        regulated = self._apply_blacklist(regulated)
        
        # 2) Varianza apertura
        regulated = self._apply_opening_variance(regulated)
        
        return regulated
    
    def _apply_anti_meteo_greeting(self, response: str, user_message: str) -> str:
        """Sostituisce risposte meteo quando c'è un saluto."""
        user_lower = user_message.lower()
        response_lower = response.lower()
        
        # Detect saluti
        greetings = ["ciao", "salve", "ehei", "buongiorno", "buonasera"]
        has_greeting = any(greeting in user_lower for greeting in greetings)
        
        # Detect meteo
        has_weather = any(word in response_lower for word in ["meteo", "tempo", "piove", "sole", "nuvoloso"])
        
        if has_greeting and has_weather:
            # Selezione deterministica basata su hash
            hash_val = int(hashlib.md5((user_message + response).encode()).hexdigest()[:8], 16)
            greeting_idx = hash_val % len(self.natural_greetings)
            return self.natural_greetings[greeting_idx]
        
        return response
    
    def _apply_blacklist(self, response: str) -> str:
        """Applica blacklist frasi."""
        regulated = response
        for blacklisted, replacement in self.blacklist_map.items():
            if blacklisted in regulated:
                regulated = regulated.replace(blacklisted, replacement)
        return regulated
    
    def _apply_anti_repeat(self, response: str, recent_responses: List[str]) -> str:
        """Previne ripetizioni con risposte recenti."""
        if not recent_responses:
            return response
        
        # Controlla similarity con ultime 5 risposte
        for recent in recent_responses[-5:]:
            if self._similarity(response, recent) > 0.85:
                # Modifica solo la frase iniziale
                sentences = response.split('. ')
                if sentences and len(sentences) > 1:
                    # Sostituisci solo la prima frase
                    hash_val = int(hashlib.md5((response + recent).encode()).hexdigest()[:8], 16)
                    variant_idx = hash_val % len(self.opening_variants)
                    new_opening = self.opening_variants[variant_idx]
                    sentences[0] = new_opening + sentences[0][len(sentences[0].split()[0]):]
                    return '. '.join(sentences)
                elif sentences:
                    # Se c'è solo una frase, aggiungi prefisso
                    hash_val = int(hashlib.md5(response.encode()).hexdigest()[:8], 16)
                    variant_idx = hash_val % len(self.opening_variants)
                    return self.opening_variants[variant_idx] + ", " + sentences[0]
        
        return response
    
    def _apply_opening_variance(self, response: str) -> str:
        """Applica varianza alle aperture problematiche."""
        problematic_openings = ["Forse", "Un ", "Non posso"]
        
        for opening in problematic_openings:
            if response.startswith(opening):
                # Selezione deterministica
                hash_val = int(hashlib.md5(response.encode()).hexdigest()[:8], 16)
                variant_idx = hash_val % len(self.opening_variants)
                replacement = self.opening_variants[variant_idx]
                return replacement + response[len(opening):]
        
        return response
    
    def _similarity(self, text1: str, text2: str) -> float:
        """Calcola similarity semplice basata su parole comuni."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
