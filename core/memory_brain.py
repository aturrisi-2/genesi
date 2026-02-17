"""
MEMORY BRAIN - Genesi Cognitive System v2
Sistema cognitivo a memoria neurale multi-strato.
4 livelli: Episodic, Relational, Semantic, Consolidation.
Unico punto di accesso per tutta la memoria del sistema.
"""

import logging
import re
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from collections import Counter, defaultdict
from core.storage import storage
from core.semantic_memory import SemanticMemory
from core.relational_state import RelationalState

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# SAFE EMOTION NORMALIZATION — module-level, usable by all layers
# ═══════════════════════════════════════════════════════════════

def _safe_emotion_label(episode_or_raw) -> str:
    """
    Normalizza emotion a stringa hashabile.
    Accetta: str, dict, None, qualsiasi tipo.
    Non lancia mai eccezioni.
    """
    try:
        # Se è un episodio dict con chiave "emotion"
        if isinstance(episode_or_raw, dict) and "emotion" in episode_or_raw:
            raw = episode_or_raw["emotion"]
        else:
            raw = episode_or_raw

        if raw is None:
            return "neutral"
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            label = raw.get("label") or raw.get("emotion") or "neutral"
            logger.debug("MEMORY_EMOTION_NORMALIZED value=%s", label)
            return str(label)
        # Qualsiasi altro tipo
        logger.debug("MEMORY_EMOTION_NORMALIZED value=%s from_type=%s", str(raw), type(raw).__name__)
        return str(raw)
    except Exception:
        return "neutral"


# ═══════════════════════════════════════════════════════════════
# LAYER 1 — EPISODIC MEMORY
# Eventi concreti con timestamp, peso, collegamenti tematici
# ═══════════════════════════════════════════════════════════════

class EpisodicLayer:
    """Memoria episodica: eventi concreti, timestamped, con decay naturale."""

    MAX_EPISODES = 200
    DECAY_RATE_PER_DAY = 0.03  # 3% al giorno

    async def store_episode(self, user_id: str, message: str, emotion: Dict[str, Any],
                            context: Dict[str, Any]) -> Optional[str]:
        """Salva episodio se supera soglia di rilevanza."""
        relevance = self._score_relevance(message, emotion, context)
        if relevance < 0.2:
            logger.debug("EPISODE_SKIP relevance=%.2f user=%s", relevance, user_id)
            return None

        episode = {
            "id": f"ep_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}_{user_id[:8]}",
            "ts": datetime.now().isoformat(),
            "msg": message[:300],
            "emotion": emotion.get("emotion", "neutral"),
            "intensity": emotion.get("intensity", 0.0),
            "relevance": relevance,
            "tags": self._extract_tags(message, context),
            "links": [],  # populated by experience_linking
            "consolidated": False,
            "decay": 1.0
        }

        episodes = await storage.load(f"episodes/{user_id}", default=[])
        episodes.append(episode)

        # Prune if over limit — keep highest relevance*decay
        if len(episodes) > self.MAX_EPISODES:
            episodes.sort(key=lambda e: e["relevance"] * e.get("decay", 1.0), reverse=True)
            episodes = episodes[:self.MAX_EPISODES]

        await storage.save(f"episodes/{user_id}", episodes)
        logger.info("EPISODE_STORED id=%s relevance=%.2f user=%s", episode["id"], relevance, user_id)
        return episode["id"]

    @staticmethod
    def _safe_age_days(ep: Dict[str, Any], now: datetime) -> int:
        """Backward-compatible timestamp parsing. Never crashes."""
        ts_value = ep.get("ts") or ep.get("created_at")
        if not ts_value:
            ts_value = datetime.utcnow().isoformat()
        try:
            return max(0, (now - datetime.fromisoformat(ts_value)).days)
        except (ValueError, TypeError):
            return 0

    async def recall(self, user_id: str, query: str = "", limit: int = 5,
                     min_relevance: float = 0.1) -> List[Dict[str, Any]]:
        """Recupera episodi rilevanti, applicando decay temporale."""
        episodes = await storage.load(f"episodes/{user_id}", default=[])
        now = datetime.now()

        scored = []
        for ep in episodes:
            age_days = self._safe_age_days(ep, now)
            decay = max(0.05, 1.0 - age_days * self.DECAY_RATE_PER_DAY)
            ep["decay"] = decay
            effective = ep.get("relevance", 0.0) * decay

            # Query boost: if query words overlap with episode
            if query:
                query_words = set(query.lower().split())
                ep_words = set(ep.get("msg", "").lower().split())
                overlap = len(query_words & ep_words)
                if overlap > 0:
                    effective += min(0.3, overlap * 0.1)

            if effective >= min_relevance:
                ep["_score"] = effective
                scored.append(ep)

        scored.sort(key=lambda e: e["_score"], reverse=True)
        return scored[:limit]

    async def apply_decay(self, user_id: str) -> int:
        """Applica decay e rimuove episodi sotto soglia."""
        episodes = await storage.load(f"episodes/{user_id}", default=[])
        now = datetime.now()
        kept, forgotten = [], 0

        for ep in episodes:
            age_days = self._safe_age_days(ep, now)
            decay = max(0.05, 1.0 - age_days * self.DECAY_RATE_PER_DAY)
            ep["decay"] = decay
            if ep.get("relevance", 0.0) * decay > 0.05:
                kept.append(ep)
            else:
                forgotten += 1

        if forgotten > 0:
            await storage.save(f"episodes/{user_id}", kept)
            logger.info("DECAY_APPLIED user=%s forgotten=%d remaining=%d", user_id, forgotten, len(kept))
        return forgotten

    # --- internals ---

    def _score_relevance(self, message: str, emotion: Dict[str, Any],
                         context: Dict[str, Any]) -> float:
        score = 0.0
        msg_lower = message.lower().strip()
        msg_len = len(message)
        word_count = len(msg_lower.split())

        # Banal micro-event penalty: single words, bare greetings, trivial messages
        banal_kw = ["ciao", "ok", "si", "no", "va bene", "grazie", "buongiorno",
                    "buonasera", "hey", "ehi", "salve", "boh", "mah"]
        if word_count <= 2 and any(msg_lower.startswith(b) for b in banal_kw):
            return 0.05  # below threshold — never stored

        # Emotional intensity (35%)
        if emotion.get("emotion", "neutral") != "neutral":
            score += emotion.get("intensity", 0.0) * 0.35
        # Vulnerability boost (10%) — feeds resonance in latent state
        if emotion.get("vulnerability", 0) > 0.4:
            score += 0.10
        # Message substance (25%)
        if msg_len > 100:
            score += 0.25
        elif msg_len > 40:
            score += 0.15
        elif msg_len > 15:
            score += 0.08
        # Personal content (25%) — feeds attachment in latent state
        personal_kw = ["chiamo", "nome", "famiglia", "moglie", "marito", "figlio", "figlia",
                       "lavoro", "vivo", "abito", "anni", "amo", "odio", "paura",
                       "soffro", "piango", "solo", "solitudine"]
        if any(kw in msg_lower for kw in personal_kw):
            score += 0.25
        # Relational intent (15%)
        if context.get("is_personal_question") or context.get("references_past"):
            score += 0.15
        return min(1.0, score)

    def _extract_tags(self, message: str, context: Dict[str, Any]) -> List[str]:
        tags = []
        if context.get("intent"):
            tags.append(context["intent"])
        msg_lower = message.lower()
        tag_map = {
            "famiglia": ["moglie", "marito", "figlio", "figlia", "madre", "padre", "famiglia", "fratello", "sorella"],
            "lavoro": ["lavoro", "professione", "ufficio", "collega", "capo"],
            "salute": ["salute", "malattia", "dottore", "ospedale", "dolore"],
            "emozione": ["triste", "felice", "arrabbiato", "ansioso", "preoccupato", "contento", "paura"],
            "identita": ["chiamo", "nome", "sono", "anni", "vivo", "abito"],
            "relazione": ["amore", "amico", "amicizia", "relazione", "partner"],
        }
        for tag, keywords in tag_map.items():
            if any(kw in msg_lower for kw in keywords):
                tags.append(tag)
        return tags[:6]


# ═══════════════════════════════════════════════════════════════
# LAYER 2 — RELATIONAL MEMORY
# Trust, depth, emotional consistency, communication patterns
# ═══════════════════════════════════════════════════════════════

class RelationalLayer:
    """Stato relazionale evolutivo con history e trend."""

    def _default(self) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        return {
            "trust": 0.15,
            "depth": 0.1,
            "attachment_risk": 0.0,
            "consistency": 0.5,  # emotional consistency 0-1
            "comm_style": "unknown",  # concise / balanced / verbose
            "stage": "initial",  # initial / building / developing / mature
            "history": {
                "first_ts": now,
                "last_ts": now,
                "total_msgs": 0,
                "emotion_variance": 0.0,
                "trust_trend": 0.0,
                "last_emotion": "neutral"
            },
            "emotion_timeline": [],
            "trust_evolution": []
        }

    async def load(self, user_id: str) -> Dict[str, Any]:
        state = await storage.load(f"relational_state:{user_id}", default=None)
        if state and isinstance(state, dict):
            default = self._default()
            for k in default:
                if k not in state:
                    state[k] = default[k]
            return state
        state = self._default()
        await storage.save(f"relational_state:{user_id}", state)
        return state

    async def update(self, user_id: str, emotion: Dict[str, Any],
                     message: str) -> Dict[str, Any]:
        state = await self.load(user_id)
        old_trust = state["trust"]

        # Trust grows slowly with interaction
        state["trust"] = min(1.0, state["trust"] + 0.008)

        # Depth tracks current emotional intensity
        intensity = emotion.get("intensity", 0.3)
        state["depth"] = 0.7 * state["depth"] + 0.3 * intensity  # EMA

        # Attachment risk
        if emotion.get("vulnerability", 0) > 0.7:
            state["attachment_risk"] = min(1.0, state["attachment_risk"] + 0.03)

        # Communication style from message length
        msg_len = len(message)
        if msg_len > 120:
            state["comm_style"] = "verbose"
        elif msg_len < 25:
            state["comm_style"] = "concise"
        else:
            state["comm_style"] = "balanced"

        # History
        h = state["history"]
        h["total_msgs"] += 1
        h["last_ts"] = datetime.now().isoformat()
        h["last_emotion"] = emotion.get("emotion", "neutral")
        h["trust_trend"] = state["trust"] - old_trust

        # Timeline (keep last 100)
        state["emotion_timeline"].append({
            "ts": datetime.now().isoformat(),
            "emotion": emotion.get("emotion", "neutral"),
            "intensity": intensity,
            "trust": state["trust"]
        })
        if len(state["emotion_timeline"]) > 100:
            state["emotion_timeline"] = state["emotion_timeline"][-100:]

        # Trust evolution (keep last 50)
        state["trust_evolution"].append({
            "ts": datetime.now().isoformat(),
            "trust": state["trust"]
        })
        if len(state["trust_evolution"]) > 50:
            state["trust_evolution"] = state["trust_evolution"][-50:]

        # Emotional consistency
        state["consistency"] = self._calc_consistency(state["emotion_timeline"])

        # Stage
        state["stage"] = self._calc_stage(state)

        # Emotional variance
        h["emotion_variance"] = self._calc_variance(state["emotion_timeline"])

        await storage.save(f"relational_state:{user_id}", state)
        logger.info("RELATIONAL_UPDATE user=%s trust=%.3f depth=%.3f stage=%s msgs=%d",
                     user_id, state["trust"], state["depth"], state["stage"], h["total_msgs"])
        return state

    def _calc_consistency(self, timeline: list) -> float:
        if len(timeline) < 3:
            return 0.5
        recent = [_safe_emotion_label(e) for e in timeline[-10:]]
        most_common = Counter(recent).most_common(1)[0][1]
        return most_common / len(recent)

    def _calc_variance(self, timeline: list) -> float:
        if len(timeline) < 2:
            return 0.0
        intensities = [e["intensity"] for e in timeline[-20:]]
        mean = sum(intensities) / len(intensities)
        return sum((x - mean) ** 2 for x in intensities) / len(intensities)

    def _calc_stage(self, state: dict) -> str:
        trust = state.get("trust", 0.15)
        depth = state.get("depth", 0.1)
        msgs = state.get("history", {}).get("total_msgs", 0)
        if msgs < 5:
            return "initial"
        elif trust < 0.35:
            return "building"
        elif trust < 0.65 or depth < 0.5:
            return "developing"
        elif trust >= 0.65 and depth >= 0.5:
            return "mature"
        return "balanced"


# ═══════════════════════════════════════════════════════════════
# LAYER 3 — SEMANTIC MEMORY
# Stable facts: entities, relationships, preferences
# ═══════════════════════════════════════════════════════════════

class SemanticLayer:
    """Informazioni stabili: entità, relazioni, preferenze."""

    PATTERNS = {
        "name": [
            r"mi chiamo\s+(\w+)", r"io mi chiamo\s+(\w+)",
            r"il mio nome (?:è|e')\s+(\w+)", r"chiamami\s+(\w+)"
        ],
        "age": [r"ho\s+(\d+)\s+anni", r"(\d+)\s+anni"],
        "city": [
            r"vivo a\s+(\w+)", r"abito a\s+(\w+)",
            r"sono di\s+(\w+)", r"vengo da\s+(\w+)"
        ],
        "profession": [
            r"lavoro come\s+(.+?)(?:\.|,|$)",
            r"faccio (?:il|la|lo|l')\s+(.+?)(?:\.|,|$)",
            r"sono (?:un|una|un')\s+(.+?)(?:\.|,|$)"
        ]
    }

    # Entity extraction for people mentioned
    ENTITY_PATTERNS = [
        (r"(?:mia|la mia)\s+moglie\s+(?:si chiama\s+)?(\w+)", "moglie"),
        (r"(?:mio|il mio)\s+marito\s+(?:si chiama\s+)?(\w+)", "marito"),
        (r"(?:mio|il mio)\s+figlio\s+(?:si chiama\s+)?(\w+)", "figlio"),
        (r"(?:mia|la mia)\s+figlia\s+(?:si chiama\s+)?(\w+)", "figlia"),
        (r"(?:mio|il mio)\s+amico\s+(\w+)", "amico"),
        (r"(?:mia|la mia)\s+amica\s+(\w+)", "amica"),
        (r"(?:mia|la mia)\s+madre\s+(?:si chiama\s+)?(\w+)", "madre"),
        (r"(?:mio|il mio)\s+padre\s+(?:si chiama\s+)?(\w+)", "padre"),
        # Catch "moglie" / "marito" without name
        (r"(?:mia|la mia)\s+(moglie)", "_role_moglie"),
        (r"(?:mio|il mio)\s+(marito)", "_role_marito"),
    ]

    async def extract_and_store(self, user_id: str, message: str) -> Dict[str, Any]:
        """Estrae dati personali e entità dal messaggio, salva nel profilo."""
        profile = await self.get_user_profile(user_id)
        extracted = {}

        # Standard fields
        for field, patterns in self.PATTERNS.items():
            for pattern in patterns:
                m = re.search(pattern, message, re.IGNORECASE)
                if m:
                    value = m.group(1).strip()
                    if field == "name":
                        value = value.capitalize()
                    elif field == "age":
                        try:
                            value = int(value)
                            if not (1 <= value <= 120):
                                continue
                        except ValueError:
                            continue
                    elif field == "profession":
                        value = value.strip().lower()

                    if profile.get(field) != value:
                        profile[field] = value
                        extracted[field] = value
                        logger.info("SEMANTIC_EXTRACT user=%s field=%s value=%s", user_id, field, value)
                    break

        # Entity extraction (people)
        entities = profile.get("entities", {})
        for pattern, role in self.ENTITY_PATTERNS:
            m = re.search(pattern, message, re.IGNORECASE)
            if m:
                name = m.group(1).strip().capitalize()
                if role.startswith("_role_"):
                    # Mentioned role without name — track mention count
                    role_key = role.replace("_role_", "")
                    if role_key not in entities:
                        entities[role_key] = {"name": None, "role": role_key, "mentions": 0}
                    entities[role_key]["mentions"] = entities[role_key].get("mentions", 0) + 1
                else:
                    entities[role] = {"name": name, "role": role, "mentions": entities.get(role, {}).get("mentions", 0) + 1}
                    extracted[f"entity_{role}"] = name
                    logger.info("ENTITY_EXTRACT user=%s role=%s name=%s", user_id, role, name)

        if entities:
            profile["entities"] = entities

        if extracted:
            await self.save_user_profile(user_id, profile)

        return extracted

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        return await storage.load(f"profile:{user_id}", default={})

    async def save_user_profile(self, user_id: str, profile: Dict[str, Any]) -> bool:
        profile["updated_at"] = datetime.now().isoformat()
        logger.info("PROFILE_BEFORE_SAVE user=%s profile=%s", user_id, profile)
        return await storage.save(f"profile:{user_id}", profile)

    async def update_emotional_pattern(self, user_id: str, emotion: str, intensity: float):
        profile = await self.get_user_profile(user_id)
        patterns = profile.get("emotional_patterns", [])
        patterns.append({"emotion": emotion, "intensity": intensity, "ts": datetime.now().isoformat()})
        if len(patterns) > 50:
            patterns = patterns[-50:]
        profile["emotional_patterns"] = patterns
        await self.save_user_profile(user_id, profile)

    async def get_entity_weight(self, user_id: str, entity_name: str) -> float:
        """Peso semantico di un'entità basato su menzioni."""
        profile = await self.get_user_profile(user_id)
        entities = profile.get("entities", {})
        for role, data in entities.items():
            if data.get("name", "").lower() == entity_name.lower():
                return min(1.0, data.get("mentions", 1) * 0.15)
        return 0.0


# ═══════════════════════════════════════════════════════════════
# LAYER 4 — CONSOLIDATION ENGINE
# Calcola relevance, comprime, consolida, collega esperienze
# ═══════════════════════════════════════════════════════════════

class ConsolidationEngine:
    """Consolida episodi in pattern e tratti nel profilo semantico."""

    CONSOLIDATION_THRESHOLD = 8  # episodi prima di consolidare
    WINDOW_DAYS = 30

    async def should_consolidate(self, user_id: str) -> bool:
        episodes = await storage.load(f"episodes/{user_id}", default=[])
        unconsolidated = [e for e in episodes if not e.get("consolidated")]
        return len(unconsolidated) >= self.CONSOLIDATION_THRESHOLD

    async def consolidate(self, user_id: str) -> Dict[str, Any]:
        """Esegue consolidamento: episodi → pattern + tratti → profilo."""
        episodes = await storage.load(f"episodes/{user_id}", default=[])
        to_consolidate = [e for e in episodes if not e.get("consolidated")]
        if not to_consolidate:
            return {"consolidated": 0, "patterns": 0, "traits": 0}

        to_consolidate.sort(key=lambda e: e.get("relevance", 0), reverse=True)
        batch = to_consolidate[:self.CONSOLIDATION_THRESHOLD]

        # Extract patterns
        patterns = self._extract_patterns(batch)
        traits = self._extract_traits(batch)

        # Update semantic profile
        semantic = SemanticLayer()
        profile = await semantic.get_user_profile(user_id)

        existing_pattern_keys = {(p.get("type"), p.get("key", "")) for p in profile.get("patterns", [])}
        new_patterns = [p for p in patterns if (p["type"], p.get("key", "")) not in existing_pattern_keys]
        profile.setdefault("patterns", []).extend(new_patterns)

        existing_trait_types = {t["type"] for t in profile.get("traits", []) if isinstance(t, dict)}
        new_traits = [t for t in traits if t["type"] not in existing_trait_types]
        # Update existing traits instead of duplicating
        for t in traits:
            if t["type"] in existing_trait_types:
                for i, existing in enumerate(profile["traits"]):
                    if isinstance(existing, dict) and existing.get("type") == t["type"]:
                        profile["traits"][i] = t
                        break
        profile.setdefault("traits", []).extend(new_traits)

        profile["last_consolidation"] = datetime.now().isoformat()
        await semantic.save_user_profile(user_id, profile)

        # Mark consolidated
        batch_ids = {e["id"] for e in batch}
        for ep in episodes:
            if ep["id"] in batch_ids:
                ep["consolidated"] = True
                ep["consolidated_at"] = datetime.now().isoformat()
        await storage.save(f"episodes/{user_id}", episodes)

        result = {"consolidated": len(batch), "patterns": len(new_patterns), "traits": len(new_traits)}
        logger.info("CONSOLIDATION_DONE user=%s %s", user_id, result)
        return result

    def _extract_patterns(self, episodes: List[Dict]) -> List[Dict]:
        patterns = []
        # Emotion patterns
        emotion_counts = Counter(_safe_emotion_label(e) for e in episodes)
        for emo, count in emotion_counts.items():
            if emo != "neutral" and count >= 2:
                patterns.append({"type": "emotion", "key": emo, "frequency": count,
                                 "confidence": count / len(episodes)})
        # Tag patterns
        all_tags = [t for e in episodes for t in e.get("tags", [])]
        tag_counts = Counter(all_tags)
        for tag, count in tag_counts.items():
            if count >= 2:
                patterns.append({"type": "topic", "key": tag, "frequency": count,
                                 "confidence": count / len(episodes)})
        return patterns

    def _extract_traits(self, episodes: List[Dict]) -> List[Dict]:
        traits = []
        # Communication trait
        lengths = [len(e.get("msg", "")) for e in episodes]
        avg_len = sum(lengths) / len(lengths) if lengths else 0
        if avg_len > 100:
            style, desc = "verbose", "Tende a essere dettagliato"
        elif avg_len < 30:
            style, desc = "concise", "Tende a essere diretto e conciso"
        else:
            style, desc = "balanced", "Equilibrato nelle comunicazioni"
        traits.append({"type": "communication", "style": style, "avg_length": avg_len, "description": desc})

        # Dominant emotion trait
        emo_counts = Counter(_safe_emotion_label(e) for e in episodes
                             if _safe_emotion_label(e) != "neutral")
        if emo_counts:
            dominant, count = emo_counts.most_common(1)[0]
            conf = count / len(episodes)
            if conf >= 0.25:
                traits.append({"type": "emotion_dominant", "emotion": dominant,
                               "confidence": conf, "description": f"Tende a esprimere {dominant}"})
        return traits


# ═══════════════════════════════════════════════════════════════
# EXPERIENCE LINKING — FASE 5
# Collega episodi tra loro per creare narrazione interna
# ═══════════════════════════════════════════════════════════════

class ExperienceLinking:
    """Collega episodi correlati per costruire narrazione."""

    async def link_new_episode(self, user_id: str, new_episode_id: str):
        """Collega nuovo episodio a episodi precedenti con tag simili."""
        episodes = await storage.load(f"episodes/{user_id}", default=[])
        new_ep = None
        for ep in episodes:
            if ep["id"] == new_episode_id:
                new_ep = ep
                break
        if not new_ep:
            return

        new_tags = set(new_ep.get("tags", []))
        if not new_tags:
            return

        links = []
        for ep in episodes:
            if ep["id"] == new_episode_id:
                continue
            ep_tags = set(ep.get("tags", []))
            overlap = new_tags & ep_tags
            if overlap:
                links.append({"episode_id": ep["id"], "shared_tags": list(overlap),
                              "strength": len(overlap) / max(len(new_tags), 1)})

        if links:
            links.sort(key=lambda l: l["strength"], reverse=True)
            new_ep["links"] = links[:5]  # max 5 links
            await storage.save(f"episodes/{user_id}", episodes)
            logger.info("EXPERIENCE_LINKED ep=%s links=%d user=%s", new_episode_id, len(links), user_id)

    async def get_narrative_thread(self, user_id: str, tag: str, limit: int = 5) -> List[Dict]:
        """Recupera thread narrativo per un tag specifico."""
        episodes = await storage.load(f"episodes/{user_id}", default=[])
        matching = [e for e in episodes if tag in e.get("tags", [])]
        matching.sort(key=lambda e: e["ts"])
        return matching[-limit:]

    async def update_entity_weight(self, user_id: str, message: str):
        """Incrementa peso entità menzionate nel messaggio."""
        semantic = SemanticLayer()
        profile = await semantic.get_user_profile(user_id)
        entities = profile.get("entities", {})
        msg_lower = message.lower()
        updated = False

        for role, data in entities.items():
            name = data.get("name")
            if name and name.lower() in msg_lower:
                data["mentions"] = data.get("mentions", 0) + 1
                updated = True
                logger.info("ENTITY_WEIGHT_UP user=%s entity=%s mentions=%d", user_id, name, data["mentions"])

        if updated:
            profile["entities"] = entities
            await semantic.save_user_profile(user_id, profile)


# ═══════════════════════════════════════════════════════════════
# LOCAL EMOTION ANALYZER — No LLM, rule-based
# Replaces GPT-4o-mini emotion_analyzer to save quota
# ═══════════════════════════════════════════════════════════════

class LocalEmotionAnalyzer:
    """Analisi emotiva locale rule-based. Zero API calls."""

    EMOTION_LEXICON = {
        "felice": ("happy", 0.7), "contento": ("happy", 0.6), "bene": ("happy", 0.4),
        "benissimo": ("happy", 0.8), "fantastico": ("happy", 0.9), "meraviglioso": ("happy", 0.9),
        "gioia": ("happy", 0.8), "entusiasta": ("happy", 0.8),
        "triste": ("sad", 0.7), "male": ("sad", 0.5), "depresso": ("sad", 0.9),
        "piango": ("sad", 0.8), "soffro": ("sad", 0.8), "dolore": ("sad", 0.7),
        "solo": ("sad", 0.6), "solitudine": ("sad", 0.7), "vuoto": ("sad", 0.6),
        "arrabbiato": ("angry", 0.7), "furioso": ("angry", 0.9), "incazzato": ("angry", 0.9),
        "frustrato": ("angry", 0.6), "stufo": ("angry", 0.5), "rabbia": ("angry", 0.8),
        "ansioso": ("anxious", 0.7), "ansia": ("anxious", 0.8), "preoccupato": ("anxious", 0.6),
        "paura": ("anxious", 0.8), "nervoso": ("anxious", 0.6), "agitato": ("anxious", 0.6),
        "stanco": ("tired", 0.5), "esausto": ("tired", 0.8), "sfinito": ("tired", 0.8),
        "sorpreso": ("surprised", 0.6), "incredibile": ("surprised", 0.7),
        "grazie": ("grateful", 0.5), "grato": ("grateful", 0.7), "riconoscente": ("grateful", 0.7),
        "amo": ("love", 0.8), "amore": ("love", 0.7), "adoro": ("love", 0.7),
        "manchi": ("longing", 0.7), "nostalgia": ("longing", 0.6), "manca": ("longing", 0.6),
    }

    INTENSIFIERS = {"molto", "tanto", "troppo", "davvero", "veramente", "estremamente", "incredibilmente"}
    DIMINISHERS = {"poco", "un po'", "leggermente", "appena"}

    def analyze(self, message: str) -> Dict[str, Any]:
        msg_lower = message.lower()
        words = msg_lower.split()

        best_emotion = "neutral"
        best_intensity = 0.3
        vulnerability = 0.1

        for word in words:
            if word in self.EMOTION_LEXICON:
                emotion, intensity = self.EMOTION_LEXICON[word]
                if intensity > best_intensity:
                    best_emotion = emotion
                    best_intensity = intensity

        # Intensifier/diminisher adjustment
        has_intensifier = any(w in msg_lower for w in self.INTENSIFIERS)
        has_diminisher = any(w in msg_lower for w in self.DIMINISHERS)
        if has_intensifier:
            best_intensity = min(1.0, best_intensity + 0.15)
        if has_diminisher:
            best_intensity = max(0.1, best_intensity - 0.15)

        # Vulnerability from sad/anxious emotions
        if best_emotion in ("sad", "anxious", "longing"):
            vulnerability = best_intensity * 0.8
        elif best_emotion in ("angry", "tired"):
            vulnerability = best_intensity * 0.4

        # Question marks reduce intensity slightly
        if "?" in message:
            best_intensity = max(0.1, best_intensity - 0.05)

        # Exclamation marks increase intensity
        if "!" in message:
            best_intensity = min(1.0, best_intensity + 0.1)

        return {
            "emotion": best_emotion,
            "intensity": round(best_intensity, 2),
            "vulnerability": round(vulnerability, 2),
            "urgency": round(best_intensity * 0.5, 2) if best_emotion in ("anxious", "angry") else 0.1
        }


# ═══════════════════════════════════════════════════════════════
# MEMORY BRAIN — Unified facade
# ═══════════════════════════════════════════════════════════════

class MemoryBrain:
    """
    Cervello unificato a 4 strati.
    Unico punto di accesso per tutta la memoria cognitiva.
    """

    def __init__(self):
        self.episodic = EpisodicLayer()
        self.relational = RelationalState()
        self.semantic = SemanticMemory()
        self.consolidation = ConsolidationEngine()
        self.linking = ExperienceLinking()
        self.emotion_analyzer = LocalEmotionAnalyzer()
        logger.info("MEMORY_BRAIN_INIT layers=4 status=ready")

    async def update_brain(self, user_id: str, message: str) -> Dict[str, Any]:
        """
        Aggiorna stato cerebrale (episodic, relational, emotion).
        Estrae e salva informazioni sul profilo se presenti.
        Returns brain_state dictionary.
        """
        # Extract and save profile information using cognitive memory engine
        from core.cognitive_memory_engine import CognitiveMemoryEngine
        from core.storage import storage
        cognitive_engine = CognitiveMemoryEngine()
        
        # Load current profile data
        raw_profile = await storage.load(f"profile:{user_id}", default={})
        
        # Evaluate message for profile updates
        decision = cognitive_engine.evaluate_event(user_id, message, raw_profile)
        
        # Save profile if there are updates
        if decision['persist'] and decision['memory_type'] == 'profile':
            await storage.save(f"profile:{user_id}", raw_profile)
            logger.info("BRAIN_PROFILE_UPDATED user=%s field=%s", user_id, decision['key'])
        
        profile = await self.semantic.get_user_profile(user_id)
        rel_state = await self.relational.load_state(user_id)
        
        # Analyze emotion for this message
        emotion = self.emotion_analyzer.analyze(message)
        
        brain_state = {
            "profile": profile,
            "relational": rel_state,
            "emotion": emotion,
            "user_id": user_id,
            "message": message
        }
        
        logger.info("BRAIN_UPDATE user=%s profile_loaded=true", user_id)
        return brain_state

    async def recall_for_response(self, user_id: str, message: str) -> Dict[str, Any]:
        """Recall completo per generazione risposta (senza update)."""
        profile = await self.semantic.get_user_profile(user_id)
        rel_state = await self.relational.load_state(user_id)
        episodes = await self.episodic.recall(user_id, query=message, limit=5)

        return {
            "profile": profile,
            "relational": rel_state,
            "episodes": episodes
        }

    def _is_personal(self, message: str) -> bool:
        kw = ["come mi chiamo", "il mio nome", "ricordi", "ti ricordi", "cosa sai di me", "chi sono"]
        return any(k in message.lower() for k in kw)

    def _references_past(self, message: str) -> bool:
        kw = ["prima", "già", "ancora", "sempre", "mai", "di nuovo", "ricordo", "avevamo", "avevo"]
        return any(k in message.lower() for k in kw)


# Istanza globale singleton
memory_brain = MemoryBrain()
