"""
GLOBAL MEMORY SERVICE — Insight consolidati cross-conversazione per utente.

Ogni 24h (al massimo) estrae da chat_memory + profilo un set di insight
stabili sull'utente (max 8 frasi) e li salva in memory/global_insights/{user_id}.json.
Questi insight vengono iniettati nel contesto LLM da context_assembler.py.

Fail-silent: qualsiasi errore non interrompe il flusso principale.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List

from core.storage import storage
from core.chat_memory import chat_memory
from core.log import log

logger = logging.getLogger("genesi")

_STORAGE_KEY = "global_insights:{user_id}"
_CONSOLIDATION_INTERVAL_HOURS = 24

_CONSOLIDATION_PROMPT = """\
Sei un assistente che analizza conversazioni per estrarre pattern stabili sull'utente.
Produci SOLO un JSON valido nel formato: {"insights": ["...", "...", ...]}
con al massimo 8 frasi brevi in italiano (una per elemento).
Ogni insight deve descrivere un fatto osservato: preferenze, stile comunicativo,
argomenti ricorrenti, situazioni di vita emerse, abitudini.
NON inventare. Usa solo ciò che emerge chiaramente dai messaggi.
Se non ci sono dati sufficienti, restituisci {"insights": []}.
Esempi di insight: "Preferisce risposte concise e dirette",
"Lavora spesso di sera", "Ha interesse per la tecnologia e il fitness",
"Si trova in un periodo lavorativo intenso".\
"""


class GlobalMemoryService:

    async def consolidate_if_needed(self, user_id: str) -> None:
        """Avvia consolidazione in background solo se passate >24h dall'ultima."""
        if not user_id:
            return
        try:
            key = _STORAGE_KEY.format(user_id=user_id)
            existing = await storage.load(key, default={})
            last_str = existing.get("last_consolidated_at")
            if last_str:
                last_dt = datetime.fromisoformat(last_str)
                diff = (datetime.utcnow() - last_dt).total_seconds()
                # If previous run had 0 insights (insufficient data), retry after 1h.
                # Otherwise use the standard 24h interval to avoid LLM overhead.
                prev_had_insights = bool(existing.get("insights"))
                interval = _CONSOLIDATION_INTERVAL_HOURS * 3600 if prev_had_insights else 3600
                if diff < interval:
                    return  # Troppo recente, salta
            # Lancia consolidazione senza bloccare
            asyncio.create_task(self._do_consolidate(user_id))
        except Exception as e:
            logger.debug("GLOBAL_MEMORY_SCHEDULE_ERROR user=%s err=%s", user_id, e)

    async def _do_consolidate(self, user_id: str) -> None:
        """Legge memoria recente e genera insight via gpt-4o-mini."""
        try:
            from core.llm_service import llm_service  # import locale per evitare circular

            recent_chats = chat_memory.get_messages(user_id, limit=40)

            # Build profile summary to seed insights even when chat history is short
            # (chat_memory resets on restart, profile persists to disk)
            profile = await storage.load(f"profile:{user_id}", default={})
            profile_parts = []
            if profile.get("name"):
                profile_parts.append(f"Nome: {profile['name']}")
            if profile.get("city"):
                profile_parts.append(f"Città: {profile['city']}")
            if profile.get("profession"):
                profile_parts.append(f"Professione: {profile['profession']}")
            if profile.get("spouse"):
                profile_parts.append(f"Partner: {profile['spouse']}")
            children = profile.get("children", [])
            if children:
                names = [c.get("name", "") if isinstance(c, dict) else str(c) for c in children]
                profile_parts.append(f"Figli: {', '.join(n for n in names if n)}")
            pets = profile.get("pets", [])
            if pets:
                desc = [f"{p.get('name','')} ({p.get('type','')})" if isinstance(p, dict) else str(p) for p in pets]
                profile_parts.append(f"Animali: {', '.join(desc)}")
            interests = profile.get("interests", [])
            if interests:
                profile_parts.append(f"Interessi: {', '.join(interests)}")
            profile_text = "\n".join(profile_parts)

            # chat_memory.get_messages returns {"user_message":..., "system_response":...} format
            lines = []
            for m in recent_chats:
                u = str(m.get("user_message", m.get("content", ""))).strip()
                r = str(m.get("system_response", "")).strip()
                if u:
                    lines.append(f"utente: {u[:200]}")
                if r:
                    lines.append(f"assistente: {r[:200]}")
            chat_text = "\n".join(lines)

            # Need at least profile data or enough chat to be useful
            if not profile_text and len(recent_chats) < 3:
                return

            input_text = ""
            if profile_text:
                input_text += f"[PROFILO UTENTE]\n{profile_text}\n\n"
            if chat_text:
                input_text += f"[CHAT RECENTE]\n{chat_text}"

            # Usa _call_model direttamente per evitare che _call_with_protection
            # sostituisca _CONSOLIDATION_PROMPT con il system prompt adattivo di Genesi
            raw = await llm_service._call_model(
                "openai/gpt-4o-mini",
                _CONSOLIDATION_PROMPT,
                input_text,
                user_id=user_id,
                route="memory"
            )
            if not raw:
                return

            # Pulizia: il modello potrebbe aggiungere ```json ``` wrapper
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            clean = clean.strip()

            parsed = json.loads(clean)
            insights: List[str] = parsed.get("insights", [])
            if not isinstance(insights, list):
                return

            # Filtra stringhe vuote e limita a 8
            insights = [str(i).strip() for i in insights if str(i).strip()][:8]

            payload = {
                "insights": insights,
                "last_consolidated_at": datetime.utcnow().isoformat(),
                "message_count": len(recent_chats),
            }
            key = _STORAGE_KEY.format(user_id=user_id)
            await storage.save(key, payload)
            log("GLOBAL_MEMORY_CONSOLIDATION_DONE", user_id=user_id, insight_count=len(insights))

        except Exception as e:
            logger.warning("GLOBAL_MEMORY_CONSOLIDATION_ERROR user=%s err=%s", user_id, e)

    async def get_insights(self, user_id: str) -> List[str]:
        """Restituisce gli insight consolidati. Lista vuota se non disponibili."""
        if not user_id:
            return []
        try:
            key = _STORAGE_KEY.format(user_id=user_id)
            data = await storage.load(key, default={})
            return data.get("insights", [])
        except Exception:
            return []


# Istanza globale
global_memory_service = GlobalMemoryService()
