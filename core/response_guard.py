"""
Response Guard - Post-Processing Response Validation and Rewrite
Sistema di protezione e miglioramento risposte LLM.
"""

import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class ResponseGuard:
    """
    Guardia per validazione e riscrittura risposte LLM.
    
    Interviene post-processing per garantire qualità e coerenza.
    """
    
    def __init__(self):
        # Pattern template da bloccare
        self.template_patterns = [
            "Non posso dirti cosa fare",
            "Mi dispiace sapere",
            "Non ho accesso",
            "Dimmi.",
            "Ok, l'ho capito",
            "Me lo hai già detto",
            "Stai ripetendo",
            "Non posso decidere per te",
            "Non riesco a controllare",
            "Lo so. Me lo hai detto"
        ]
        
        # Pattern passive-aggressive
        self.passive_aggressive_patterns = [
            r"Cosa cambi\?",
            r"Perché non.*\?",
            r"Dovresti.*",
            r"Non capisco perché.*",
            r"Se solo.*",
            r"Forse se.*"
        ]
        
        # Pattern tool leak
        self.tool_leak_patterns = [
            "servizio meteo",
            "non configurato",
            "non ho accesso ai dati",
            "API",
            "servizio notizie",
            "sistema",
            "backend"
        ]
    
    def validate_and_rewrite(self, response: str, context: Dict, user_id: str) -> str:
        """
        Valida e riscrive la risposta LLM.
        
        Args:
            response: Risposta LLM originale
            context: Contesto conversazionale
            user_id: ID utente
            
        Returns:
            str: Risposta validata e riscritta
        """
        if not response or not response.strip():
            return response
        
        rewritten = response
        modified = False
        
        # A. Template Blocker
        original = rewritten
        rewritten = self._block_templates(rewritten, context)
        if rewritten != original:
            logger.info("RESPONSE_GUARD_TEMPLATE_BLOCK user=%s", user_id)
            modified = True
        
        # B. Anti Passive-Aggressive
        original = rewritten
        rewritten = self._remove_passive_aggressive(rewritten)
        if rewritten != original:
            modified = True
        
        # C. Frasi Tronche
        original = rewritten
        rewritten = self._fix_incomplete_sentences(rewritten)
        if rewritten != original:
            modified = True
        
        # D. Tool Leak Protector
        original = rewritten
        rewritten = self._protect_tool_leaks(rewritten)
        if rewritten != original:
            logger.info("RESPONSE_GUARD_TOOL_BLOCK user=%s", user_id)
            modified = True
        
        # E. Anti Loop
        original = rewritten
        rewritten = self._prevent_loop(rewritten, context, user_id)
        if rewritten != original:
            modified = True
        
        if modified:
            logger.info("RESPONSE_GUARD_APPLIED user=%s", user_id)
        
        return rewritten
    
    def _block_templates(self, response: str, context: Dict) -> str:
        """Blocca e riscrive pattern template."""
        rewritten = response
        
        for pattern in self.template_patterns:
            if pattern in rewritten:
                # Estrai contesto per riscrittura coerente
                user_message = context.get("current_message", "").lower()
                
                # Riscritture specifiche basate sul contesto
                if "decidere" in pattern:
                    if "lavoro" in user_message or "cambiare" in user_message:
                        rewritten = rewritten.replace(pattern, "La scelta finale spetta a te.")
                    else:
                        rewritten = rewritten.replace(pattern, "La decisione è tua.")
                elif "dispiace" in pattern:
                    rewritten = rewritten.replace(pattern, "Capisco.")
                elif "accesso" in pattern:
                    rewritten = rewritten.replace(pattern, "Al momento non posso verificare.")
                elif "dimmi" in pattern:
                    rewritten = rewritten.replace(pattern, "Spiegami meglio.")
                elif "già detto" in pattern:
                    rewritten = rewritten.replace(pattern, "Sì, lo ricordo.")
                elif "ripetendo" in pattern:
                    rewritten = rewritten.replace(pattern, "Vediamo da un'altra angolazione.")
                else:
                    # Riscrittura generica
                    rewritten = rewritten.replace(pattern, "Procediamo diversamente.")
        
        return rewritten
    
    def _remove_passive_aggressive(self, response: str) -> str:
        """Rimuove toni passive-aggressive."""
        rewritten = response
        
        for pattern in self.passive_aggressive_patterns:
            if re.search(pattern, rewritten, re.IGNORECASE):
                # Sostituisci con tono neutro
                if "Cosa cambi" in rewritten:
                    rewritten = re.sub(pattern, "Cosa vorresti cambiare?", rewritten, flags=re.IGNORECASE)
                elif "Perché non" in rewritten:
                    rewritten = re.sub(pattern, "Cosa ti blocca?", rewritten, flags=re.IGNORECASE)
                elif "Dovresti" in rewritten:
                    rewritten = re.sub(pattern, "Potresti considerare", rewritten, flags=re.IGNORECASE)
                else:
                    # Rimuovi pattern problematico
                    rewritten = re.sub(pattern, "", rewritten, flags=re.IGNORECASE)
        
        return rewritten
    
    def _fix_incomplete_sentences(self, response: str) -> str:
        """Corregge frasi incomplete o tronche."""
        rewritten = response.strip()
        
        # Fix iniziale minuscola
        if rewritten and rewritten[0].islower():
            rewritten = rewritten[0].upper() + rewritten[1:]
        
        # Fix frasi che iniziano con "per "
        if rewritten.startswith("Per "):
            rewritten = "Per " + rewritten[4:]
        
        # Fix frasi tronche che terminano con punto senza soggetto chiaro
        sentences = rewritten.split('. ')
        fixed_sentences = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and not sentence.endswith('.'):
                # Controlla se è una frase completa
                if any(word in sentence.lower() for word in ['è', 'sono', 'hai', 'ho', 'può', 'posso']):
                    sentence += '.'
                elif len(sentence.split()) >= 3:
                    sentence += '.'
            
            if sentence:
                fixed_sentences.append(sentence)
        
        return '. '.join(fixed_sentences)
    
    def _protect_tool_leaks(self, response: str) -> str:
        """Protegge da leak tecnici del sistema."""
        rewritten = response
        
        for pattern in self.tool_leak_patterns:
            if pattern in rewritten:
                # Sostituisci con frasi naturali
                if "meteo" in pattern:
                    rewritten = rewritten.replace(pattern, "il tempo")
                elif "non configurato" in pattern:
                    rewritten = rewritten.replace(pattern, "non disponibile")
                elif "accesso ai dati" in pattern:
                    rewritten = rewritten.replace(pattern, "informazioni")
                elif "API" in pattern:
                    rewritten = rewritten.replace(pattern, "servizio")
                elif "sistema" in pattern or "backend" in pattern:
                    rewritten = rewritten.replace(pattern, "funzionalità")
        
        return rewritten
    
    def _prevent_loop(self, response: str, context: Dict, user_id: str) -> str:
        """Previne loop su ripetizioni utente."""
        # Estrai messaggi utente recenti dal contesto
        recent_messages = context.get("recent_messages", [])
        if not recent_messages:
            return response
        
        # Conta ripetizioni utente
        user_messages = [msg.get("content", "") for msg in recent_messages if msg.get("role") == "user"]
        if len(user_messages) < 3:
            return response
        
        # Controlla se l'ultimo messaggio è ripetuto
        last_message = user_messages[-1].strip().lower()
        repeat_count = sum(1 for msg in user_messages[-3:] if msg.strip().lower() == last_message)
        
        if repeat_count >= 2:
            # Se l'utente ripete, cambia angolazione
            if any(phrase in response.lower() for phrase in ["già detto", "lo so", "ripeti"]):
                # Riscrivi con approccio diverso
                if "lavoro" in last_message:
                    response = "Vediamo il problema da un'altra prospettiva."
                elif "stanco" in last_message:
                    response = "Forse c'è qualcosa che ti sta consumando."
                elif "ciao" in last_message:
                    response = "Ehi! Tutto bene?"
                else:
                    response = "Proviamo ad affrontarlo diversamente."
        
        return response
