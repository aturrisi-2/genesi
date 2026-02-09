"""
VERIFIED KNOWLEDGE SOURCES
Fonti verificate per medicina, storia e dati fattuali
"""

import requests
import json
import re
from typing import Dict, Optional, List
from urllib.parse import quote

class VerifiedKnowledge:
    """
    FONTI VERIFICATE PER RISPOSTE AFFIDABILI
    Wikipedia, API mediche, knowledge base locale
    """
    
    def __init__(self):
        self.wikipedia_api = "https://it.wikipedia.org/api/rest_v1/page/summary/"
        self.timeout = 10
    
    def get_medical_info(self, topic: str) -> Dict:
        """
        OTTIENE INFORMAZIONI MEDICHE VERIFICATE
        Fonte: Wikipedia sezione medica + disclaimer
        
        Args:
            topic: Argomento medico (es: "mal di testa")
            
        Returns:
            Dict con info mediche e disclaimer
        """
        try:
            # Prima prova Wikipedia italiano
            url = f"{self.wikipedia_api}{quote(topic)}"
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                
                # Verifica se è contenuto medico appropriato
                content = self._filter_medical_content(data.get("extract", ""))
                
                return {
                    "source": "wikipedia",
                    "content": content,
                    "title": data.get("title", ""),
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "disclaimer": "Non sono un medico. Per problemi di salute consulta un professionista.",
                    "verified": True
                }
            else:
                return self._medical_fallback(topic)
                
        except Exception as e:
            return self._medical_fallback(topic)
    
    def get_historical_info(self, topic: str) -> Dict:
        """
        OTTIENE INFORMAZIONI STORICHE VERIFICATE
        Fonte: Wikipedia
        
        Args:
            topic: Argomento storico (es: "Napoleone")
            
        Returns:
            Dict con info storiche
        """
        try:
            url = f"{self.wikipedia_api}{quote(topic)}"
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                
                return {
                    "source": "wikipedia",
                    "content": data.get("extract", ""),
                    "title": data.get("title", ""),
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "verified": True
                }
            else:
                return self._historical_fallback(topic)
                
        except Exception as e:
            return self._historical_fallback(topic)
    
    def _filter_medical_content(self, content: str) -> str:
        """
        FILTRA CONTENUTO MEDICO PER RIMUOVERE CONSIGLI PERICOLOSI
        
        Args:
            content: Contenuto grezzo da Wikipedia
            
        Returns:
            Contenuto filtrato e sicuro
        """
        if not content:
            return "Informazione non disponibile."
        
        # Rimuovi riferimenti a farmaci specifici
        content = re.sub(r'farmaco\w*\s+[A-Z][a-z]+', 'farmaci', content, flags=re.IGNORECASE)
        content = re.sub(r'medicina\w*\s+[A-Z][a-z]+', 'medicinali', content, flags=re.IGNORECASE)
        
        # Rimuovi dosaggi e trattamenti specifici
        content = re.sub(r'\d+\s*mg', '', content)
        content = re.sub(r'\d+\s*volte\s+al\s+giorno', '', content, flags=re.IGNORECASE)
        
        # Limita lunghezza per sicurezza
        sentences = content.split('.')[:3]  # Max 3 frasi
        filtered = '. '.join(sentences).strip()
        
        if not filtered.endswith('.'):
            filtered += '.'
        
        return filtered
    
    def _medical_fallback(self, topic: str) -> Dict:
        """
        FALLBACK SICURO PER INFORMAZIONI MEDICHE
        
        Args:
            topic: Argomento medico
            
        Returns:
            Dict con risposta sicura
        """
        fallback_responses = {
            "mal di testa": "Il mal di testa è un disturbo comune che può avere molte cause, come stress, disidratazione o tensione muscolare. Se è intenso o persistente, è importante consultare un medico.",
            "febbre": "La febbre è una risposta del corpo a infezioni o infiammazioni. Generalmente non è preoccupante se sotto i 38.5°C, ma se persiste o è molto alta consulta un medico.",
            "dolore": "Il dolore è un segnale del corpo che qualcosa non funziona correttamente. Per dolori persistenti o intensi è sempre meglio consultare un professionista medico."
        }
        
        topic_lower = topic.lower()
        for key, response in fallback_responses.items():
            if key in topic_lower:
                return {
                    "source": "fallback_medical",
                    "content": response,
                    "disclaimer": "Non sono un medico. Per problemi di salute consulta un professionista.",
                    "verified": False,
                    "safe_fallback": True
                }
        
        return {
            "source": "fallback_medical",
            "content": "Per questioni mediche è sempre meglio consultare un professionista qualificato. Posso fornire solo informazioni generali.",
            "disclaimer": "Non sono un medico. Per problemi di salute consulta un professionista.",
            "verified": False,
            "safe_fallback": True
        }
    
    def _historical_fallback(self, topic: str) -> Dict:
        """
        FALLBACK PER INFORMAZIONI STORICHE
        
        Args:
            topic: Argomento storico
            
        Returns:
            Dict con risposta di fallback
        """
        return {
            "source": "fallback_historical",
            "content": f"Non ho informazioni specifiche su {topic}. Posso aiutarti con un altro argomento storico?",
            "verified": False,
            "fallback": True
        }

# Istanza globale
verified_knowledge = VerifiedKnowledge()
