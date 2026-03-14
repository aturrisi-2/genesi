"""
EPISODE MEMORY — Genesi Episodic Memory System

Salva, recupera e fa pruning di eventi personali specifici dell'utente.
Gli episodi sono eventi temporali concreti (non pattern astratti come global_insights).

Retention: 30 giorni. Rimozione automatica se mai usato o non usato da 30gg.
Max 50 episodi per utente (FIFO).
"""

import logging
from datetime import datetime, date, timedelta
from typing import List

from core.storage import storage
from core.log import log

logger = logging.getLogger("genesi")

_STORAGE_KEY = "episodes:{user_id}"
_RETENTION_DAYS = 30
_MAX_EPISODES = 50


class EpisodeMemory:

    async def add(self, user_id: str, episode: dict) -> None:
        """Aggiunge un episodio alla lista, poi esegue pruning."""
        try:
            episodes = await self._load(user_id)
            # Deduplica: non aggiungere se testo quasi identico (primi 60 chars)
            prefix = episode.get("text", "")[:60].lower()
            for existing in episodes:
                if existing.get("text", "")[:60].lower() == prefix:
                    return  # già presente
            episodes.append(episode)
            episodes = self._prune(episodes)
            await storage.save(_STORAGE_KEY.format(user_id=user_id), episodes)
        except Exception as e:
            logger.debug("EPISODE_MEMORY_ADD_ERROR user=%s err=%s", user_id, e)

    async def get_all(self, user_id: str) -> List[dict]:
        """Carica tutti gli episodi validi (con pruning automatico)."""
        try:
            episodes = await self._load(user_id)
            pruned = self._prune(episodes)
            if len(pruned) != len(episodes):
                await storage.save(_STORAGE_KEY.format(user_id=user_id), pruned)
            return pruned
        except Exception:
            return []

    async def get_relevant(self, user_id: str, message: str, limit: int = 3,
                           current_emotion: str = None) -> List[dict]:
        """Restituisce gli episodi più rilevanti per il messaggio corrente.

        Args:
            current_emotion: se fornita, applica mood-congruent boost (+0.08)
                             agli episodi con tag emotivo corrispondente.
        """
        try:
            episodes = await self.get_all(user_id)
            if not episodes:
                return []
            scored = []
            for ep in episodes:
                score = self._score_relevance(ep, message)
                # Mood-congruent retrieval: boost episodi che condividono l'emozione corrente
                if current_emotion and current_emotion not in ("neutral", ""):
                    if current_emotion in ep.get("tags", []):
                        score += 0.08
                scored.append((ep, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            # Prendi solo quelli con score > 0
            relevant = [ep for ep, score in scored if score > 0]
            return relevant[:limit]
        except Exception:
            return []

    async def mark_used(self, user_id: str, episode_id: str) -> None:
        """Aggiorna last_used_at e use_count per un episodio."""
        try:
            episodes = await self._load(user_id)
            for ep in episodes:
                if ep.get("id") == episode_id:
                    ep["last_used_at"] = datetime.utcnow().isoformat()
                    ep["use_count"] = ep.get("use_count", 0) + 1
                    break
            await storage.save(_STORAGE_KEY.format(user_id=user_id), episodes)
        except Exception as e:
            logger.debug("EPISODE_MARK_USED_ERROR user=%s err=%s", user_id, e)

    async def _load(self, user_id: str) -> List[dict]:
        data = await storage.load(_STORAGE_KEY.format(user_id=user_id), default=[])
        return data if isinstance(data, list) else []

    def _prune(self, episodes: List[dict]) -> List[dict]:
        """Rimuove episodi scaduti e mantiene max _MAX_EPISODES."""
        now = datetime.utcnow()
        cutoff = now - timedelta(days=_RETENTION_DAYS)
        kept = []
        for ep in episodes:
            saved_str = ep.get("saved_at", "")
            last_used_str = ep.get("last_used_at")
            use_count = ep.get("use_count", 0)
            try:
                saved_dt = datetime.fromisoformat(saved_str)
            except Exception:
                continue  # formato invalido → scarta

            # Rimuovi se mai usato e più vecchio di 30gg
            if use_count == 0 and saved_dt < cutoff:
                continue
            # Rimuovi se ultimo utilizzo più vecchio di 30gg
            if last_used_str:
                try:
                    if datetime.fromisoformat(last_used_str) < cutoff:
                        continue
                except Exception:
                    pass
            kept.append(ep)

        # Max _MAX_EPISODES: tieni i più recenti (FIFO)
        if len(kept) > _MAX_EPISODES:
            kept = kept[-_MAX_EPISODES:]
        return kept

    def _score_relevance(self, episode: dict, message: str) -> float:
        """Calcola score di rilevanza episodio vs messaggio corrente."""
        score = 0.0
        msg_words = set(message.lower().split())
        # Tag overlap
        tags = episode.get("tags", [])
        for tag in tags:
            if tag.lower() in msg_words or any(tag.lower() in w for w in msg_words):
                score += 3.0
        # Testo overlap (parole significative)
        text_words = set(episode.get("text", "").lower().split())
        overlap = msg_words & text_words
        # Filtra stop words
        stop = {"il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "e", "è",
                "a", "di", "in", "che", "con", "per", "non", "si", "da", "del",
                "della", "dei", "delle", "degli", "al", "alla", "agli", "alle",
                "l'utente", "deve", "ha", "ho", "mi", "ti", "ci", "vi", "suo", "sua"}
        meaningful = overlap - stop
        score += len(meaningful) * 1.0
        # Follow-up bonus: evento futuro con data passata
        if episode.get("is_future") and episode.get("event_date"):
            try:
                if date.fromisoformat(episode["event_date"]) <= date.today():
                    score += 10.0
            except Exception:
                pass
        # Recency bonus: salvato nelle ultime 24h
        try:
            saved_dt = datetime.fromisoformat(episode.get("saved_at", ""))
            if (datetime.utcnow() - saved_dt).total_seconds() < 86400:
                score += 5.0
        except Exception:
            pass
        return score


# Istanza globale
episode_memory = EpisodeMemory()
