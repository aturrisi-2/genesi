from core.llm import generate_response as llm_generate
from core.local_llm import LocalLLM
from core.tools import resolve_tools
from core.genesi_response_engine import genesi_engine
from typing import Optional, Dict, List
import json
from datetime import datetime, timedelta
import re

class ResponseGenerator:
    """
    GENERATORE DI RISPOSTA FINALE - NUOVO PARADIGMA
    LLM produce solo intent, Genesi produce testo finale
    """

    async def generate_final_response(
        self,
        user_message: str,
        cognitive_state,
        recent_memories: List[Dict],
        relevant_memories: List[Dict],
        tone,
        intent: Dict,
        document_context: Optional[Dict] = None
    ) -> Dict:
        """
        GENERA RISPOSTA FINALE BASATA SU INTENT LLM
        LLM → intent strutturato, Genesi → testo finale
        """
        print(f"[GENESI_FINAL] Processing: '{user_message[:50]}...'", flush=True)
        
        # 1. OTTIENI INTENT DALL'LLM
        llm_intent = await self._extract_intent_from_llm(user_message, cognitive_state, tone)
        
        # 2. GENERA RISPOSTA FINALE CON GENESI ENGINE
        if llm_intent and isinstance(llm_intent, dict):
            print(f"[GENESI_FINAL] Using structured intent from LLM", flush=True)
            final_result = genesi_engine.generate_response_from_intent(llm_intent)
        else:
            print(f"[GENESI_FINAL] Using text fallback from LLM", flush=True)
            final_result = genesi_engine.generate_response_from_text(str(llm_intent))
        
        # 3. AGGIUNGI CONTESTO AGGIUNTIVO
        final_result["style"] = "psychological" if intent.get("type") == "psychological" else "standard"
        
        print(f"[GENESI_FINAL] Final response: '{final_result['final_text']}'", flush=True)
        return final_result

    async def _extract_intent_from_llm(self, user_message: str, cognitive_state, tone) -> Dict:
        """
        Estrai intent strutturato dall'LLM
        LLM NON deve produrre testo finale, solo intent
        """
        try:
            # Build prompt per intent extraction
            intent_prompt = self._build_intent_prompt(user_message, cognitive_state, tone)
            
            # Chiama LLM
            llm_response = llm_generate({
                "prompt": intent_prompt,
                "intent": {"type": "intent_extraction"},
                "tone": tone
            })
            
            print(f"[GENESI_LLM] Raw response: '{llm_response[:100]}...'", flush=True)
            
            # Prova a parsare come JSON strutturato
            try:
                import json
                intent_data = json.loads(llm_response)
                
                # Valida struttura
                if "intent" in intent_data and "confidence" in intent_data:
                    print(f"[GENESI_LLM] Structured intent: {intent_data}", flush=True)
                    return intent_data
                    
            except json.JSONDecodeError:
                print(f"[GENESI_LLM] Not JSON, treating as text fallback", flush=True)
            
            # Se non è JSON, usa come testo per pattern matching
            if genesi_engine.validate_llm_output(llm_response):
                # LLM ha prodotto solo intent breve, va bene
                return {"intent": "generic", "confidence": 0.5}
            else:
                # LLM ha prodotto troppo testo, scarta e usa generic
                print(f"[GENESI_LLM] LLM produced too much text, using generic", flush=True)
                return {"intent": "generic", "confidence": 0.3}
                
        except Exception as e:
            print(f"[GENESI_LLM] Error: {e}", flush=True)
            return {"intent": "generic", "confidence": 0.3}

    def _build_intent_prompt(self, user_message: str, cognitive_state, tone) -> str:
        """
        Build prompt per estrarre solo intent dall'LLM
        """
        sections = []
        
        # User info
        user_profile = cognitive_state.user.profile or {}
        if user_profile.get("name"):
            sections.append(f"UTENTE: {user_profile['name']}")
        
        # Message
        sections.append(f"MESSAGGIO:\n{user_message}")
        
        # Instructions for intent extraction
        sections.append(
            "ISTRUZIONI:\n"
            "- Analizza SOLO l'intent del messaggio\n"
            "- NON scrivere frasi complete\n"
            "- NON usare emoji o asterischi\n"
            "- Rispondi SOLO in questo formato JSON:\n"
            '{\n'
            '  "intent": "greeting|physical_discomfort|emotional_distress|acknowledgment|question|farewell|generic",\n'
            '  "confidence": 0.0-1.0\n'
            '}\n'
            "- Scegli l'intent più appropriato"
        )
        
        return "\n\n".join(sections)

    
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
                "ISTRUZIONE: Input breve. Rispondi in 1-2 frasi. "
                "Niente monologhi, niente espansioni. Diretto e naturale. "
                "Solo il testo della risposta."
            )
        else:
            sections.append(
                "ISTRUZIONE: Rispondi in modo conciso. Massimo 3-4 frasi. "
                "Solo il testo della risposta."
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

        for m in (relevant_memories or [])[:5]:
            text = self._extract_memory_text(m)
            if text and text not in seen and not self._is_noise(m, text):
                seen.add(text)
                lines.append(f"- {text}")

        for m in (recent_memories or [])[:5]:
            text = self._extract_memory_text(m)
            if text and text not in seen and not self._is_noise(m, text):
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

    def _is_noise(self, memory: Dict, text: str) -> bool:
        """Filtra memorie che non devono entrare nel prompt RELAZIONE."""
        mem_type = memory.get("type", "")
        if mem_type == "system_response":
            return True
        if mem_type == "document_context":
            return True
        text_lower = text.lower()
        noise_phrases = [
            "dati meteo", "openweather", "gnews", "ecb", "eurostat",
            "world bank", "notizie principali", "previsioni", "°c con",
            "umidità al", "vento a", "eur/usd",
        ]
        if any(p in text_lower for p in noise_phrases):
            return True
        return False

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
                "ISTRUZIONE OBBLIGATORIA: Riformula ESCLUSIVAMENTE i dati reali forniti sopra. "
                "I dati sono verificati e aggiornati. NON puoi ignorarli. "
                "NON dire che non hai accesso a dati. NON menzionare limiti o fonti. "
                "NON aggiungere contesto temporale inventato. "
                "Riscrivi i dati in italiano naturale, come un notiziario. Solo il testo."
            )
            print(f"[FATTI][FORCED_REAL_DATA_RESPONSE] type={tool_result.get('tool_type','?')} prompt_mode=RIFORMULAZIONE_OBBLIGATORIA", flush=True)
        else:
            sections.append(
                "Rispondi con le informazioni più accurate che conosci. "
                "Solo il testo della risposta."
            )

        return "\n\n".join(sections)

    # ===============================
    # BYPASS LLM — TEMPLATE DIRETTO
    # ===============================
    def _direct_template(self, tool_result: dict) -> str:
        """Genera risposta diretta da dati API senza passare per LLM."""
        tool_type = tool_result.get("tool_type")
        data = tool_result.get("data", {})

        if tool_type == "meteo":
            return self._direct_weather(data)
        elif tool_type == "news":
            return self._direct_news(data)
        return ""

    def _direct_weather(self, data: dict) -> str:
        city = data.get("city", "la tua zona")
        current = data.get("current", {})
        forecast = data.get("forecast", [])

        if not current:
            return ""

        temp = current.get("temp", "")
        feels = current.get("feels_like", "")
        desc = current.get("description", "")
        humidity = current.get("humidity", "")
        wind = current.get("wind_speed", "")
        t_min = current.get("temp_min", "")
        t_max = current.get("temp_max", "")

        parts = []
        parts.append(f"A {city} adesso ci sono {temp}°C con {desc}, percepiti come {feels}°C.")
        parts.append(f"La minima è {t_min}°C e la massima {t_max}°C, con umidità al {humidity}% e vento a {wind} m/s.")

        # Previsioni prossime ore
        if forecast:
            # Raggruppa per domani
            tomorrow_entries = []
            now = datetime.now()
            tomorrow_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            for f in forecast:
                dt_str = f.get("datetime", "")
                if tomorrow_date in dt_str:
                    tomorrow_entries.append(f)

            if tomorrow_entries:
                temps = []
                for f in tomorrow_entries:
                    try:
                        temps.append(float(f.get("temp", 0)))
                    except (TypeError, ValueError):
                        pass
                descs = [f.get("description", "") for f in tomorrow_entries]
                if temps:
                    t_min_f = f"{min(temps):.1f}"
                    t_max_f = f"{max(temps):.1f}"
                    desc_f = max(set(descs), key=descs.count) if descs else ""
                    parts.append(f"Domani si prevedono temperature tra {t_min_f}°C e {t_max_f}°C, con {desc_f}.")
            elif len(forecast) >= 3:
                # Prossime ore
                next_f = forecast[2]  # ~9h avanti
                parts.append(f"Nelle prossime ore: {next_f.get('temp', '')}°C, {next_f.get('description', '')}.")

        return " ".join(parts)

    def _direct_news(self, data: dict) -> str:
        articles = data.get("articles", [])
        if not articles:
            return ""

        parts = ["Ecco le notizie principali di oggi."]
        for i, art in enumerate(articles[:5]):
            title = art.get("title", "").strip()
            desc = art.get("description", "").strip()
            source = art.get("source", "").strip()
            if title:
                entry = title
                if desc and len(desc) > 30:
                    # Prendi solo la prima frase della descrizione
                    first_sentence = desc.split(".")[0].strip()
                    if first_sentence and first_sentence != title:
                        entry += f". {first_sentence}."
                if source:
                    entry += f" ({source})"
                parts.append(entry)

        return " ".join(parts)

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
