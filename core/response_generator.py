from core.llm import generate_response as llm_generate
from typing import Optional, Dict, List
import json
from datetime import datetime


class ResponseGenerator:

    def generate_response(
        self,
        user_message: str,
        cognitive_state,
        recent_memories: List[Dict],
        relevant_memories: List[Dict],
        tone,
        intent: Dict,
        document_context: Optional[Dict] = None
    ) -> str:

        print(f"[RESPONSE_GENERATOR] intent={intent}", flush=True)

        # ===============================
        # GESTIONE DOCUMENTI / FILE
        # ===============================
        if document_context:
            prompt = self._build_document_prompt(
                user_message, document_context, recent_memories, relevant_memories
            )
            model = "gpt-4o"

        else:
            prompt = self._build_conversation_prompt(
                user_message, cognitive_state, recent_memories,
                relevant_memories, tone, intent
            )
            model = self._select_model(intent)

        # ===============================
        # CHIAMATA LLM
        # ===============================
        response = llm_generate({
            "prompt": prompt,
            "model": model,
            "intent": intent,
            "tone": tone
        })

        print(f"[RESPONSE_GENERATOR] response='{response[:200]}...'", flush=True)
        return response.strip()

    # ===============================
    # PROMPT CONVERSAZIONALE
    # ===============================
    def _build_conversation_prompt(
        self,
        user_message: str,
        cognitive_state,
        recent_memories: List[Dict],
        relevant_memories: List[Dict],
        tone,
        intent: Dict
    ) -> str:

        sections = []

        # --- CHI È L'UTENTE ---
        user_profile = cognitive_state.user.profile or {}
        if user_profile:
            identity_parts = []
            if user_profile.get("name"):
                identity_parts.append(f"Si chiama {user_profile['name']}.")
            if user_profile.get("profession"):
                identity_parts.append(f"Fa {user_profile['profession']}.")
            for key, val in user_profile.items():
                if key not in ("name", "profession") and isinstance(val, str):
                    identity_parts.append(f"{key}: {val}")
            if identity_parts:
                sections.append("CHI È:\n" + " ".join(identity_parts))

        # --- COSA RICORDI DI LUI ---
        memory_text = self._format_memories_human(recent_memories, relevant_memories)
        if memory_text:
            sections.append("COSA RICORDI DI LUI/LEI:\n" + memory_text)

        # --- STATO EMOTIVO DELLA CONVERSAZIONE ---
        tone_desc = self._describe_tone_human(tone)
        if tone_desc:
            sections.append("CLIMA DELLA CONVERSAZIONE:\n" + tone_desc)

        # --- CARATTERE RELAZIONALE ---
        if hasattr(cognitive_state, 'character') and cognitive_state.character:
            char = cognitive_state.character
            char_parts = []
            if char.get("empathy", 0.5) > 0.7:
                char_parts.append("La relazione è profonda, puoi essere più aperto.")
            if char.get("question_rate", 0.2) < 0.1:
                char_parts.append("Evita domande, questa persona preferisce che tu capisca da solo.")
            if char_parts:
                sections.append("NOTA RELAZIONALE:\n" + " ".join(char_parts))

        # --- MESSAGGIO ---
        sections.append(f"MESSAGGIO:\n{user_message}")

        # --- ISTRUZIONE FINALE ---
        if intent.get("depth") == "breve" or len(user_message.split()) <= 5:
            sections.append(
                "ISTRUZIONE: L'utente ha scritto poco. NON compensare con domande. "
                "Rispondi con una frase dichiarativa breve. Nessuna domanda. "
                "Rispondi come Genesi. Solo il testo della risposta, niente altro."
            )
        else:
            sections.append(
                "Rispondi come Genesi. Solo il testo della risposta, niente altro."
            )

        return "\n\n".join(sections)

    # ===============================
    # PROMPT DOCUMENTI
    # ===============================
    def _build_document_prompt(
        self,
        user_message: str,
        document_context: Dict,
        recent_memories: List[Dict],
        relevant_memories: List[Dict]
    ) -> str:

        document_mode = document_context.get("document_mode", "unknown")
        content = document_context.get("content", "")
        description = document_context.get("description", "Nessuna")
        ocr_reliability = document_context.get("ocr_reliability", "unknown")

        sections = []

        sections.append(
            f"FILE CARICATO:\n"
            f"- Tipo: {document_mode}\n"
            f"- Descrizione: {description}\n"
            f"- Affidabilità OCR: {ocr_reliability}"
        )

        if document_mode in ("text", "mixed") and content.strip():
            sections.append(f"CONTENUTO:\n{content}")
        elif document_mode == "image":
            sections.append(
                "Questo è un file immagine. Puoi descrivere il contesto generale "
                "ma non interpretare dettagli grafici."
            )

        # Memoria anche con documenti
        memory_text = self._format_memories_human(recent_memories, relevant_memories)
        if memory_text:
            sections.append("CONTESTO PERSONALE:\n" + memory_text)

        sections.append(f"DOMANDA:\n{user_message}")
        sections.append("Rispondi come Genesi. Solo il testo della risposta.")

        return "\n\n".join(sections)

    # ===============================
    # FORMATTAZIONE MEMORIE (UMANA)
    # ===============================
    def _format_memories_human(
        self,
        recent_memories: List[Dict],
        relevant_memories: List[Dict]
    ) -> str:

        seen = set()
        lines = []

        # Prima le memorie rilevanti (più importanti)
        for m in (relevant_memories or [])[:5]:
            text = self._extract_memory_text(m)
            if text and text not in seen:
                seen.add(text)
                lines.append(f"- {text}")

        # Poi le recenti (contesto temporale)
        for m in (recent_memories or [])[:5]:
            text = self._extract_memory_text(m)
            if text and text not in seen:
                seen.add(text)
                lines.append(f"- {text}")

        return "\n".join(lines) if lines else ""

    def _extract_memory_text(self, memory: Dict) -> str:
        content = memory.get("content", "")
        if isinstance(content, dict):
            return content.get("text", "").strip()
        if isinstance(content, str):
            return content.strip()
        return ""

    # ===============================
    # TONO → LINGUAGGIO NATURALE
    # ===============================
    def _describe_tone_human(self, tone) -> str:
        parts = []
        if tone.warmth > 0.6:
            parts.append("L'atmosfera è calda e accogliente.")
        if tone.empathy > 0.7:
            parts.append("C'è un forte bisogno emotivo.")
        elif tone.empathy < 0.3:
            parts.append("Il tono è distaccato, pragmatico.")
        if tone.directness > 0.7:
            parts.append("L'utente vuole risposte dirette.")
        return " ".join(parts) if parts else ""

    # ===============================
    # SCELTA MODELLO
    # ===============================
    def _select_model(self, intent: Dict) -> str:
        emotional_weight = intent.get("emotional_weight", 0.3)
        focus = intent.get("focus", "")

        if emotional_weight >= 0.5 or focus in ("presenza", "connessione", "identità"):
            return "gpt-4o"

        if focus in ("tecnico", "spiegazione", "analisi"):
            return "gpt-4o-mini"

        return "gpt-4o"
