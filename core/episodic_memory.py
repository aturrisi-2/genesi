"""
EPISODIC MEMORY - Genesi Neural Memory v1
Memoria episodica strutturata ispirata al funzionamento umano
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from core.storage import storage

logger = logging.getLogger(__name__)

class EpisodicMemory:
    """
    Episodic Memory - Sistema di memoria episodica neurale
    Filtra, salva e gestisce episodi conversazionali rilevanti
    """
    
    def __init__(self):
        self.min_relevance_score = 0.3  # Soglia dinamica iniziale
        self.max_episodes_per_user = 100  # Limite per evitare overflow
        logger.info("EPISODIC_MEMORY_INIT", extra={"status": "ready", "min_relevance": self.min_relevance_score})
    
    async def create_episode(self, user_id: str, message: str, emotion: Dict[str, Any], 
                           context: Dict[str, Any]) -> Optional[str]:
        """
        Crea episodio se rilevante
        
        Args:
            user_id: ID utente
            message: Messaggio utente
            emotion: Dati emotivi
            context: Contesto conversazionale
            
        Returns:
            Episode ID se salvato, None se scartato
        """
        try:
            # Calcolo rilevanza
            relevance_score = await self._calculate_relevance(user_id, message, emotion, context)
            
            if relevance_score < self.min_relevance_score:
                logger.info("EPISODE_DISCARDED", extra={
                    "user_id": user_id,
                    "relevance_score": relevance_score,
                    "min_relevance": self.min_relevance_score,
                    "reason": "low_relevance"
                })
                return None
            
            # Creazione episodio
            episode = {
                "id": f"episode_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_id[:8]}",
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "message": message[:200],  # Limitato per storage
                "synthesized_context": self._synthesize_context(context),
                "emotion": {
                    "emotion": emotion.get("emotion", "neutral"),
                    "intensity": emotion.get("intensity", 0.0)
                },
                "relevance_score": relevance_score,
                "semantic_tags": await self._extract_semantic_tags(message, context),
                "relational_engagement": self._calculate_relational_engagement(context),
                "decay_factor": 1.0  # Iniziale, decade nel tempo
            }
            
            # Salvataggio episodio
            await self._save_episode(user_id, episode)
            
            logger.info("EPISODE_CREATED", extra={
                "user_id": user_id,
                "episode_id": episode["id"],
                "relevance_score": relevance_score,
                "emotion": episode["emotion"]["emotion"]
            })
            
            return episode["id"]
            
        except Exception as e:
            logger.error("EPISODE_CREATE_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return None
    
    async def get_relevant_episodes(self, user_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Recupera episodi più rilevanti per utente
        
        Args:
            user_id: ID utente
            limit: Numero massimo episodi
            
        Returns:
            Lista episodi rilevanti ordinati per rilevanza
        """
        try:
            episodes = await storage.load(f"episodes/{user_id}", default=[])
            
            # Filtra per decay e ordina per rilevanza
            valid_episodes = []
            for episode in episodes:
                # Applica decay temporale
                decayed_relevance = episode["relevance_score"] * episode["decay_factor"]
                if decayed_relevance > 0.1:  # Soglia minima post-decay
                    episode["current_relevance"] = decayed_relevance
                    valid_episodes.append(episode)
            
            # Ordina per rilevanza corrente e limita
            valid_episodes.sort(key=lambda x: x["current_relevance"], reverse=True)
            return valid_episodes[:limit]
            
        except Exception as e:
            logger.error("EPISODE_RETRIEVE_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return []
    
    async def apply_decay(self, user_id: str):
        """
        Applica decadimento temporale agli episodi
        
        Args:
            user_id: ID utente
        """
        try:
            episodes = await storage.load(f"episodes/{user_id}", default=[])
            updated_episodes = []
            forgotten_count = 0
            
            for episode in episodes:
                # Calcolo decay basato su età
                episode_age = datetime.now() - datetime.fromisoformat(episode["timestamp"])
                days_old = episode_age.days
                
                # Decay formula: più vecchio = meno rilevante
                decay_factor = max(0.1, 1.0 - (days_old * 0.05))  # 5% al giorno
                episode["decay_factor"] = decay_factor
                
                # Rimuovi se sotto soglia minima
                if episode["relevance_score"] * decay_factor > 0.05:
                    updated_episodes.append(episode)
                else:
                    forgotten_count += 1
                    logger.info("EPISODE_FORGOTTEN", extra={
                        "user_id": user_id,
                        "episode_id": episode["id"],
                        "reason": "decay_below_threshold"
                    })
            
            # Salva episodi aggiornati
            await storage.save(f"episodes/{user_id}", updated_episodes)
            
            if forgotten_count > 0:
                logger.info("MEMORY_DECAY_APPLIED", extra={
                    "user_id": user_id,
                    "forgotten_count": forgotten_count,
                    "remaining_count": len(updated_episodes)
                })
            
        except Exception as e:
            logger.error("EPISODE_DECAY_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
    
    async def _calculate_relevance(self, user_id: str, message: str, emotion: Dict[str, Any], 
                                 context: Dict[str, Any]) -> float:
        """
        Calcola score di rilevanza per episodio
        
        Args:
            user_id: ID utente
            message: Messaggio
            emotion: Dati emotivi
            context: Contesto
            
        Returns:
            Score rilevanza 0.0-1.0
        """
        try:
            score = 0.0
            
            # 1️⃣ Intensità emotiva (30%)
            emotion_intensity = emotion.get("intensity", 0.0)
            if emotion.get("emotion") != "neutral":
                score += emotion_intensity * 0.3
            
            # 2️⃣ Novità informativa (25%)
            novelty_score = await self._calculate_novelty(user_id, message, context)
            score += novelty_score * 0.25
            
            # 3️⃣ Impatto relazionale (25%)
            relational_impact = self._calculate_relational_engagement(context)
            score += relational_impact * 0.25
            
            # 4️⃣ Coerenza con profilo (20%)
            coherence_score = await self._calculate_coherence(user_id, message, context)
            score += coherence_score * 0.2
            
            return min(1.0, max(0.0, score))
            
        except Exception as e:
            logger.error("RELEVANCE_CALC_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return 0.0
    
    def _synthesize_context(self, context: Dict[str, Any]) -> str:
        """
        Sintetizza contesto conversazionale
        
        Args:
            context: Contesto completo
            
        Returns:
            Contesto sintetizzato
        """
        try:
            synthesis_parts = []
            
            if context.get("intent"):
                synthesis_parts.append(f"Intent: {context['intent']}")
            
            if context.get("topic"):
                synthesis_parts.append(f"Topic: {context['topic']}")
            
            if context.get("previous_messages"):
                prev_count = len(context["previous_messages"])
                synthesis_parts.append(f"Context messages: {prev_count}")
            
            return " | ".join(synthesis_parts) if synthesis_parts else "General conversation"
            
        except Exception as e:
            logger.error("CONTEXT_SYNTHESIS_ERROR", exc_info=True, extra={"error": str(e)})
            return "Unknown context"
    
    async def _extract_semantic_tags(self, message: str, context: Dict[str, Any]) -> List[str]:
        """
        Estrae tag semantici dal messaggio
        
        Args:
            message: Messaggio utente
            context: Contesto
            
        Returns:
            Lista tag semantici
        """
        tags = []
        
        # Tag base da intent
        if context.get("intent"):
            tags.append(f"intent:{context['intent']}")
        
        # Tag da parole chiave
        message_lower = message.lower()
        
        personal_keywords = ["nome", "chiamo", "età", "città", "lavoro", "famiglia", "amico"]
        for keyword in personal_keywords:
            if keyword in message_lower:
                tags.append(f"personal:{keyword}")
        
        emotional_keywords = ["triste", "felice", "arrabbiato", "preoccupato", "contento"]
        for keyword in emotional_keywords:
            if keyword in message_lower:
                tags.append(f"emotional:{keyword}")
        
        return tags[:5]  # Limita numero tag
    
    def _calculate_relational_engagement(self, context: Dict[str, Any]) -> float:
        """
        Calcola coinvolgimento relazionale
        
        Args:
            context: Contesto conversazionale
            
        Returns:
            Score coinvolgimento 0.0-1.0
        """
        score = 0.0
        
        # Intent relazionali hanno score più alto
        relational_intents = ["relational", "greeting", "identity", "how_are_you"]
        if context.get("intent") in relational_intents:
            score += 0.5
        
        # Domande personali aumentano engagement
        if context.get("is_personal_question", False):
            score += 0.3
        
        # Lunghezza messaggio indica profondità
        message_length = context.get("message_length", 0)
        if message_length > 50:
            score += 0.2
        
        return min(1.0, score)
    
    async def _calculate_novelty(self, user_id: str, message: str, context: Dict[str, Any]) -> float:
        """
        Calcola novità informativa rispetto a episodi passati
        
        Args:
            user_id: ID utente
            message: Messaggio
            context: Contesto
            
        Returns:
            Score novità 0.0-1.0
        """
        try:
            # Recupera episodi recenti per confronto
            recent_episodes = await self.get_relevant_episodes(user_id, limit=10)
            
            if not recent_episodes:
                return 1.0  # Primo episodio = massimo novità
            
            # Calcolo similarità semplificato
            message_words = set(message.lower().split())
            
            max_similarity = 0.0
            for episode in recent_episodes:
                episode_words = set(episode["message"].lower().split())
                
                # Jaccard similarity
                intersection = len(message_words & episode_words)
                union = len(message_words | episode_words)
                
                if union > 0:
                    similarity = intersection / union
                    max_similarity = max(max_similarity, similarity)
            
            # Novità = 1 - similarità massima
            return 1.0 - max_similarity
            
        except Exception as e:
            logger.error("NOVELTY_CALC_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return 0.5  # Default moderate novelty
    
    async def _calculate_coherence(self, user_id: str, message: str, context: Dict[str, Any]) -> float:
        """
        Calcola coerenza con profilo utente
        
        Args:
            user_id: ID utente
            message: Messaggio
            context: Contesto
            
        Returns:
            Score coerenza 0.0-1.0
        """
        try:
            # Carica profilo utente
            from core.semantic_memory import semantic_memory
            profile = await semantic_memory.get_user_profile(user_id)
            
            if not profile:
                return 0.5  # Default senza profilo
            
            coherence_score = 0.0
            
            # Coerenza con nome
            if profile.get("name"):
                name_lower = profile["name"].lower()
                if name_lower in message.lower():
                    coherence_score += 0.3
            
            # Coerenza con città
            if profile.get("city"):
                city_lower = profile["city"].lower()
                if city_lower in message.lower():
                    coherence_score += 0.2
            
            # Coerenza con professione
            if profile.get("profession"):
                profession_lower = profile["profession"].lower()
                if profession_lower in message.lower():
                    coherence_score += 0.2
            
            return min(1.0, coherence_score)
            
        except Exception as e:
            logger.error("COHERENCE_CALC_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return 0.5
    
    async def _save_episode(self, user_id: str, episode: Dict[str, Any]):
        """
        Salva episodio nel storage
        
        Args:
            user_id: ID utente
            episode: Dati episodio
        """
        try:
            # Carica episodi esistenti
            episodes = await storage.load(f"episodes/{user_id}", default=[])
            
            # Aggiungi nuovo episodio
            episodes.append(episode)
            
            # Limita numero episodi
            if len(episodes) > self.max_episodes_per_user:
                # Rimuovi episodi meno rilevanti
                episodes.sort(key=lambda x: x["relevance_score"] * x["decay_factor"], reverse=True)
                episodes = episodes[:self.max_episodes_per_user]
                logger.info("EPISODES_LIMITED", extra={
                    "user_id": user_id,
                    "removed_count": len(episodes) - self.max_episodes_per_user
                })
            
            # Salva episodi aggiornati
            await storage.save(f"episodes/{user_id}", episodes)
            
        except Exception as e:
            logger.error("EPISODE_SAVE_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})

# Istanza globale singleton
episodic_memory = EpisodicMemory()
