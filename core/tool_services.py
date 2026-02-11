"""
TOOL SERVICES - Genesi Core v2
Servizi tool per weather, news, time, date
"""

from datetime import datetime
from typing import Dict, Any
from core.log import log

class ToolService:
    """
    Tool Service - Gestione servizi tool
    Weather, News, Time, Date
    """
    
    def __init__(self):
        log("TOOL_SERVICE_ACTIVE")
    
    async def get_weather(self, message: str) -> str:
        """
        Ottieni informazioni meteo
        
        Args:
            message: Messaggio utente
            
        Returns:
            Informazioni meteo
        """
        try:
            log("TOOL_WEATHER_REQUEST", message=message[:50])
            
            # Estrai città dal messaggio
            city = self._extract_city(message)
            
            # Mock weather data (in futuro implementare API reale)
            weather_info = f"Il tempo a {city or 'Roma'} è soleggiato con 22°C. Vento leggero da ovest."
            
            log("TOOL_WEATHER_RESPONSE", city=city or "Roma")
            return weather_info
            
        except Exception as e:
            log("TOOL_WEATHER_ERROR", error=str(e))
            return "Mi dispiace, non riesco a ottenere informazioni meteo."
    
    async def get_news(self, message: str) -> str:
        """
        Ottieni notizie
        
        Args:
            message: Messaggio utente
            
        Returns:
            Notizie recenti
        """
        try:
            log("TOOL_NEWS_REQUEST", message=message[:50])
            
            # Estrai argomento dal messaggio
            topic = self._extract_topic(message)
            
            # Mock news data (in futuro implementare API reale)
            news_info = f"Ultime notizie su {topic or 'tecnologia'}: Nuovi sviluppi nell'intelligenza artificiale e innovazioni sostenibili."
            
            log("TOOL_NEWS_RESPONSE", topic=topic or "tecnologia")
            return news_info
            
        except Exception as e:
            log("TOOL_NEWS_ERROR", error=str(e))
            return "Mi dispiace, non riesco a ottenere le notizie."
    
    async def get_time(self) -> str:
        """
        Ottieni ora corrente
        
        Returns:
            Ora corrente
        """
        try:
            log("TOOL_TIME_REQUEST")
            
            current_time = datetime.now().strftime("%H:%M")
            time_info = f"Sono le {current_time}."
            
            log("TOOL_TIME_RESPONSE", time=current_time)
            return time_info
            
        except Exception as e:
            log("TOOL_TIME_ERROR", error=str(e))
            return "Mi dispiace, non riesco a ottenere l'ora."
    
    async def get_date(self) -> str:
        """
        Ottieni data corrente
        
        Returns:
            Data corrente
        """
        try:
            log("TOOL_DATE_REQUEST")
            
            current_date = datetime.now().strftime("%d/%m/%Y")
            weekday = datetime.now().strftime("%A")
            
            date_info = f"Oggi è {weekday}, {current_date}."
            
            log("TOOL_DATE_RESPONSE", date=current_date, weekday=weekday)
            return date_info
            
        except Exception as e:
            log("TOOL_DATE_ERROR", error=str(e))
            return "Mi dispiace, non riesco a ottenere la data."
    
    def _extract_city(self, message: str) -> str:
        """
        Estrai nome città dal messaggio
        
        Args:
            message: Messaggio utente
            
        Returns:
            Nome città o None
        """
        cities = ["roma", "milano", "napoli", "torino", "firenze", "bologna", "genova", "palermo"]
        message_lower = message.lower()
        
        for city in cities:
            if city in message_lower:
                return city.capitalize()
        
        return None
    
    def _extract_topic(self, message: str) -> str:
        """
        Estrai argomento dal messaggio
        
        Args:
            message: Messaggio utente
            
        Returns:
            Argomento o None
        """
        topics = ["tecnologia", "sport", "politica", "economia", "cultura", "scienza"]
        message_lower = message.lower()
        
        for topic in topics:
            if topic in message_lower:
                return topic
        
        return None

# Istanza globale
tool_service = ToolService()
