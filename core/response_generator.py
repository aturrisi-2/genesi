from core.llm import generate_response as llm_generate
from core.local_llm import LocalLLM
from core.tools import resolve_tools
from typing import Optional, Dict, List
import json
from datetime import datetime, timedelta

# ========================================
# MODO FORZATO PERSONALPLEX 7B (DISABILITATO)
# ========================================
FORCE_LOCAL_LLM = False


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

        # ========================================
        # MODO FORZATO PERSONALPLEX 7B (TEMPORANEO)
        # ========================================
        if FORCE_LOCAL_LLM:
            print(f"[FORCED_LOCAL_LLM] IGNORING Proactor decision", flush=True)
            print(f"[FORCED_LOCAL_LLM] PersonalPlex 7B called with: '{user_message}'", flush=True)
            
            try:
                # Chiamata diretta a PersonalPlex 7B
                local_llm = LocalLLM()
                response_text = local_llm.generate(user_message)
                
                if response_text and len(response_text.strip()) > 0:
                    response_text = response_text.strip()
                    print(f"[FORCED_LOCAL_LLM] PersonalPlex 7B response: '{response_text[:100]}...'", flush=True)
                    print(f"[FORCED_LOCAL_LLM] PersonalPlex 7B SUCCESS", flush=True)
                    return response_text
                else:
                    print(f"[FORCED_LOCAL_LLM] PersonalPlex 7B empty response", flush=True)
                    print(f"[FORCED_LOCAL_LLM] Fallback to GPT", flush=True)
                    # Continua con GPT come fallback
                    
            except Exception as e:
                print(f"[FORCED_LOCAL_LLM] PersonalPlex 7B error: {e}", flush=True)
                print(f"[FORCED_LOCAL_LLM] Fallback to GPT", flush=True)
                # Continua con GPT come fallback

        # ===============================
        # PROACTOR DECISION CHECK
        # ===============================
        
        # SE PROACTOR HA BLOCCATO → NON CHIAMARE CHATGPT
        if not intent.get("should_respond", True):
            decision = intent.get("decision", "silence")
            reason = intent.get("reason", "proactor_block")
            print(f"[RESPONSE_GENERATOR] PROACTOR_BLOCKED decision={decision} reason={reason}", flush=True)
            print(f"[CHATGPT] called=false", flush=True)
            return ""  # Silenzio assoluto
        
        # SE PROACTOR DECIDE SILENZIO → NON CHIAMARE CHATGPT
        if intent.get("decision") == "silence":
            reason = intent.get("reason", "silence_decision")
            print(f"[RESPONSE_GENERATOR] PROACTOR_SILENCE reason={reason}", flush=True)
            print(f"[CHATGPT] called=false", flush=True)
            return ""  # Silenzio assoluto

        # ===============================
        # CLOSURE INTENT HANDLING (PRE-LLM)
        # ===============================
        if intent.get("type") == "closure":
            level = intent.get("closure_level", "soft")
            # Determine if previous response was long/psycho (simplified: check recent memories for system_response length)
            prev_long = any(
                e.get("type") == "system_response" and len(str(e.get("content", {}).get("text", ""))) > 100
                for e in recent_memories[-2:]
            )
            if level == "soft":
                if prev_long:
                    response = "Va bene."
                else:
                    response = ""  # Silence
                print(f"[INTENT_CLOSURE] level=soft action={'response' if response else 'silence'}", flush=True)
                return response
            elif level == "hard":
                response = "Ok."
                print(f"[INTENT_CLOSURE] level=hard action=minimal", flush=True)
                return response
            elif level == "transition":
                response = "Va bene. Dimmi."
                print(f"[INTENT_CLOSURE] level=transition action=aggancio", flush=True)
                return response

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
            has_real_data = (
                tool_result
                and tool_result.get("data")
                and not tool_result["data"].get("error")
            )

            # 2. BYPASS LLM: meteo e news con dati reali → template diretto
            if has_real_data and tool_result["tool_type"] in ("meteo", "news"):
                direct = self._direct_template(tool_result)
                if direct:
                    print(f"[FATTI][FORCED_REAL_DATA_RESPONSE] type={tool_result['tool_type']} bypass_llm=True", flush=True)
                    print(f"[RESPONSE_GENERATOR] response='{direct[:200]}...'", flush=True)
                    return direct

            # 3. Segnala al LLM che ci sono dati reali (per system prompt RIFORMULATORE)
            if has_real_data:
                intent["_has_real_data"] = True

            # 4. Costruisci prompt arricchito con dati reali
            prompt = self._build_facts_prompt(user_message, tool_result)

        else:
            # Genesi-Relazione: prompt completo con memoria, tono, contesto
            prompt = self._build_conversation_prompt(
                user_message, cognitive_state, recent_memories,
                relevant_memories, tone, intent
            )

        # ===============================
        # CONTROLLO RISPOSTA PERSONALPLEX PRIMA DI GPT
        # ===============================
        if intent.get("reason") == "personalplex_primary" and "personalplex_response" in intent:
            # Usa risposta PersonalPlex dal Proactor
            response = intent["personalplex_response"]
            print(f"[RESPONSE_GENERATOR] using PERSONALPLEX response='{response[:200]}...'", flush=True)
            return response.strip()
        
        # ===============================
        # CHIAMATA LLM (il routing modello avviene in llm.py)
        # ===============================
        if FORCE_LOCAL_LLM:
            print(f"[FORCED_LOCAL_LLM] Fallback to GPT", flush=True)
        print(f"[CHATGPT] called=true", flush=True)
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
