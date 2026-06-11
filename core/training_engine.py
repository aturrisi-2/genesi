"""
TRAINING ENGINE — Genesi Training System
Gestisce corrections (segnalazioni admin) e lessons (few-shot examples iniettati nel prompt).

Flusso:
  1. Admin nota risposta errata → POST /admin/training/corrections
  2. Correction salvata con bad_response / correct_response / category
  3. Admin attiva la correction come "lesson" → diventa few-shot example
  4. context_assembler.py inietta le lessons attive rilevanti nel prompt
"""

import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional

from core.storage import storage

logger = logging.getLogger(__name__)

CORRECTIONS_KEY = "admin/corrections"

CATEGORIES = {
    "memoria":   "Memoria / Ricordi",
    "identita":  "Identità utente",
    "emozione":  "Risposta emotiva",
    "stile":     "Stile / Tono",
    "fatto":     "Fatto errato",
    "intent":    "Intent sbagliato",
    "altro":     "Altro",
}


class TrainingEngine:

    # ── CORRECTIONS ────────────────────────────────────────────────────────

    async def add_correction(
        self,
        input_message:    str,
        bad_response:     str,
        correct_response: str,
        category:         str = "altro",
        admin_note:       str = "",
        user_id:          str = "",
    ) -> Dict:
        """Aggiunge una correzione. Crea automaticamente una lesson candidata (non attiva)."""
        correction = {
            "id":               uuid.uuid4().hex[:8],
            "timestamp":        datetime.utcnow().isoformat(),
            "user_id":          user_id,
            "input_message":    input_message,
            "bad_response":     bad_response,
            "correct_response": correct_response,
            "category":         category,
            "admin_note":       admin_note,
            "lesson_active":    False,   # attivare esplicitamente
        }
        corrections = await self._load()
        corrections.append(correction)
        await storage.save(CORRECTIONS_KEY, corrections)
        logger.info("CORRECTION_SAVED id=%s category=%s", correction["id"], category)
        return correction

    async def get_corrections(self, category: Optional[str] = None) -> List[Dict]:
        """Restituisce tutte le correzioni, opzionalmente filtrate per categoria."""
        data = await self._load()
        if category:
            data = [c for c in data if c.get("category") == category]
        return list(reversed(data))

    async def delete_correction(self, correction_id: str) -> bool:
        corrections = await self._load()
        before      = len(corrections)
        corrections = [c for c in corrections if c.get("id") != correction_id]
        if len(corrections) < before:
            await storage.save(CORRECTIONS_KEY, corrections)
            logger.info("CORRECTION_DELETED id=%s", correction_id)
            return True
        return False

    async def toggle_lesson(self, correction_id: str, active: bool) -> bool:
        """Attiva/disattiva una correction come few-shot lesson.
        Le lessons attivate manualmente vengono pinnate (lesson_pinned=True)
        e l'autopilot non le disattiverà nella rotazione automatica.
        """
        corrections = await self._load()
        for c in corrections:
            if c.get("id") == correction_id:
                c["lesson_active"] = active
                # Pinning: attivazione manuale = protetta dall'autopilot
                c["lesson_pinned"] = active
                await storage.save(CORRECTIONS_KEY, corrections)
                logger.info("LESSON_TOGGLED id=%s active=%s pinned=%s", correction_id, active, active)
                return True
        return False

    async def batch_toggle_lessons(self, changes: dict) -> tuple[int, int]:
        """Applica più toggle in un unico load+save.
        changes = {correction_id: True/False}
        Ritorna (activated, deactivated).
        """
        if not changes:
            return 0, 0
        corrections = await self._load()
        activated = deactivated = 0
        for c in corrections:
            cid = c.get("id")
            if cid in changes:
                new_state = changes[cid]
                if new_state and not c.get("lesson_active"):
                    activated += 1
                elif not new_state and c.get("lesson_active"):
                    deactivated += 1
                c["lesson_active"] = new_state
        if activated or deactivated:
            await storage.save(CORRECTIONS_KEY, corrections)
            logger.info("LESSONS_BATCH_TOGGLED activated=%d deactivated=%d", activated, deactivated)
        return activated, deactivated

    async def get_active_lessons(self) -> List[Dict]:
        """Restituisce solo le lessons attive."""
        corrections = await self._load()
        return [c for c in corrections if c.get("lesson_active")]

    # ── LESSON INJECTION ──────────────────────────────────────────────────

    async def get_context_lessons(self, message: str, max_lessons: int = 2) -> str:
        """
        Restituisce un blocco di few-shot lessons da iniettare nel prompt LLM.
        Seleziona le lessons più rilevanti per il messaggio corrente tramite
        keyword overlap. Restituisce stringa vuota se non ci sono lessons attive.
        """
        try:
            active = await self.get_active_lessons()
            if not active:
                return ""

            msg_words = set(message.lower().split())
            scored: List[tuple] = []
            for lesson in active:
                lw      = set(lesson.get("input_message", "").lower().split())
                overlap = len(msg_words & lw)
                scored.append((overlap, lesson))

            scored.sort(key=lambda x: x[0], reverse=True)

            # Prendi fino a max_lessons (priorità: quelle con overlap > 0, poi le altre)
            selected = [l for sc, l in scored[:max_lessons]]
            if not selected:
                return ""

            lines = ["[ESEMPI DI RISPOSTA OTTIMALE — replicare stile e contenuto]"]
            for lesson in selected:
                lines.append(f"Utente: {lesson['input_message']}")
                lines.append(f"Genesi: {lesson['correct_response']}")
                if lesson.get("admin_note"):
                    lines.append(f"(Nota admin: {lesson['admin_note']})")
                lines.append("")
            return "\n".join(lines).strip()

        except Exception as e:
            logger.warning("LESSON_INJECTION_ERROR err=%s", e)
            return ""

    # ── Stats ──────────────────────────────────────────────────────────────

    async def get_stats(self) -> Dict:
        """Statistiche aggregate per il cruscotto."""
        corrections = await self._load()
        by_cat: Dict[str, int] = {}
        active = 0
        for c in corrections:
            cat = c.get("category", "altro")
            by_cat[cat] = by_cat.get(cat, 0) + 1
            if c.get("lesson_active"):
                active += 1
        return {
            "total":      len(corrections),
            "active_lessons": active,
            "by_category":    by_cat,
            "categories":     CATEGORIES,
        }

    async def get_weak_categories(self, top_n: int = 3) -> List[Dict]:
        """
        Analizza le corrections e restituisce le categorie più deboli.
        Debolezza = corrections non risolte (senza lesson attiva).
        Se nessuna correction esiste, restituisce le categorie default più critiche.
        """
        corrections = await self._load()

        cat_total: Dict[str, int]   = {}
        cat_lessons: Dict[str, int] = {}
        for c in corrections:
            cat = c.get("category", "altro")
            cat_total[cat] = cat_total.get(cat, 0) + 1
            if c.get("lesson_active"):
                cat_lessons[cat] = cat_lessons.get(cat, 0) + 1

        if not cat_total:
            # Nessuna correction → categorie default più critiche
            defaults = ["confini", "crisi", "emozione"]
            return [{"category": c, "total": 0, "lessons": 0, "unresolved": 0,
                     "reason": "default (nessuna correction presente)"} for c in defaults[:top_n]]

        scored = []
        for cat, total in cat_total.items():
            lessons    = cat_lessons.get(cat, 0)
            unresolved = total - lessons
            scored.append({
                "category":   cat,
                "total":      total,
                "lessons":    lessons,
                "unresolved": unresolved,
                # peso: irrisolti contano doppio
                "_score":     unresolved * 2 + total,
            })

        scored.sort(key=lambda x: -x["_score"])
        for s in scored:
            s.pop("_score", None)
        return scored[:top_n]

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _load(self) -> List[Dict]:
        data = await storage.load(CORRECTIONS_KEY, default=[])
        return data if isinstance(data, list) else []


training_engine = TrainingEngine()
