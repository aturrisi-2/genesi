"""
MEMORY RELEVANCE - Genesi Neural Memory v1
Sistema di calcolo rilevanza dinamica per memoria episodica
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from core.storage import storage

logger = logging.getLogger(__name__)

class MemoryRelevance:
    """
    Memory Relevance - Calcolo dinamico rilevanza episodi
    Adatta soglie in base a frequenza conversazionale e patterns utente
    """
    
    def __init__(self):
        self.base_threshold = 0.3
        self.adaptive_factor = 0.1  # Fattore adattamento soglia
        self.conversation_frequency_window = 7  # Giorni per calcolo frequenza
        logger.info("MEMORY_RELEVANCE_INIT", extra={"base_threshold": self.base_threshold})
    
    async def calculate_dynamic_relevance(self, user_id: str, message: str, emotion: Dict[str, Any], 
                                         context: Dict[str, Any]) -> float:
        """
        Calcola rilevanza dinamica con soglia adattiva
        
        Args:
            user_id: ID utente
            message: Messaggio utente
            emotion: Dati emotivi
            context: Contesto conversazionale
            
        Returns:
            Score rilevanza 0.0-1.0
        """
        try:
            # Calcolo base relevance
            base_score = await self._calculate_base_relevance(message, emotion, context)
            
            # Adattamento soglia per utente
            user_threshold = await self._get_adaptive_threshold(user_id)
            
            # Boost per patterns speciali
            pattern_boost = await self._calculate_pattern_boost(user_id, message, context)
            
            # Score finale
            final_score = base_score + pattern_boost
            
            logger.info("DYNAMIC_RELEVANCE_CALCULATED", extra={
                "user_id": user_id,
                "base_score": base_score,
                "user_threshold": user_threshold,
                "pattern_boost": pattern_boost,
                "final_score": final_score
            })
            
            return min(1.0, max(0.0, final_score))
            
        except Exception as e:
            logger.error("DYNAMIC_RELEVANCE_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return 0.0
    
    async def _calculate_base_relevance(self, message: str, emotion: Dict[str, Any], 
                                      context: Dict[str, Any]) -> float:
        """
        Calcolo base relevance senza adattamento
        
        Args:
            message: Messaggio
            emotion: Dati emotivi
            context: Contesto
            
        Returns:
            Score base 0.0-1.0
        """
        score = 0.0
        
        # 1️⃣ Intensità emotiva (35%)
        emotion_intensity = emotion.get("intensity", 0.0)
        emotion_type = emotion.get("emotion", "neutral")
        
        if emotion_type != "neutral":
            # Emozioni forti hanno score più alto
            emotion_multiplier = {
                "joy": 1.2,
                "sadness": 1.3,
                "anger": 1.4,
                "fear": 1.5,
                "surprise": 1.1,
                "disgust": 1.2
            }.get(emotion_type, 1.0)
            
            score += (emotion_intensity * emotion_multiplier) * 0.35
        
        # 2️⃣ Novità informativa (30%)
        novelty_score = self._calculate_novelty_score(message, context)
        score += novelty_score * 0.30
        
        # 3️⃣ Impatto relazionale (25%)
        relational_impact = self._calculate_relational_impact(context)
        score += relational_impact * 0.25
        
        # 4️⃣ Complessità cognitiva (10%)
        complexity_score = self._calculate_cognitive_complexity(message, context)
        score += complexity_score * 0.10
        
        return min(1.0, score)
    
    async def _get_adaptive_threshold(self, user_id: str) -> float:
        """
        Calcola soglia adattiva per utente
        
        Args:
            user_id: ID utente
            
        Returns:
            Soglia adattiva 0.0-1.0
        """
        try:
            # Analizza frequenza conversazionale
            conversation_stats = await self._get_conversation_stats(user_id)
            
            # Utenti attivi richiedono soglia più alta (selettività)
            # Utenti occasionali richiedono soglia più bassa (inclusività)
            
            daily_avg = conversation_stats.get("daily_average", 0)
            
            if daily_avg >= 10:  # Utente molto attivo
                adaptive_threshold = self.base_threshold + 0.2
            elif daily_avg >= 5:  # Utente attivo
                adaptive_threshold = self.base_threshold + 0.1
            elif daily_avg >= 2:  # Utente moderato
                adaptive_threshold = self.base_threshold
            else:  # Utente occasionale
                adaptive_threshold = max(0.1, self.base_threshold - 0.1)
            
            logger.info("ADAPTIVE_THRESHOLD_CALCULATED", extra={
                "user_id": user_id,
                "daily_avg": daily_avg,
                "adaptive_threshold": adaptive_threshold
            })
            
            return adaptive_threshold
            
        except Exception as e:
            logger.error("ADAPTIVE_THRESHOLD_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return self.base_threshold
    
    async def _calculate_pattern_boost(self, user_id: str, message: str, context: Dict[str, Any]) -> float:
        """
        Calcola boost per patterns speciali
        
        Args:
            user_id: ID utente
            message: Messaggio
            context: Contesto
            
        Returns:
            Boost score 0.0-0.3
        """
        boost = 0.0
        
        try:
            # Pattern di prima interazione
            if await self._is_first_interaction(user_id):
                boost += 0.2
                logger.info("FIRST_INTERACTION_BOOST", extra={"user_id": user_id})
            
            # Pattern di condivisione personale
            if self._contains_personal_sharing(message):
                boost += 0.15
                logger.info("PERSONAL_SHARING_BOOST", extra={"user_id": user_id})
            
            # Pattern di domanda profonda
            if self._contains_deep_question(message):
                boost += 0.1
                logger.info("DEEP_QUESTION_BOOST", extra={"user_id": user_id})
            
            # Pattern di evento significativo
            if self._contains_significant_event(message, context):
                boost += 0.25
                logger.info("SIGNIFICANT_EVENT_BOOST", extra={"user_id": user_id})
            
            return min(0.3, boost)
            
        except Exception as e:
            logger.error("PATTERN_BOOST_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return 0.0
    
    def _calculate_novelty_score(self, message: str, context: Dict[str, Any]) -> float:
        """
        Calcola novità informativa del messaggio
        
        Args:
            message: Messaggio
            context: Contesto
            
        Returns:
            Score novità 0.0-1.0
        """
        novelty = 0.0
        
        # Lunghezza messaggio indica complessità
        message_length = len(message)
        if message_length > 100:
            novelty += 0.3
        elif message_length > 50:
            novelty += 0.2
        
        # Presenza di numeri/date indica informazioni specifiche
        import re
        if re.search(r'\d+', message):
            novelty += 0.2
        
        # Domande indicano ricerca informazioni
        if '?' in message:
            novelty += 0.1
        
        # Parole chiave informative
        informative_words = ["nuovo", "prima volta", "mai", "appena", "recentemente", "scoperto"]
        message_lower = message.lower()
        for word in informative_words:
            if word in message_lower:
                novelty += 0.1
                break
        
        return min(1.0, novelty)
    
    def _calculate_relational_impact(self, context: Dict[str, Any]) -> float:
        """
        Calcola impatto relazionale del messaggio
        
        Args:
            context: Contesto
            
        Returns:
            Score impatto 0.0-1.0
        """
        impact = 0.0
        
        # Intent relazionali hanno impatto alto
        relational_intents = ["relational", "greeting", "identity", "how_are_you", "goodbye", "help"]
        if context.get("intent") in relational_intents:
            impact += 0.4
        
        # Domande personali aumentano impatto
        if context.get("is_personal_question", False):
            impact += 0.3
        
        # Espressioni emotive aumentano impatto
        if context.get("has_emotional_expression", False):
            impact += 0.2
        
        # Riferimenti a conversazioni passate
        if context.get("references_past", False):
            impact += 0.1
        
        return min(1.0, impact)
    
    def _calculate_cognitive_complexity(self, message: str, context: Dict[str, Any]) -> float:
        """
        Calcola complessità cognitiva del messaggio
        
        Args:
            message: Messaggio
            context: Contesto
            
        Returns:
            Score complessità 0.0-1.0
        """
        complexity = 0.0
        
        # Frasi complesse (multiple clausole)
        if message.count(',') >= 2:
            complexity += 0.3
        
        # Parole astratte/concettuali
        abstract_words = ["pensiero", "idea", "sentimento", "emozione", "concetto", "teoria", "filosofia"]
        message_lower = message.lower()
        for word in abstract_words:
            if word in message_lower:
                complexity += 0.2
                break
        
        # Domande complesse (why, how)
        if any(word in message_lower for word in ["perché", "come", "per quale motivo"]):
            complexity += 0.2
        
        # Espressioni di opinione/giudizio
        opinion_words = ["penso che", "secondo me", "credo che", "mi sembra"]
        for word in opinion_words:
            if word in message_lower:
                complexity += 0.1
                break
        
        return min(1.0, complexity)
    
    async def _get_conversation_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Ottieni statistiche conversazione utente
        
        Args:
            user_id: ID utente
            
        Returns:
            Statistiche conversazione
        """
        try:
            # Recupera episodi recenti per calcolo frequenza
            from core.episodic_memory import episodic_memory
            episodes = await episodic_memory.get_relevant_episodes(user_id, limit=100)
            
            if not episodes:
                return {"daily_average": 0, "total_episodes": 0}
            
            # Calcola frequenza negli ultimi N giorni
            cutoff_date = datetime.now() - timedelta(days=self.conversation_frequency_window)
            recent_episodes = [
                ep for ep in episodes 
                if datetime.fromisoformat(ep["timestamp"]) > cutoff_date
            ]
            
            daily_average = len(recent_episodes) / self.conversation_frequency_window
            
            return {
                "daily_average": daily_average,
                "total_episodes": len(episodes),
                "recent_episodes": len(recent_episodes)
            }
            
        except Exception as e:
            logger.error("CONVERSATION_STATS_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return {"daily_average": 0, "total_episodes": 0}
    
    async def _is_first_interaction(self, user_id: str) -> bool:
        """
        Verifica se è prima interazione utente
        
        Args:
            user_id: ID utente
            
        Returns:
            True se prima interazione
        """
        try:
            from core.episodic_memory import episodic_memory
            episodes = await episodic_memory.get_relevant_episodes(user_id, limit=1)
            return len(episodes) == 0
            
        except Exception as e:
            logger.error("FIRST_INTERACTION_CHECK_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return False
    
    def _contains_personal_sharing(self, message: str) -> bool:
        """
        Verifica se messaggio contiene condivisione personale
        
        Args:
            message: Messaggio
            
        Returns:
            True se contiene condivisione personale
        """
        personal_patterns = [
            r"mi sento",
            r"ho provato",
            r"penso di",
            r"secondo me",
            r"la mia esperienza",
            r"personalmente",
            r"per me",
            r"io vivo",
            r"la mia vita"
        ]
        
        import re
        for pattern in personal_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True
        
        return False
    
    def _contains_deep_question(self, message: str) -> bool:
        """
        Verifica se messaggio contiene domanda profonda
        
        Args:
            message: Messaggio
            
        Returns:
            True se contiene domanda profonda
        """
        deep_question_patterns = [
            r"perché",
            r"come mai",
            r"qual è il senso",
            r"cosa ne pensi",
            r"secondo te",
            r"che ne dici"
        ]
        
        import re
        for pattern in deep_question_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True
        
        return False
    
    def _contains_significant_event(self, message: str, context: Dict[str, Any]) -> bool:
        """
        Verifica se messaggio descrive evento significativo
        
        Args:
            message: Messaggio
            context: Contesto
            
        Returns:
            True se evento significativo
        """
        significant_patterns = [
            r"è successo",
            r"ho appena",
            r"finalmente",
            r"dopo tanto tempo",
            r"per la prima volta",
            r"non ho mai",
            r"è cambiato",
            r"ho deciso"
        ]
        
        import re
        for pattern in significant_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True
        
        return False

# Istanza globale singleton
memory_relevance = MemoryRelevance()
