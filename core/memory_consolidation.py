"""
MEMORY CONSOLIDATION - Genesi Neural Memory v1
Sistema di consolidamento memoria da episodica a lungo termine
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import Counter, defaultdict
from core.storage import storage

logger = logging.getLogger(__name__)

class MemoryConsolidation:
    """
    Memory Consolidation - Trasforma episodi in pattern e tratti persistenti
    Implementa consolidamento periodico e aggiornamento profilo utente
    """
    
    def __init__(self):
        self.consolidation_interval = 10  # Episodi prima del consolidamento
        self.pattern_threshold = 3  # Minimo occorrenze per creare pattern
        self.consolidation_window_days = 30  # Giorni considerati per consolidamento
        logger.info("MEMORY_CONSOLIDATION_INIT", extra={
            "consolidation_interval": self.consolidation_interval,
            "pattern_threshold": self.pattern_threshold
        })
    
    async def check_consolidation_needed(self, user_id: str) -> bool:
        """
        Verifica se è necessario consolidamento
        
        Args:
            user_id: ID utente
            
        Returns:
            True se consolidamento necessario
        """
        try:
            episodes = await storage.load(f"episodes/{user_id}", default=[])
            
            # Controlla numero episodi non consolidati
            unconsolidated_count = len([
                ep for ep in episodes 
                if not ep.get("consolidated", False)
            ])
            
            needed = unconsolidated_count >= self.consolidation_interval
            
            logger.info("CONSOLIDATION_CHECK", extra={
                "user_id": user_id,
                "unconsolidated_count": unconsolidated_count,
                "threshold": self.consolidation_interval,
                "consolidation_needed": needed
            })
            
            return needed
            
        except Exception as e:
            logger.error("CONSOLIDATION_CHECK_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return False
    
    async def consolidate_memory(self, user_id: str) -> Dict[str, Any]:
        """
        Esegue consolidamento memoria utente
        
        Args:
            user_id: ID utente
            
        Returns:
            Risultati consolidamento
        """
        try:
            logger.info("CONSOLIDATION_STARTED", extra={"user_id": user_id})
            
            # 1️⃣ Recupera episodi da consolidare
            episodes_to_consolidate = await self._get_episodes_to_consolidate(user_id)
            
            if not episodes_to_consolidate:
                logger.info("CONSOLIDATION_SKIPPED", extra={"user_id": user_id, "reason": "no_episodes"})
                return {"consolidated": 0, "patterns": 0, "traits": 0}
            
            # 2️⃣ Analizza e crea pattern
            patterns = await self._extract_patterns(episodes_to_consolidate)
            
            # 3️⃣ Estrae tratti personali
            traits = await self._extract_traits(episodes_to_consolidate)
            
            # 4️⃣ Aggiorna profilo utente
            await self._update_user_profile(user_id, patterns, traits)
            
            # 5️⃣ Marca episodi come consolidati
            await self._mark_episodes_consolidated(user_id, episodes_to_consolidate)
            
            # 6️⃣ Pulisci episodi vecchi e irrilevanti
            await self._cleanup_old_episodes(user_id)
            
            results = {
                "consolidated": len(episodes_to_consolidate),
                "patterns": len(patterns),
                "traits": len(traits),
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info("CONSOLIDATION_COMPLETED", extra={
                "user_id": user_id,
                **results
            })
            
            return results
            
        except Exception as e:
            logger.error("CONSOLIDATION_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return {"consolidated": 0, "patterns": 0, "traits": 0}
    
    async def _get_episodes_to_consolidate(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Recupera episodi da consolidare
        
        Args:
            user_id: ID utente
            
        Returns:
            Lista episodi da consolidare
        """
        try:
            episodes = await storage.load(f"episodes/{user_id}", default=[])
            
            # Filtra episodi non consolidati
            unconsolidated = [
                ep for ep in episodes 
                if not ep.get("consolidated", False)
            ]
            
            # Ordina per rilevanza
            unconsolidated.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            
            # Limita numero episodi per consolidamento
            return unconsolidated[:self.consolidation_interval]
            
        except Exception as e:
            logger.error("GET_EPISODES_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
            return []
    
    async def _extract_patterns(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Estrae pattern ricorrenti dagli episodi
        
        Args:
            episodes: Lista episodi
            
        Returns:
            Lista pattern identificati
        """
        patterns = []
        
        try:
            # 1️⃣ Pattern emotivi
            emotion_patterns = self._analyze_emotion_patterns(episodes)
            patterns.extend(emotion_patterns)
            
            # 2️⃣ Pattern tematici
            topic_patterns = self._analyze_topic_patterns(episodes)
            patterns.extend(topic_patterns)
            
            # 3️⃣ Pattern temporali
            temporal_patterns = self._analyze_temporal_patterns(episodes)
            patterns.extend(temporal_patterns)
            
            # 4️⃣ Pattern relazionali
            relational_patterns = self._analyze_relational_patterns(episodes)
            patterns.extend(relational_patterns)
            
            logger.info("PATTERNS_EXTRACTED", extra={
                "total_patterns": len(patterns),
                "emotion_patterns": len(emotion_patterns),
                "topic_patterns": len(topic_patterns),
                "temporal_patterns": len(temporal_patterns),
                "relational_patterns": len(relational_patterns)
            })
            
            return patterns
            
        except Exception as e:
            logger.error("PATTERNS_EXTRACTION_ERROR", exc_info=True, extra={"error": str(e)})
            return []
    
    def _analyze_emotion_patterns(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analizza pattern emotivi ricorrenti
        
        Args:
            episodes: Lista episodi
            
        Returns:
            Pattern emotivi
        """
        patterns = []
        
        # Conta occorrenze emozioni
        emotion_counts = Counter()
        emotion_intensity_sum = defaultdict(float)
        
        for episode in episodes:
            emotion = episode.get("emotion", {})
            emotion_type = emotion.get("emotion", "neutral")
            intensity = emotion.get("intensity", 0.0)
            
            emotion_counts[emotion_type] += 1
            emotion_intensity_sum[emotion_type] += intensity
        
        # Crea pattern per emozioni ricorrenti
        for emotion_type, count in emotion_counts.items():
            if count >= self.pattern_threshold and emotion_type != "neutral":
                avg_intensity = emotion_intensity_sum[emotion_type] / count
                
                pattern = {
                    "type": "emotion",
                    "emotion": emotion_type,
                    "frequency": count,
                    "average_intensity": avg_intensity,
                    "confidence": min(1.0, count / len(episodes)),
                    "created_at": datetime.now().isoformat()
                }
                patterns.append(pattern)
        
        return patterns
    
    def _analyze_topic_patterns(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analizza pattern tematici ricorrenti
        
        Args:
            episodes: Lista episodi
            
        Returns:
            Pattern tematici
        """
        patterns = []
        
        # Estrae tag semantici dagli episodi
        all_tags = []
        for episode in episodes:
            tags = episode.get("semantic_tags", [])
            all_tags.extend(tags)
        
        # Conta occorrenze tag
        tag_counts = Counter(all_tags)
        
        # Crea pattern per tag ricorrenti
        for tag, count in tag_counts.items():
            if count >= self.pattern_threshold:
                pattern = {
                    "type": "topic",
                    "tag": tag,
                    "frequency": count,
                    "confidence": min(1.0, count / len(episodes)),
                    "created_at": datetime.now().isoformat()
                }
                patterns.append(pattern)
        
        return patterns
    
    def _analyze_temporal_patterns(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analizza pattern temporali
        
        Args:
            episodes: Lista episodi
            
        Returns:
            Pattern temporali
        """
        patterns = []
        
        # Analizza orari conversazioni
        hour_counts = Counter()
        day_counts = Counter()
        
        for episode in episodes:
            timestamp = datetime.fromisoformat(episode["timestamp"])
            hour_counts[timestamp.hour] += 1
            day_counts[timestamp.strftime("%A")] += 1
        
        # Pattern orari
        for hour, count in hour_counts.items():
            if count >= self.pattern_threshold:
                pattern = {
                    "type": "temporal",
                    "subtype": "hourly",
                    "hour": hour,
                    "frequency": count,
                    "confidence": min(1.0, count / len(episodes)),
                    "created_at": datetime.now().isoformat()
                }
                patterns.append(pattern)
        
        # Pattern giornalieri
        for day, count in day_counts.items():
            if count >= self.pattern_threshold:
                pattern = {
                    "type": "temporal",
                    "subtype": "daily",
                    "day": day,
                    "frequency": count,
                    "confidence": min(1.0, count / len(episodes)),
                    "created_at": datetime.now().isoformat()
                }
                patterns.append(pattern)
        
        return patterns
    
    def _analyze_relational_patterns(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analizza pattern relazionali
        
        Args:
            episodes: Lista episodi
            
        Returns:
            Pattern relazionali
        """
        patterns = []
        
        # Analizza engagement relazionale
        engagement_scores = [ep.get("relational_engagement", 0) for ep in episodes]
        avg_engagement = sum(engagement_scores) / len(engagement_scores) if engagement_scores else 0
        
        if avg_engagement > 0.5:  # Soglia per pattern relazionale significativo
            pattern = {
                "type": "relational",
                "subtype": "engagement",
                "average_engagement": avg_engagement,
                "confidence": min(1.0, avg_engagement),
                "created_at": datetime.now().isoformat()
            }
            patterns.append(pattern)
        
        return patterns
    
    async def _extract_traits(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Estrae tratti personali dagli episodi
        
        Args:
            episodes: Lista episodi
            
        Returns:
            Tratti personali identificati
        """
        traits = []
        
        try:
            # 1️⃣ Tratto emotivo dominante
            dominant_emotion = self._extract_dominant_emotion_trait(episodes)
            if dominant_emotion:
                traits.append(dominant_emotion)
            
            # 2️⃣ Tratto comunicativo
            communication_trait = self._extract_communication_trait(episodes)
            if communication_trait:
                traits.append(communication_trait)
            
            # 3️⃣ Tratto temporale
            temporal_trait = self._extract_temporal_trait(episodes)
            if temporal_trait:
                traits.append(temporal_trait)
            
            # 4️⃣ Tratto relazionale
            relational_trait = self._extract_relational_trait(episodes)
            if relational_trait:
                traits.append(relational_trait)
            
            logger.info("TRAITS_EXTRACTED", extra={
                "total_traits": len(traits),
                "trait_types": [t["type"] for t in traits]
            })
            
            return traits
            
        except Exception as e:
            logger.error("TRAITS_EXTRACTION_ERROR", exc_info=True, extra={"error": str(e)})
            return []
    
    def _extract_dominant_emotion_trait(self, episodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Estrae tratto emotivo dominante
        
        Args:
            episodes: Lista episodi
            
        Returns:
            Tratto emotivo o None
        """
        emotion_counts = Counter()
        
        for episode in episodes:
            emotion = episode.get("emotion", {})
            emotion_type = emotion.get("emotion", "neutral")
            if emotion_type != "neutral":
                emotion_counts[emotion_type] += 1
        
        if not emotion_counts:
            return None
        
        # Emozione dominante
        dominant_emotion, count = emotion_counts.most_common(1)[0]
        confidence = count / len(episodes)
        
        if confidence >= 0.3:  # Soglia minima per tratto
            return {
                "type": "emotion_trait",
                "emotion": dominant_emotion,
                "frequency": count,
                "confidence": confidence,
                "description": f"Tende a esprimere {dominant_emotion}",
                "created_at": datetime.now().isoformat()
            }
        
        return None
    
    def _extract_communication_trait(self, episodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Estrae tratto comunicativo
        
        Args:
            episodes: Lista episodi
            
        Returns:
            Tratto comunicativo o None
        """
        message_lengths = [len(ep.get("message", "")) for ep in episodes]
        avg_length = sum(message_lengths) / len(message_lengths) if message_lengths else 0
        
        if avg_length > 100:
            style = "verbose"
            description = "Tende a essere dettagliato nelle comunicazioni"
        elif avg_length < 30:
            style = "concise"
            description = "Tende a essere diretto e conciso"
        else:
            style = "balanced"
            description = "Equilibrato nelle comunicazioni"
        
        return {
            "type": "communication_trait",
            "style": style,
            "average_length": avg_length,
            "confidence": 0.7,  # Fisso per ora
            "description": description,
            "created_at": datetime.now().isoformat()
        }
    
    def _extract_temporal_trait(self, episodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Estrae tratto temporale
        
        Args:
            episodes: Lista episodi
            
        Returns:
            Tratto temporale o None
        """
        hour_counts = Counter()
        
        for episode in episodes:
            timestamp = datetime.fromisoformat(episode["timestamp"])
            hour_counts[timestamp.hour] += 1
        
        if not hour_counts:
            return None
        
        # Identifica fascia oraria preferita
        dominant_hour, count = hour_counts.most_common(1)[0]
        confidence = count / len(episodes)
        
        if confidence >= 0.4:  # Soglia minima
            if 6 <= dominant_hour < 12:
                period = "morning"
                description = "Più attivo al mattino"
            elif 12 <= dominant_hour < 18:
                period = "afternoon"
                description = "Più attivo nel pomeriggio"
            elif 18 <= dominant_hour < 22:
                period = "evening"
                description = "Più attivo alla sera"
            else:
                period = "night"
                description = "Più attivo di notte"
            
            return {
                "type": "temporal_trait",
                "period": period,
                "preferred_hour": dominant_hour,
                "confidence": confidence,
                "description": description,
                "created_at": datetime.now().isoformat()
            }
        
        return None
    
    def _extract_relational_trait(self, episodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Estrae tratto relazionale
        
        Args:
            episodes: Lista episodi
            
        Returns:
            Tratto relazionale o None
        """
        engagement_scores = [ep.get("relational_engagement", 0) for ep in episodes]
        avg_engagement = sum(engagement_scores) / len(engagement_scores) if engagement_scores else 0
        
        if avg_engagement > 0.7:
            style = "highly_engaged"
            description = "Molto coinvolto nelle interazioni"
        elif avg_engagement > 0.4:
            style = "moderately_engaged"
            description = "Moderatamente coinvolto nelle interazioni"
        else:
            style = "reserved"
            description = "Riservato nelle interazioni"
        
        return {
            "type": "relational_trait",
            "style": style,
            "average_engagement": avg_engagement,
            "confidence": 0.6,  # Fisso per ora
            "description": description,
            "created_at": datetime.now().isoformat()
        }
    
    async def _update_user_profile(self, user_id: str, patterns: List[Dict[str, Any]], 
                                 traits: List[Dict[str, Any]]):
        """
        Aggiorna profilo utente con pattern e tratti
        
        Args:
            user_id: ID utente
            patterns: Pattern identificati
            traits: Tratti identificati
        """
        try:
            # Carica profilo esistente
            from core.semantic_memory import semantic_memory
            profile = await semantic_memory.get_user_profile(user_id)
            
            if not profile:
                profile = {}
            
            # Aggiungi pattern al profilo
            if "patterns" not in profile:
                profile["patterns"] = []
            
            # Aggiungi solo nuovi pattern
            existing_pattern_keys = {(p["type"], p.get("subtype", "")) for p in profile["patterns"]}
            new_patterns = [p for p in patterns if (p["type"], p.get("subtype", "")) not in existing_pattern_keys]
            profile["patterns"].extend(new_patterns)
            
            # Aggiungi tratti al profilo
            if "traits" not in profile:
                profile["traits"] = []
            
            # Aggiungi solo nuovi tratti
            existing_trait_types = {t["type"] for t in profile["traits"]}
            new_traits = [t for t in traits if t["type"] not in existing_trait_types]
            profile["traits"].extend(new_traits)
            
            # Aggiorna timestamp consolidamento
            profile["last_consolidation"] = datetime.now().isoformat()
            
            # Salva profilo aggiornato
            await semantic_memory.save_user_profile(user_id, profile)
            
            logger.info("PROFILE_UPDATED", extra={
                "user_id": user_id,
                "new_patterns": len(new_patterns),
                "new_traits": len(new_traits),
                "total_patterns": len(profile["patterns"]),
                "total_traits": len(profile["traits"])
            })
            
        except Exception as e:
            logger.error("PROFILE_UPDATE_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
    
    async def _mark_episodes_consolidated(self, user_id: str, episodes: List[Dict[str, Any]]):
        """
        Marca episodi come consolidati
        
        Args:
            user_id: ID utente
            episodes: Episodi da marcare
        """
        try:
            # Carica tutti gli episodi
            all_episodes = await storage.load(f"episodes/{user_id}", default=[])
            
            # Marca episodi specifici come consolidati
            episode_ids_to_mark = {ep["id"] for ep in episodes}
            
            for episode in all_episodes:
                if episode["id"] in episode_ids_to_mark:
                    episode["consolidated"] = True
                    episode["consolidated_at"] = datetime.now().isoformat()
            
            # Salva episodi aggiornati
            await storage.save(f"episodes/{user_id}", all_episodes)
            
            logger.info("EPISODES_MARKED_CONSOLIDATED", extra={
                "user_id": user_id,
                "marked_count": len(episodes)
            })
            
        except Exception as e:
            logger.error("MARK_CONSOLIDATED_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})
    
    async def _cleanup_old_episodes(self, user_id: str):
        """
        Pulisce episodi vecchi e irrilevanti
        
        Args:
            user_id: ID utente
        """
        try:
            episodes = await storage.load(f"episodes/{user_id}", default=[])
            
            # Filtra episodi vecchi e già consolidati
            cutoff_date = datetime.now() - timedelta(days=self.consolidation_window_days)
            
            cleaned_episodes = []
            removed_count = 0
            
            for episode in episodes:
                episode_date = datetime.fromisoformat(episode["timestamp"])
                
                # Mantiene se:
                # 1. Recente (entro finestra)
                # 2. Non consolidato
                # 3. Alta rilevanza
                should_keep = (
                    episode_date > cutoff_date or
                    not episode.get("consolidated", False) or
                    episode.get("relevance_score", 0) > 0.7
                )
                
                if should_keep:
                    cleaned_episodes.append(episode)
                else:
                    removed_count += 1
                    logger.info("EPISODE_REMOVED", extra={
                        "user_id": user_id,
                        "episode_id": episode["id"],
                        "reason": "old_consolidated_low_relevance"
                    })
            
            # Salva episodi puliti
            await storage.save(f"episodes/{user_id}", cleaned_episodes)
            
            if removed_count > 0:
                logger.info("EPISODES_CLEANED", extra={
                    "user_id": user_id,
                    "removed_count": removed_count,
                    "remaining_count": len(cleaned_episodes)
                })
            
        except Exception as e:
            logger.error("CLEANUP_ERROR", exc_info=True, extra={"user_id": user_id, "error": str(e)})

# Istanza globale singleton
memory_consolidation = MemoryConsolidation()
