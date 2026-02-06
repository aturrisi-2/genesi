from core.llm import generate_response as llm_generate
from core.tools import resolve_tools
from typing import Optional, Dict, List
import json
from datetime import datetime


class ResponseGenerator:

    async def generate_response(
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

        # ===============================
        # DUAL BRAIN ROUTING — CON TOOLS API
        # ===============================
        elif intent.get("brain_mode") == "fatti":
            # 1. Chiama API esterne per dati reali
            tool_result = await resolve_tools(user_message)
            # 2. Costruisci prompt arricchito con dati reali
            prompt = self._build_facts_prompt(user_message, tool_result)

        else:
            # Genesi-Relazione: prompt completo con memoria, tono, contesto
            prompt = self._build_conversation_prompt(
                user_message, cognitive_state, recent_memories,
                relevant_memories, tone, intent
            )

        # ===============================
        # CHIAMATA LLM (il routing modello avviene in llm.py)
        # ===============================
        response = llm_generate({
            "prompt": prompt,
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
        if len(user_message.split()) <= 5:
            sections.append(
                "ISTRUZIONE: L'utente ha scritto poco. Sii presente e discorsivo. "
                "Parla, commenta, rifletti — ma senza fare domande. "
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
    # PROMPT FATTUALE (GENESI-FATTI)
    # ===============================
    def _build_facts_prompt(self, user_message: str, tool_result: dict = None) -> str:
        sections = []

        if tool_result and tool_result.get("data") and not tool_result["data"].get("error"):
            tool_type = tool_result.get("tool_type", "unknown")
            data = tool_result["data"]

            if tool_type == "meteo":
                sections.append(self._format_weather_data(data))
            elif tool_type == "news":
                sections.append(self._format_news_data(data))
            elif tool_type == "economy":
                sections.append(self._format_economy_data(data))
            elif tool_type == "medical":
                sections.append(self._format_medical_data(data))

            print(f"[FATTI][LLM_SYNTHESIS] tool={tool_type} data_injected=True", flush=True)
        else:
            tool_type = tool_result.get("tool_type", "none") if tool_result else "none"
            print(f"[FATTI][LLM_SYNTHESIS] tool={tool_type} (no real data, solo LLM knowledge)", flush=True)

        sections.append(f"DOMANDA DELL'UTENTE:\n{user_message}")

        if tool_result and tool_result.get("data") and not tool_result["data"].get("error"):
            sections.append(
                "ISTRUZIONE: Usa i DATI REALI forniti sopra per rispondere. "
                "Sintetizza in modo chiaro e naturale in italiano. "
                "Non inventare dati aggiuntivi. Solo il testo della risposta."
            )
        else:
            sections.append(
                "Rispondi con le informazioni più accurate che conosci. "
                "Solo il testo della risposta."
            )

        return "\n\n".join(sections)

    def _format_weather_data(self, data: dict) -> str:
        lines = ["DATI METEO REALI (fonte: OpenWeatherMap):"]
        city = data.get("city", "")
        current = data.get("current", {})
        if current:
            lines.append(f"Città: {city}")
            lines.append(f"Ora: {current.get('description', '')}")
            lines.append(f"Temperatura: {current.get('temp', '')}°C (percepita {current.get('feels_like', '')}°C)")
            lines.append(f"Min/Max: {current.get('temp_min', '')}°C / {current.get('temp_max', '')}°C")
            lines.append(f"Umidità: {current.get('humidity', '')}%")
            lines.append(f"Vento: {current.get('wind_speed', '')} m/s")

        forecast = data.get("forecast", [])
        if forecast:
            lines.append("\nPrevisioni prossime ore:")
            for f in forecast[:6]:
                lines.append(f"  {f.get('datetime', '')}: {f.get('temp', '')}°C, {f.get('description', '')}, umidità {f.get('humidity', '')}%")

        return "\n".join(lines)

    def _format_news_data(self, data: dict) -> str:
        lines = [f"NOTIZIE REALI (fonte: GNews, aggiornate a {data.get('timestamp', 'ora')}):"]
        for art in data.get("articles", []):
            lines.append(f"- {art.get('title', '')}")
            desc = art.get('description', '')
            if desc:
                lines.append(f"  {desc[:200]}")
            source = art.get('source', '')
            if source:
                lines.append(f"  (fonte: {source})")
        return "\n".join(lines)

    def _format_economy_data(self, data: dict) -> str:
        lines = ["DATI ECONOMICI REALI:"]

        rates = data.get("exchange_rates", {})
        if rates:
            lines.append("Tassi di cambio (ECB):")
            for pair, val in rates.items():
                lines.append(f"  {pair}: {val}")

        gdp = data.get("italy_gdp_growth", [])
        if gdp:
            lines.append("Crescita PIL Italia (World Bank):")
            for entry in gdp:
                lines.append(f"  {entry['year']}: {entry['gdp_growth_pct']}%")

        unemp = data.get("italy_unemployment", [])
        if unemp:
            lines.append("Disoccupazione Italia (Eurostat):")
            for entry in unemp:
                lines.append(f"  {entry['period']}: {entry['rate_pct']}%")

        news = data.get("economic_news", [])
        if news:
            lines.append("Notizie economiche recenti:")
            for art in news:
                lines.append(f"  - {art.get('title', '')}")

        return "\n".join(lines)

    def _format_medical_data(self, data: dict) -> str:
        lines = ["INFORMAZIONI MEDICHE (fonti istituzionali):"]

        for info in data.get("medical_info", []):
            lines.append(f"\n{info.get('title', '')}:")
            lines.append(info.get('extract', ''))
            lines.append(f"(fonte: {info.get('source', '')})")

        disclaimer = data.get("disclaimer", "")
        if disclaimer:
            lines.append(f"\nNOTA: {disclaimer}")

        return "\n".join(lines)
