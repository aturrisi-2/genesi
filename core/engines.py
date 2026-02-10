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
        from core.llm import generate_response as llm_generate
        self.llm_generate = llm_generate
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta con GPT-full - testo pulito, niente teatralità
        """
        print(f"[GPT_FULL] Generating factual response", flush=True)
        
        try:
            # Prompt per GPT-full - solo fatti
            prompt = self._build_factual_prompt(message, params.get("intent_type", ""))
            
            response = await self.llm_generate(
                prompt=prompt,
                temperature=params.get("temperature", 0.3),
                max_tokens=params.get("max_tokens", 150)
            )
            
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

class PersonalplexEngine(BaseEngine):
    """
    PERSONALPLEX - SOLO per chat libera e relazione
    REGOLE RIGIDE: solo italiano, niente emoji, max 2 frasi
    """
    
    def __init__(self):
        from core.local_llm import LocalLLM
        self.local_llm = LocalLLM()
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta con PersonalPlex - VINCOLI RIGIDI
        """
        print(f"[PERSONALPLEX] Generating chat response", flush=True)
        
        try:
            # Prompt rigoroso per PersonalPlex
            prompt = f"""Rispondi in modo naturale e semplice a: {message}

REGOLE ASSOLUTE:
- SOLO italiano
- NIENTE emoji
- NIENTE simboli (*smile*, *wink*, ecc.)
- MASSIMO 2 frasi
- Tono umano e sobrio
- SOLO conversazione informale"""
            
            response = self.local_llm.generate(
                prompt=prompt,
                max_tokens=60,  # Ridotto per risposte brevi
                temperature=0.6
            )
            
            # Post-processing per garantire conformità
            response = self._enforce_personalplex_rules(response)
            
            return response.strip()
            
        except Exception as e:
            print(f"[PERSONALPLEX] Error: {e}", flush=True)
            return "Posso aiutarti in altro modo?"
    
    def _enforce_personalplex_rules(self, response: str) -> str:
        """Applica regole rigide alla risposta PersonalPlex"""
        if not response:
            return response
        
        # Rimuovi emoji
        import re
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "]+", flags=re.UNICODE
        )
        response = emoji_pattern.sub('', response)
        
        # Rimuovi azioni teatrali
        theatrical_pattern = re.compile(r'\*[^*]*\*', re.IGNORECASE)
        response = theatrical_pattern.sub('', response)
        
        # Limita a 2 frasi
        sentences = response.split('.')
        if len(sentences) > 2:
            response = '. '.join(sentences[:2]) + '.'
        
        # Rimuovi spazi extra
        response = ' '.join(response.split())
        
        return response
    
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
        """Estrae città dal messaggio meteo"""
        from core.tools import extract_city
        location = extract_city(message)
        print(f"[DEBUG_API_TOOLS] extract_city result: {location}", flush=True)
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
                
                # Costruisci risposta TTS friendly
                response = f"A {city} ci sono {temp} gradi con {description}."
                if humidity > 0:
                    response += f" Umidità {humidity} per cento."
                if wind_speed > 0:
                    if wind_speed <= 5:
                        wind_desc = "debole"
                    elif wind_speed <= 15:
                        wind_desc = "moderato"
                    elif wind_speed <= 25:
                        wind_desc = "forte"
                    else:
                        wind_desc = "molto forte"
                    response += f" Vento {wind_desc}."
                
                print(f"[DEBUG_WEATHER] response built (TTS friendly): {response}", flush=True)
                return response
            else:
                print(f"[DEBUG_WEATHER] no current data in response", flush=True)
                return f"Dati meteo non disponibili per {location}."
                
        except Exception as e:
            print(f"[DEBUG_WEATHER] Exception in _get_weather: {e}", flush=True)
            return f"Errore nel recupero dati meteo per {location}."
    
    async def _get_news(self, message: str = "") -> str:
        """Ottiene notizie reali da API con filtro per località"""
        print(f"[DEBUG_NEWS] _get_news called", flush=True)
        
        try:
            from core.tools import fetch_news
            print(f"[DEBUG_NEWS] calling fetch_news API", flush=True)
            
            news_data = await fetch_news(message)
            print(f"[DEBUG_NEWS] API response received", flush=True)
            
            if "error" in news_data:
                print(f"[DEBUG_NEWS] API error: {news_data['error']}", flush=True)
                return "Al momento non risultano notizie disponibili."
            
            # Estrai articoli
            articles = news_data.get("articles", [])
            print(f"[DEBUG_NEWS] total_articles={len(articles)}", flush=True)
            
            if not articles:
                print(f"[DEBUG_NEWS] no articles found", flush=True)
                return "Al momento non risultano notizie rilevanti."
            
            # Estrai località dal messaggio
            location = self._extract_location_from_message(message)
            print(f"[DEBUG_NEWS] location_filter={location}", flush=True)
            
            # Applica filtro per località se specificata
            if location and location.lower() != "italia":
                filtered_articles = self._filter_news_by_location(articles, location)
                print(f"[DEBUG_NEWS] filtered_articles={len(filtered_articles)}", flush=True)
                
                # Se dopo il filtro non ci sono articoli, usa fallback
                if not filtered_articles:
                    print(f"[DEBUG_NEWS] no articles after location filter", flush=True)
                    return f"Al momento non ci sono notizie rilevanti su {location}."
                
                articles = filtered_articles
            else:
                print(f"[DEBUG_NEWS] using all articles (no location filter)", flush=True)
            
            # Costruisci risposta TTS friendly con max 2 articoli
            response_parts = []
            
            # Prendi solo i primi 2 articoli
            for i, article in enumerate(articles[:2]):
                title = article.get("title", "").strip()
                description = article.get("description", "").strip()
                
                # Rimuovi fonti e date
                title = self._clean_news_text(title)
                description = self._clean_news_text(description)
                
                if title and len(title) > 10:
                    if i == 0:
                        response_parts.append(f"Ultime notizie{f' da {location}' if location else ''}. {title}.")
                    else:
                        response_parts.append(title)
                
                if description and len(description) > 20 and i < 2:
                    # Limita a una frase breve
                    sentences = description.split('.')
                    if sentences:
                        first_sentence = sentences[0].strip()
                        if len(first_sentence) > 15:
                            response_parts.append(first_sentence + ".")
            
            if response_parts:
                final_response = " ".join(response_parts[:3])  # Max 3 frasi
                print(f"[DEBUG_NEWS] response built (TTS friendly): {final_response}", flush=True)
                return final_response
            else:
                print(f"[DEBUG_NEWS] no valid content found", flush=True)
                return "Al momento non risultano notizie rilevanti."
                
        except Exception as e:
            print(f"[DEBUG_NEWS] Exception in _get_news: {e}", flush=True)
            return "Non riesco a ottenere notizie in questo momento."
    
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
        """Filtra articoli per località usando parole chiave"""
        location_lower = location.lower()
        
        # Mappa località → parole chiave
        location_keywords = {
            "roma": ["roma", "romano", "romana", "capitale", "lazio"],
            "milano": ["milano", "milanese", "lombardia", "lombardo"],
            "napoli": ["napoli", "napoletano", "campania"],
            "torino": ["torino", "torinese", "piemonte", "piemontese"],
            "bologna": ["bologna", "bolognese", "emilia", "romagna"],
            "firenze": ["firenze", "fiorentino", "toscana", "toscano"],
            "genova": ["genova", "genovese", "liguria", "ligure"],
            "palermo": ["palermo", "palermitano", "sicilia", "siciliano"],
        }
        
        # Ottieni parole chiave per la località
        keywords = location_keywords.get(location_lower, [location_lower])
        
        filtered_articles = []
        for article in articles:
            title = article.get("title", "").lower()
            description = article.get("description", "").lower()
            
            # Controlla se contiene parole chiave della località
            if any(keyword in title or keyword in description for keyword in keywords):
                filtered_articles.append(article)
        
        return filtered_articles
    
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

class PsychologicalEngine(BaseEngine):
    """
    PSYCHOLOGICAL - Solo per supporto emotivo
    """
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta di supporto emotivo
        """
        print(f"[PSYCHOLOGICAL] Generating supportive response", flush=True)
        
        try:
            from core.psychological_responder import generate_psychological_response
            
            response = await generate_psychological_response(
                user_message=message,
                detection=context.get("psy_detection", {}) if context else {},
                psy_context=context.get("psy_context", {}) if context else {},
                user_name=context.get("user_name") if context else None
            )
            
            return response
            
        except Exception as e:
            print(f"[PSYCHOLOGICAL] Error: {e}", flush=True)
            return "Sono qui per te. Non sei solo."
    
    def can_handle(self, intent_type: str) -> bool:
        """Psychological gestisce supporto emotivo"""
        return intent_type == "emotional_support"

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
            "personalplex": PersonalplexEngine(),
            "api_tools": APIToolsEngine(),
            "psychological": PsychologicalEngine(),
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
                # Solo per chat_free o altri, usa PersonalPlex
                print(f"[ENGINE_REGISTRY] Fallback: {intent_type} -> personalplex", flush=True)
                engine = self.get_engine("personalplex")
        
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
