"""
MOTORI DI GENERAZIONE - Separazione netta delle responsabilità
Ogni motore ha UN SOLO compito specifico
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import asyncio
import re

class BaseEngine(ABC):
    """Base class per tutti i motori"""
    
    @abstractmethod
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """Genera risposta - metodo obbligatorio"""
        pass
    
    @abstractmethod
    def can_handle(self, intent_type: str) -> bool:
        """Verifica se può gestire l'intent"""
        pass

class DateTimeEngine(BaseEngine):
    """
    DATE_TIME - Solo per data e ora corrente
    Usa Python datetime, nessun LLM
    """
    
    def __init__(self):
        pass
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta con data/ora corrente in italiano
        """
        from datetime import datetime
        import locale
        
        try:
            # Imposta locale italiano
            locale.setlocale(locale.LC_TIME, 'it_IT.UTF-8')
        except:
            pass  # Fallback se locale non disponibile
        
        now = datetime.now()
        
        # Pattern di richiesta
        msg_lower = message.lower()
        
        if "giorno" in msg_lower:
            # Nome del giorno
            day_name = now.strftime("%A")
            date_str = now.strftime("%d %B %Y")
            return f"Oggi è {day_name}, {date_str}"
        
        elif "ora" in msg_lower:
            # Ora corrente
            time_str = now.strftime("%H:%M")
            return f"Sono le ore {time_str}"
        
        elif "data" in msg_lower:
            # Data completa
            date_str = now.strftime("%d/%m/%Y")
            day_name = now.strftime("%A")
            return f"Oggi è {day_name} {date_str}"
        
        else:
            # Risposta di default
            date_str = now.strftime("%d/%m/%Y %H:%M")
            day_name = now.strftime("%A")
            return f"È {day_name} {date_str}"
    
    def can_handle(self, intent_type: str) -> bool:
        """DateTime gestisce solo date_time"""
        return intent_type == "date_time"

class GPTFullEngine(BaseEngine):
    """
    GPT-FULL - Solo per fatti verificabili
    Usato per: meteo, news, spiegazioni tecniche, definizioni, psicologico
    """
    
    def __init__(self):
        from core.llm import generate_gpt_full_response as llm_generate
        self.llm_generate = llm_generate
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta con GPT-full - testo pulito, niente teatralità
        """
        print(f"[GPT_FULL] Generating factual response", flush=True)
        
        try:
            # Prompt per GPT-full - solo fatti
            prompt = self._build_factual_prompt(message, params.get("intent_type", ""))
            
            # Costruisci payload corretto per generate_response()
            payload = {
                "prompt": prompt,
                "tone": params.get("tone", "neutral"),
                "intent": {
                    "brain_mode": "factual",
                    "intent_type": params.get("intent_type", "medical_info")
                }
            }
            
            response = self.llm_generate(payload)
            
            return response.strip()
            
        except Exception as e:
            print(f"[GPT_FULL] Error: {e}", flush=True)
            return "Non posso fornire questa informazione in questo momento."
    
    def can_handle(self, intent_type: str) -> bool:
        """GPT-full gestisce intent fattuali"""
        return intent_type in [
            "medical_info", "historical_info", "definition", 
            "technical", "identity", "other"
        ]
    
    def _build_factual_prompt(self, message: str, intent_type: str) -> str:
        """
        Costruisce prompt per GPT-full - solo fatti
        """
        base_prompt = """Rispondi in modo fattuale e conciso.

REGOLE ASSOLUTE:
- SOLO informazioni verificabili
- Niente opinioni personali
- Niente teatralità o emoji
- Niente conversazione personale
- Massimo 2-3 frasi

"""
        
        if intent_type == "medical_info":
            base_prompt += "Fornisci informazioni mediche generali. Aggiungi sempre: 'Per problemi specifici consulta un medico'."
        elif intent_type == "historical_info":
            base_prompt += "Fornisci informazioni storiche accurate e concise."
        elif intent_type == "definition":
            base_prompt += "Spiega il concetto in modo semplice e tecnico."
        elif intent_type == "identity":
            base_prompt += "Rispondi in modo amichevole ma conciso."
        else:
            base_prompt += "Rispondi in modo informativo e diretto."
        
        return f"{base_prompt}\n\nDomanda: {message}\nRisposta:"

class PsychologicalEngine(BaseEngine):
    """
    MOTORE PSICOLOGICO - Supporto emotivo con GPT_FULL
    Usa conoscenze psicologiche standard, linguaggio empatico
    """
    
    def __init__(self):
        from core.llm import generate_gpt_full_response as llm_generate
        self.llm_generate = llm_generate
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta psicologica empatica e supportiva
        """
        print(f"[PSYCHOLOGICAL] Generating empathetic response", flush=True)
        
        try:
            # Prompt psicologico - empatico ma non diagnostico
            prompt = self._build_psychological_prompt(message, params.get("emotional_weight", 0.5))
            
            # Costruisci payload per generate_response()
            payload = {
                "prompt": prompt,
                "tone": "empathetic",
                "intent": {
                    "brain_mode": "support",
                    "intent_type": "emotional_support"
                }
            }
            
            response = self.llm_generate(payload)
            
            return response.strip()
            
        except Exception as e:
            print(f"[PSYCHOLOGICAL] Error: {e}", flush=True)
            return "Capisco che questo momento sia difficile. Sono qui per ascoltarti."
    
    def can_handle(self, intent_type: str) -> bool:
        """Motore psicologico gestisce supporto emotivo"""
        return intent_type in ["emotional_support", "psychological"]
    
    def _build_psychological_prompt(self, message: str, emotional_weight: float) -> str:
        """
        Costruisce prompt psicologico - empatico ma non diagnostico
        """
        base_prompt = """Rispondi in modo empatico e supportivo.

REGOLE ASSOLUTE:
- Usa linguaggio calmo e normalizzante
- NON fare diagnosi
- NON suggerire terapie specifiche
- Fornisci supporto emotivo generale
- Normalizza i sentimenti espressi
- Suggerisci strategie di coping generali
- Se necessario, suggerisci aiuto professionale
- Massimo 3-4 frasi
"""

        if emotional_weight >= 0.7:
            base_prompt += """
Il messaggio mostra alto distress emotivo.
Rispondi con particolare empatia e validazione.
Includi: "È normale sentirsi così in certi momenti".
"""
        elif emotional_weight >= 0.5:
            base_prompt += """
Il messaggio mostra moderato distress emotivo.
Rispondi con supporto empatico e incoraggiamento.
"""
        else:
            base_prompt += """
Il messaggio mostra lieve distress emotivo.
Rispondi con supporto generale e incoraggiamento.
"""
        
        return f"{base_prompt}\n\nMessaggio: {message}\nRisposta:"

class PersonalplexEngine(BaseEngine):
    """
    PERSONALPLEX - SOLO per chat libera e relazione
    REGOLE: solo italiano, max 2 frasi, EMOJI CONSENTITE
    """
    
    def __init__(self):
        from core.local_llm import LocalLLM
        self.local_llm = LocalLLM()
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        ❌ PERSONALPLEX NON GENERA PIÙ TESTO
        ORCHESTRATORE PURO - DELEGA A MISTRAL
        """
        print(f"[PERSONALPLEX] ORCHESTRATORE PURO - delegating to Mistral", flush=True)
        
        # DELEGA A MISTRAL via LocalLLM (che ora usa Mistral)
        try:
            from core.local_llm import local_llm
            
            # Prompt BISTURI V2 DEFINITIVO - stringo vincolo semantico
            prompt = f"""Sei Genesi.
Parli sempre e solo in italiano.

Rispondi SOLO al messaggio dell'utente.
NON aggiungere esempi, storie, ricordi o descrizioni inventate.
NON parlare di te se non richiesto esplicitamente.
NON anticipare domande future.
NON cambiare argomento.

Usa frasi brevi e dirette.
Massimo 1-2 frasi.

Stile:
calmo, umano, presente.

Messaggio utente:
{message}"""
            
            response = local_llm.generate(
                prompt=prompt,
                max_tokens=80,   # n_predict = 80
                temperature=0.35  # Come richiesto
            )
            
            # Post-processing minimo
            response = self._enforce_personalplex_rules(response)
            return response.strip()
            
        except Exception as e:
            print(f"[PERSONALPLEX] Mistral delegation failed: {e}", flush=True)
            return "Ah, non so cosa dire..."
    
    def _enforce_personalplex_rules(self, response: str) -> str:
        """Applica regole PersonalPlex - LIBERO DALLE CATENE"""
        if not response:
            return response
        
        # SOLO pulizia base - niente più vincoli!
        # Rimuovi solo caratteri davvero problematici
        response = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', response)
        
        # Pulizia spazi multipli
        response = re.sub(r'\s+', ' ', response)
        
        return response.strip()
    
    def can_handle(self, intent_type: str) -> bool:
        """PersonalPlex gestisce SOLO chat_free"""
        return intent_type == "chat_free"
    
    def _build_conversational_prompt(self, message: str, context: Optional[Dict] = None) -> str:
        """
        Costruisce prompt per PersonalPlex - solo conversazione
        """
        base_prompt = """Sei Genesi. Rispondi in modo naturale e conversazionale.

REGOLE:
- Sii amichevole e naturale
- Massimo 1-2 frasi
- Niente fatti tecnici
- Niente teatralità o emoji

"""
        
        return f"{base_prompt}\nUtente: {message}\nGenesi:"

class APIToolsEngine(BaseEngine):
    """
    API TOOLS - Solo per API esterne
    Usato per: meteo, news
    """
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Chiama API esterne per meteo/news
        """
        intent_type = params.get("intent_type", "")
        print(f"[API_TOOLS] Calling API for intent: {intent_type}", flush=True)
        print(f"[DEBUG_API_TOOLS] message: {message}", flush=True)
        
        try:
            if intent_type == "weather":
                # Estrai città dal messaggio
                location = self._extract_location(message)
                print(f"[DEBUG_API_TOOLS] extracted location: {location}", flush=True)
                return await self._get_weather(location)
            elif intent_type == "news":
                return await self._get_news(message)
            else:
                return "Servizio non disponibile."
                
        except Exception as e:
            print(f"[API_TOOLS] Error: {e}", flush=True)
            return "Non riesco a ottenere informazioni in questo momento."
    
    def _extract_location(self, message: str) -> str:
        """Estrae città dal messaggio meteo con normalizzazione preposizioni"""
        # Normalizza il testo rimuovendo preposizioni comuni
        normalized_message = message.lower()
        prepositions = [" a ", " su ", " per ", " di ", " nel ", " nella ", " in "]
        
        for prep in prepositions:
            normalized_message = normalized_message.replace(prep, " ")
        
        # Ricostruisci il messaggio normalizzato per l'estrazione
        words = normalized_message.split()
        normalized_message = " ".join(words)
        
        print(f"[DEBUG_WEATHER] normalized message: '{normalized_message}'", flush=True)
        
        # Usa extract_city sul messaggio normalizzato
        from core.tools import extract_city
        location = extract_city(normalized_message)
        
        print(f"[DEBUG_WEATHER] extracted location: '{location}'", flush=True)
        return location if location else "Roma"
    
    def can_handle(self, intent_type: str) -> bool:
        """API tools gestiscono meteo e news"""
        return intent_type in ["weather", "news"]
    
    async def _get_weather(self, location: str) -> str:
        """Ottiene meteo da location usando API reali"""
        print(f"[DEBUG_WEATHER] _get_weather called with location: {location}", flush=True)
        
        try:
            from core.tools import fetch_weather
            print(f"[DEBUG_WEATHER] calling fetch_weather API", flush=True)
            
            weather_data = await fetch_weather(f"che tempo fa a {location}")
            print(f"[DEBUG_WEATHER] API response received", flush=True)
            
            if "error" in weather_data:
                print(f"[DEBUG_WEATHER] API error: {weather_data['error']}", flush=True)
                return f"Non riesco a ottenere informazioni meteo per {location}."
            
            # Estrai dati meteo
            current = weather_data.get("current", {})
            city = weather_data.get("city", location)
            
            if current:
                # Arrotonda i valori per TTS friendly
                temp_raw = current.get("temp", 0)
                description = current.get("description", "condizioni sconosciute")
                humidity_raw = current.get("humidity", 0)
                wind_speed_raw = current.get("wind_speed", 0)
                
                # Arrotonda a interi
                temp = int(round(float(temp_raw))) if temp_raw != "N/A" else 0
                humidity = int(round(float(humidity_raw))) if humidity_raw != "N/A" else 0
                wind_speed = int(round(float(wind_speed_raw))) if wind_speed_raw != "N/A" else 0
                
                # Costruisci risposta TTS friendly con emoji
                weather_emoji = self._get_weather_emoji(description)
                
                # Determina descrizione vento
                if wind_speed > 0:
                    if wind_speed <= 5:
                        wind_desc = "debole"
                    elif wind_speed <= 15:
                        wind_desc = "moderato"
                    elif wind_speed <= 25:
                        wind_desc = "forte"
                    else:
                        wind_desc = "molto forte"
                else:
                    wind_desc = "assente"
                
                response = f"{weather_emoji} **{city}** {weather_emoji}\n{temp}°C, {description}\n💧 Umidità {humidity}%\n🌬️ Vento {wind_desc}"
                
                print(f"[DEBUG_WEATHER] response built (TTS friendly): {response}", flush=True)
                return response
            else:
                print(f"[DEBUG_WEATHER] no current data in response", flush=True)
                return f"Dati meteo non disponibili per {location}."
                
        except Exception as e:
            print(f"[DEBUG_WEATHER] Exception in _get_weather: {e}", flush=True)
            return f"Errore nel recupero dati meteo per {location}."
    
    async def _get_news(self, message: str = "") -> str:
        """Ottiene notizie reali da API con robustezza e fallback"""
        print(f"[DEBUG_NEWS] _get_news called", flush=True)
        
        try:
            from core.tools import fetch_news
            print(f"[DEBUG_NEWS] calling fetch_news API", flush=True)
            
            news_data = await fetch_news(message)
            print(f"[DEBUG_NEWS] API response received", flush=True)
            
            # GESTIONE ERRORI API
            if "error" in news_data:
                print(f"[DEBUG_NEWS] API error: {news_data['error']}", flush=True)
                return self._get_news_fallback(message)
            
            # GESTIONE PAYLOAD VUOTO
            if not news_data or not isinstance(news_data, dict):
                print(f"[DEBUG_NEWS] empty or invalid payload", flush=True)
                return self._get_news_fallback(message)
            
            # Estrai articoli
            articles = news_data.get("articles", [])
            print(f"[DEBUG_NEWS] total_articles={len(articles)}", flush=True)
            
            # GESTIONE NESSUN ARTICOLO
            if not articles:
                print(f"[DEBUG_NEWS] no articles found", flush=True)
                return self._get_news_fallback(message)
            
            # Estrai località dal messaggio
            location = self._extract_location_from_message(message)
            print(f"[DEBUG_NEWS] location_filter={location}", flush=True)
            
            # Applica filtro per località se specificata
            if location and location.lower() != "italia":
                filtered_articles = self._filter_news_by_location(articles, location)
                print(f"[DEBUG_NEWS] filtered_articles={len(filtered_articles)}", flush=True)
                
                # Se dopo il filtro ci sono meno di 2 articoli, usa fallback esplicito
                if len(filtered_articles) < 2:
                    print(f"[DEBUG_NEWS] insufficient local articles: {len(filtered_articles)}", flush=True)
                    return self._get_news_fallback(message)
                
                articles = filtered_articles
            else:
                print(f"[DEBUG_NEWS] using all articles (no location filter)", flush=True)
            
            # Costruisci risposta TTS friendly con max 2 articoli approfonditi
            response_parts = []
            
            # Prendi solo i primi 2 articoli e approfondisci
            for i, article in enumerate(articles[:2]):
                title = article.get("title", "").strip()
                description = article.get("description", "").strip()
                source = article.get("source", "").strip()
                
                # Rimuovi fonti e date ma mantieni il contenuto
                title = self._clean_news_text(title)
                description = self._clean_news_text(description)
                
                if title and len(title) > 10:
                    # Costruisci risposta approfondita con formato OBBLIGATORIO
                    if i == 0:
                        # Prima notizia con formato completo
                        category = self._get_news_category(title, description)
                        emoji = self._get_news_emoji(category)
                        
                        news_part = f"📰 **{location} – {category}** 📰\n"
                        news_part += f"👉 {title} 👉\n"
                        news_part += f"📍 {relevance} 📍"
                        
                        # Aggiungi dettagli se disponibili
                        if description and len(description) > 30:
                            # Estrai la frase più importante
                            sentences = description.split('.')
                            if sentences:
                                detail_sentence = sentences[0].strip()
                                if len(detail_sentence) > 20:
                                    news_part += f" {detail_sentence}. 🔥"
                        
                        response_parts.append(news_part)
                    else:
                        # Seconda notizia più breve ma ricca di emoji
                        category = self._get_news_category(title, description)
                        emoji = self._get_news_emoji(category)
                        
                        news_part = f"{emoji} {title} ⚠️"
                        if description and len(description) > 30:
                            sentences = description.split('.')
                            if sentences:
                                first_sentence = sentences[0].strip()
                                if len(first_sentence) > 20:
                                    news_part += f" {first_sentence}. 📢"
                        
                        response_parts.append(news_part)
            
            if response_parts:
                # Unisci le notizie con formattazione
                final_response = "\n\n".join(response_parts)
                print(f"[DEBUG_NEWS] response built (deep format): {final_response[:100]}...", flush=True)
                return final_response
            else:
                print(f"[DEBUG_NEWS] no valid content found", flush=True)
                return self._get_news_fallback(message)
                
        except Exception as e:
            print(f"[DEBUG_NEWS] Exception in _get_news: {e}", flush=True)
            return self._get_news_fallback(message)
    
    def _get_news_fallback(self, message: str) -> str:
        """Fallback strutturato per news"""
        location = self._extract_location_from_message(message)
        
        if location and location.lower() != "italia":
            return f"📰 **{location} – Attualità**\n👉 Oggi poche notizie locali verificabili su {location}.\n📍 Ecco cosa sta emergendo a livello cittadino: monitoriamo gli eventi principali che potrebbero interessare i residenti."
        else:
            return "📰 **Attualità**\n👉 Oggi poche notizie verificabili disponibili.\n📍 Stiamo monitorando gli eventi principali a livello nazionale."
    
    def _extract_location_from_message(self, message: str) -> str:
        """Estrae località dal messaggio news"""
        message_lower = message.lower()
        
        # Pattern per notizie su località
        for pattern in ["notizie su ", "notizie di ", "notizie da ", "notizie a "]:
            idx = message_lower.find(pattern)
            if idx >= 0:
                rest = message[idx + len(pattern):].strip()
                # Prendi solo la prima parola come località
                if rest:
                    location = rest.split()[0].strip()
                    return location.capitalize()
        
        # Prova con extract_city come fallback
        try:
            from core.tools import extract_city
            location = extract_city(message)
            return location if location != "Roma" else ""
        except:
            return ""
    
    def _filter_news_by_location(self, articles: list, location: str) -> list:
        """Filtra articoli SOLO per località con criteri severi"""
        location_lower = location.lower()
        
        # Parole chiave locali ESCLUSIVE per Roma
        rome_keywords = [
            "roma", "romano", "romana", "capitale", "lazio",
            # Quartieri e zone specifiche
            "trastevere", "tridente", "testaccio", "prati", "monti", "esquilino",
            "tuscolano", "appio", "eur", "garbatella", "pigneto", "san lorenzo",
            "campidoglio", "quirinale", "vaticano", "trastevere",
            # Istituzioni locali
            "comune di roma", "sindaco di roma", "municipio", "atac", "roma servizi",
            # Luoghi specifici
            "colosseo", "fori imperiali", "piazza navona", "fontana di trevi",
            "pantheon", "circo massimo", "bocca della verità", "castel sant'angelo",
            # Infrastrutture
            "metro a", "metro b", "linea a", "linea b", "termini", "tiburtina",
            "grande raccordo anulare", "gra", "autostrada roma"
        ]
        
        # Parole chiave per altre città
        city_keywords = {
            "milano": ["milano", "milanese", "lombardia", "duomo", "piazza del duomo", "atm", "comune di milano"],
            "napoli": ["napoli", "napoletano", "campania", "municipio di napoli", "anm"],
            "torino": ["torino", "torinese", "piemonte", "municipio", "gtt"],
            "bologna": ["bologna", "bolognese", "emilia", "romagna", "tper"],
            "firenze": ["firenze", "fiorentino", "toscana", "palazzo vecchio", "autolinee toscane"],
            "genova": ["genova", "genovese", "liguria", "amt"],
            "palermo": ["palermo", "palermitano", "sicilia", "amat"]
        }
        
        # Ottieni parole chiave per la località
        if location_lower == "roma":
            keywords = rome_keywords
        else:
            keywords = city_keywords.get(location_lower, [location_lower])
        
        filtered_articles = []
        for article in articles:
            title = article.get("title", "").lower()
            description = article.get("description", "").lower()
            
            # SCARTA contenuti non locali
            if self._is_non_local_content(title, description):
                continue
            
            # Controlla se contiene parole chiave LOCALI ESCLUSIVE
            if any(keyword in title for keyword in keywords):
                filtered_articles.append(article)
            elif any(keyword in description for keyword in keywords):
                filtered_articles.append(article)
        
        return filtered_articles
    
    def _is_non_local_content(self, title: str, description: str) -> bool:
        """Scarta contenuti non locali"""
        text = (title + " " + description).lower()
        
        # SCARTA questi contenuti
        non_local_patterns = [
            # Oroscopo e astrologia
            "oroscopo", "oroscopo della settimana", "segno zodiacale", "ariete", "toro", "gemelli",
            "cancro", "leone", "vergine", "bilancia", "scorpione", "sagittario", "capricorno", 
            "acquario", "pesci",
            
            # Sport nazionale non locale
            "serie a", "serie b", "champions league", "europa league", "nazionale italiana",
            "juventus", "milan", "inter",
            
            # Economia nazionale
            "borsa italiana", "ftse mib", "spread", "btp", "banca d'italia", "economia nazionale",
            
            # Spettacolo nazionale
            "sanremo", "festival di sanremo", "cinema italiano", "tv italiana",
            
            # Politica nazionale
            "governo nazionale", "consiglio dei ministri", "palazzo chigi", "presidente del consiglio",
            
            # Internazionale
            "ue", "unione europea", "nato", "onu", "stati uniti", "cina", "russia"
        ]
        
        return any(pattern in text for pattern in non_local_patterns)
    
    def _get_news_category(self, title: str, description: str) -> str:
        """Determina la categoria della notizia"""
        text = (title + " " + description).lower()
        
        if any(word in text for word in ["metro", "bus", "traffico", "autostrada", "treno", "aeroporto"]):
            return "Trasporti"
        elif any(word in text for word in ["comune", "sindaco", "municipio", "regione", "provincia"]):
            return "Politica"
        elif any(word in text for word in ["scuola", "università", "studenti", "didattica"]):
            return "Istruzione"
        elif any(word in text for word in ["ospedale", "sanità", "medico", "paziente", "asl"]):
            return "Sanità"
        elif any(word in text for word in ["lavoro", "impiego", "disoccupazione", "sciopero"]):
            return "Lavoro"
        elif any(word in text for word in ["cultura", "museo", "teatro", "cinema", "concerto"]):
            return "Cultura"
        elif any(word in text for word in ["sport", "calcio", "stadio", "squadra"]):
            return "Sport"
        elif any(word in text for word in ["economia", "azienda", "negozio", "commercio"]):
            return "Economia"
        else:
            return "Attualità"
    
    def _get_news_emoji(self, category: str) -> str:
        """Restituisce l'emoji appropriata per la categoria"""
        emoji_map = {
            "Trasporti": "🚇",
            "Politica": "🏛️",
            "Istruzione": "🎓",
            "Sanità": "🏥",
            "Lavoro": "💼",
            "Cultura": "🎭",
            "Sport": "⚽",
            "Economia": "💰",
            "Attualità": "📰"
        }
        return emoji_map.get(category, "📰")
    
    def _get_relevance_context(self, sentence: str, location: str) -> str:
        """Genera contesto di rilevanza per la località"""
        location_lower = location.lower()
        sentence_lower = sentence.lower()
        
        # Pattern di rilevanza per Roma
        if location_lower == "roma":
            if any(word in sentence_lower for word in ["centro", "storico", "colosseo", "vaticano"]):
                return "Questo interessa chi vive o visita il centro storico. "
            elif any(word in sentence_lower for word in ["metro", "bus", "traffico", "spostamenti"]):
                return "Questo potrebbe cambiare gli spostamenti quotidiani. "
            elif any(word in sentence_lower for word in ["comune", "sindaco", "municipio", "decisione"]):
                return "Questa decisione amministrativa riguarda tutti i residenti. "
            elif any(word in sentence_lower for word in ["lavori", "intervento", "manutenzione"]):
                return "Questi lavori potrebbero causare disagi alla circolazione. "
            else:
                return f"Questa notizia è rilevante per chi vive a {location}. "
        
        # Pattern di rilevanza per altre città
        elif any(word in sentence_lower for word in ["metro", "bus", "traffico"]):
            return "Questo potrebbe impattare la mobilità urbana. "
        elif any(word in sentence_lower for word in ["comune", "sindaco"]):
            return "Questa decisione amministrativa riguarda i cittadini. "
        else:
            return f"Questo evento è importante per {location}. "
    
    def _clean_news_text(self, text: str) -> str:
        """Pulisce il testo delle notizie per TTS"""
        if not text:
            return ""
        
        # Rimuovi fonti tra parentesi
        text = re.sub(r'\s*-\s*[^-]*$', '', text)  # Rimuovi " - Fonte"
        text = re.sub(r'\([^)]*\)', '', text)  # Rimuovi testo tra parentesi
        text = re.sub(r'\[[^\]]*\]', '', text)  # Rimuovi testo tra quadre
        
        # Rimuovi URL
        text = re.sub(r'http[s]?://\S+', '', text)
        
        # Rimuovi date numeriche
        text = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '', text)
        text = re.sub(r'\d{1,2}\s*(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)', '', text, flags=re.IGNORECASE)
        
        # Rimuovi caratteri problematici
        text = text.replace('"', '').replace("'", "").replace(":", "").replace(";", "")
        
        # Limita lunghezza
        if len(text) > 100:
            text = text[:100].rsplit(' ', 1)[0] + "..."
        
        return text.strip()
    
    def _get_weather_emoji(self, description: str) -> str:
        """Restituisce l'emoji appropriata per il meteo"""
        desc_lower = description.lower()
        
        if any(word in desc_lower for word in ["soleggiato", "sole", "sereno", "clear"]):
            return "☀️"
        elif any(word in desc_lower for word in ["nuvoloso", "nuvole", "cloudy"]):
            return "☁️"
        elif any(word in desc_lower for word in ["pioggia", "piove", "pioggia", "rain"]):
            return "🌧️"
        elif any(word in desc_lower for word in ["neve", "nevica", "snow"]):
            return "❄️"
        elif any(word in desc_lower for word in ["temporale", "tuono", "thunder"]):
            return "⛈️"
        elif any(word in desc_lower for word in ["nebbia", "nebbioso", "fog"]):
            return "🌫️"
        elif any(word in desc_lower for word in ["vento", "ventoso", "windy"]):
            return "💨"
        else:
            return "🌤️"

class VerifiedKnowledgeEngine(BaseEngine):
    """
    VERIFIED KNOWLEDGE - Knowledge base verificato
    """
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Estrae knowledge verificato
        """
        print(f"[VERIFIED_KNOWLEDGE] Extracting verified info", flush=True)
        
        try:
            from core.verified_knowledge import verified_knowledge
            
            knowledge_type = params.get("knowledge_type", "")
            
            if knowledge_type == "historical_info":
                data = verified_knowledge.get_historical_info(message)
            else:
                data = verified_knowledge.get_general_info(message)
            
            if data.get("verified", False):
                return data.get("content", "Informazione non disponibile.")
            elif params.get("fallback_to_gpt", False):
                # Delega a GPT-full
                gpt_engine = GPTFullEngine()
                return await gpt_engine.generate(message, params, context)
            else:
                return "Informazione verificata non disponibile."
                
        except Exception as e:
            print(f"[VERIFIED_KNOWLEDGE] Error: {e}", flush=True)
            return "Non posso accedere alle informazioni verifiche."
    
    def can_handle(self, intent_type: str) -> bool:
        """Verified knowledge gestisce knowledge verificato"""
        return intent_type in ["verified_knowledge", "historical_info"]

# Registry motori
class EngineRegistry:
    """Registry centrale per tutti i motori"""
    
    def __init__(self):
        self.engines = {
            "gpt_full": GPTFullEngine(),
            "psychological": PsychologicalEngine(),  # NUOVO - con GPT_FULL
            "personalplex": PersonalplexEngine(),
            "api_tools": APIToolsEngine(),
            "verified_knowledge": VerifiedKnowledgeEngine(),
            "date_time": DateTimeEngine()  # NUOVO
        }
    
    def get_engine(self, engine_type: str) -> BaseEngine:
        """Ottiene motore per tipo"""
        return self.engines.get(engine_type, self.engines["personalplex"])
    
    async def generate_with_engine(self, engine_type: str, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta con motore specifico
        FALLBACK CORRETTI - MAI PersonalPlex per intent specialistici
        """
        engine = self.get_engine(engine_type)
        intent_type = params.get("intent_type", "")
        
        # Verifica se il motore può gestire l'intent
        if not engine.can_handle(intent_type):
            print(f"[ENGINE_REGISTRY] Engine {engine_type} cannot handle intent: {intent_type}", flush=True)
            
            # FALLBACK CORRETTI basati su intent
            if intent_type in ["weather", "news"]:
                # Fallback a API_TOOLS per intent meteo/news
                print(f"[ENGINE_REGISTRY] Fallback: {engine_type} -> api_tools", flush=True)
                engine = self.get_engine("api_tools")
            elif intent_type in ["medical_info", "psychological", "historical_info", "verified_knowledge", "date_time"]:
                # Retry con stesso motore o errore contestuale
                print(f"[ENGINE_REGISTRY] Fallback: retry same engine or contextual error", flush=True)
                return await self._handle_specialist_fallback(intent_type, message, params, context)
            else:
                # ❌ NESSUN FALLBACK A PERSONALPLEX - VIETATO
                print(f"[ENGINE_REGISTRY] No fallback available for {intent_type}", flush=True)
                return "Servizio temporaneamente non disponibile."
        
        return await engine.generate(message, params, context)
    
    async def _handle_specialist_fallback(self, intent_type: str, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Gestione fallback per motori specialistici - MAI PersonalPlex
        """
        print(f"[ENGINE_REGISTRY] Handling specialist fallback for {intent_type}", flush=True)
        
        # Risposte contestuali per ogni tipo di fallimento
        fallback_responses = {
            "weather": "In questo momento non riesco a ottenere informazioni meteo. Vuoi che riprovi?",
            "news": "Non riesco a recuperare le notizie attualmente. Posso aiutarti con altro?",
            "medical_info": "Per questioni mediche è sempre meglio consultare un professionista. Posso aiutarti in altro modo?",
            "psychological": "Sono qui per ascoltarti. In questo momento ho difficoltà a elaborare, ma sono con te.",
            "historical_info": "Non riesco a accedere alle informazioni storiche in questo momento. Vuoi che riprovi?",
            "verified_knowledge": "Non posso verificare questa informazione ora. Posso aiutarti con altro?",
            "date_time": "Non riesco a ottenere l'ora corrente. Controlla il tuo dispositivo."
        }
        
        return fallback_responses.get(intent_type, "In questo momento non posso elaborare questa richiesta. Posso aiutarti con altro?")

# Istanza globale
engine_registry = EngineRegistry()
