"""
CONVERSATION SUMMARY SERVICE - Genesi Memory
Salva un riassunto di ogni conversazione per abilitare memoria cross-sessione.
Storage: memory/conversation_summaries/{user_id}.json
"""

import logging
from datetime import datetime
from typing import List, Dict
from core.storage import storage
from core.log import log

logger = logging.getLogger(__name__)

_MAX_SUMMARIES = 10
_MIN_MESSAGES_FOR_SUMMARY = 2   # anche conversazioni brevi (1 scambio = 2 msg)
_UPDATE_EVERY_N_MESSAGES = 3    # aggiorna ogni 3 nuovi messaggi


class ConversationSummaryService:

    async def record_summary(self, user_id: str, conv_id: str, title: str, messages: list):
        """
        Genera e salva il sommario di una conversazione.
        Chiamato come background task dopo ogni N messaggi.
        """
        if len(messages) < _MIN_MESSAGES_FOR_SUMMARY:
            return

        key = f"conversation_summaries:{user_id}"
        summaries: List[Dict] = await storage.load(key, default=[])

        # Debounce: aggiorna solo se ci sono N nuovi messaggi rispetto all'ultimo sommario
        existing = next((s for s in summaries if s.get("conv_id") == conv_id), None)
        msg_count = len(messages)
        if existing and (msg_count - existing.get("msg_count", 0)) < _UPDATE_EVERY_N_MESSAGES:
            return

        # Genera sommario via LLM (gpt-4o-mini)
        try:
            from core.llm_service import llm_service

            # Trascrizione degli ultimi 20 messaggi
            lines = []
            for m in messages[-20:]:
                role = m.get("role", "")
                content = (m.get("content", "") or "")[:200]
                if role == "user":
                    lines.append(f"Utente: {content}")
                elif role in ("assistant", "genesi"):
                    lines.append(f"Genesi: {content}")
            transcript = "\n".join(lines)

            prompt = (
                "Questa è una conversazione tra un utente e Genesi (un'AI personale). "
                "Scrivi UN SOLO riassunto di 1-2 frasi che descriva i principali argomenti discussi. "
                "Sii specifico e concreto (es: 'L'utente ha parlato della guerra in Iran e dell'attività di Genesi su Moltbook'). "
                "NON scrivere frasi generiche come 'si è parlato di vari argomenti'.\n\n"
                f"Conversazione:\n{transcript}\n\nRiassunto:"
            )

            summary_text = await llm_service._call_model(
                "openai/gpt-4o-mini", prompt, "", user_id=user_id, route="memory"
            )
            if not summary_text:
                return
            summary_text = summary_text.strip()[:300]

        except Exception as e:
            logger.warning("CONV_SUMMARY_LLM_ERROR user=%s conv_id=%s err=%s", user_id, conv_id, e)
            return

        entry = {
            "conv_id": conv_id,
            "title": (title or "Conversazione")[:60],
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": summary_text,
            "msg_count": msg_count,
        }

        if existing:
            summaries[summaries.index(existing)] = entry
        else:
            summaries.append(entry)

        # Mantieni solo gli ultimi MAX_SUMMARIES
        if len(summaries) > _MAX_SUMMARIES:
            summaries = summaries[-_MAX_SUMMARIES:]

        await storage.save(key, summaries)
        log("CONV_SUMMARY_SAVED", user_id=user_id, conv_id=conv_id, msg_count=msg_count)

    async def get_context_block(self, user_id: str, current_conv_id: str = None) -> str:
        """
        Restituisce un blocco testo con i sommari delle conversazioni recenti
        (esclusa quella corrente), dal più recente al più vecchio.
        """
        key = f"conversation_summaries:{user_id}"
        summaries: List[Dict] = await storage.load(key, default=[])

        past = [s for s in summaries if s.get("conv_id") != current_conv_id]
        if not past:
            return ""

        # Ultimi 5, più recenti per primi
        past = list(reversed(past))[:5]

        lines = [f"• {s['date']}: {s['summary']}" for s in past]
        return "\n".join(lines)


conv_summary_service = ConversationSummaryService()
