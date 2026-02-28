"""
FALLBACK ENGINE - Genesi Internal Monitoring
Raccoglie errori, fallback e risposte hard-coded per miglioramenti mirati.
- Salva eventi in modo strutturato
- Suggerisce soluzioni tramite LLM (opzionale/async)
- Raggruppa eventi simili
"""

import json
import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import hashlib

from core.log import log
from core.storage import storage

logger = logging.getLogger(__name__)

# Percorso file persistenza
FALLBACK_LOG_PATH = "memory/admin/fallbacks.json"

class FallbackEngine:
    """
    Gestore dei fallback e delle mancate risposte.
    """
    
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self._load_local()
        # Assicura directory
        os.makedirs(os.path.dirname(FALLBACK_LOG_PATH), exist_ok=True)

    def _load_local(self):
        """Carica log esistenti"""
        if os.path.exists(FALLBACK_LOG_PATH):
            try:
                with open(FALLBACK_LOG_PATH, 'r', encoding='utf-8') as f:
                    self.events = json.load(f)
            except Exception as e:
                logger.error("FALLBACK_LOAD_ERROR: %s", e)
                self.events = []

    def _save_local(self):
        """Salva log su disco"""
        try:
            with open(FALLBACK_LOG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.events, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("FALLBACK_SAVE_ERROR: %s", e)

    def _generate_group_key(self, message: str) -> str:
        """Genera una chiave di raggruppamento semplificata"""
        # Normalizzazione minima: lowercase e rimozione spazi extra
        clean = message.lower().strip()
        # Prendi i primi 40 caratteri o usa un hash per raggruppare messaggi molto simili
        return hashlib.md5(clean.encode()).hexdigest()[:12]

    async def log_event(
        self, 
        user_id: str, 
        message: str, 
        fallback_type: str, 
        response_given: str, 
        reason: Optional[str] = None
    ):
        """
        Registra un evento di fallback.
        
        Args:
            user_id: ID utente coinvolto
            message: Messaggio originale dell'utente
            fallback_type: Tipo di errore (es: 'tool_error', 'unsupported_intent', 'api_timeout')
            response_given: La risposta hard-coded data all'utente
            reason: Dettaglio dell'errore tecnico (opzionale)
        """
        timestamp = datetime.now().isoformat()
        group_key = self._generate_group_key(message)
        
        event = {
            "id": f"fb_{int(datetime.now().timestamp() * 1000)}",
            "timestamp": timestamp,
            "user_id": user_id,
            "user_message": message,
            "response_given": response_given,
            "fallback_type": fallback_type,
            "reason": reason or "No details",
            "group_key": group_key,
            "status": "pending", # 'pending', 'resolved', 'ignored'
            "possible_solution": "Analisi in corso..."
        }
        
        self.events.append(event)
        self._save_local()
        
        log("FALLBACK_LOGGED", type=fallback_type, user_id=user_id)
        
        # Avvia suggerimento soluzione in background (non bloccante)
        asyncio.create_task(self._suggest_solution(event["id"], message, fallback_type, reason))

    async def _suggest_solution(self, event_id: str, message: str, f_type: str, reason: str):
        """Usa una chiamata minima a LLM per suggerire come risolvere il problema."""
        try:
            from core.llm_service import llm_service
            
            prompt = f"""Analizza questo errore del sistema AI e suggerisci una soluzione tecnica o una nuova 'skill' da implementare.
Messaggio Utente: "{message}"
Tipo Errore: {f_type}
Dettaglio Tecnico: {reason}

Rispondi con una singola frase pratica e concisa (max 20 parole) che spieghi COSA aggiungere o sistemare nel codice."""

            # Nota: use low cost model for monitoring tasks
            suggestion = await llm_service._call_with_protection(
                "gpt-4o-mini", 
                prompt, 
                "system-fallback-analysis",
                user_id="admin-monitoring",
                route="admin"
            )
            
            if suggestion:
                # Aggiorna evento in memoria e salva
                for ev in self.events:
                    if ev["id"] == event_id:
                        ev["possible_solution"] = suggestion.strip()
                        break
                self._save_local()
                
        except Exception as e:
            logger.error("SOL_SUGGEST_ERROR for %s: %s", event_id, e)

    def get_summary(self) -> List[Dict[str, Any]]:
        """Ritorna una vista raggruppata per eventi simili"""
        groups = {}
        for ev in self.events:
            gk = ev["group_key"]
            if gk not in groups:
                groups[gk] = {
                    "count": 0,
                    "last_timestamp": ev["timestamp"],
                    "examples": [],
                    "possible_solution": ev["possible_solution"],
                    "type": ev["fallback_type"]
                }
            groups[gk]["count"] += 1
            groups[gk]["last_timestamp"] = max(groups[gk]["last_timestamp"], ev["timestamp"])
            if len(groups[gk]["examples"]) < 3:
                groups[gk]["examples"].append(ev["user_message"])
                
        return sorted(list(groups.values()), key=lambda x: x["count"], reverse=True)

    def get_all_raw(self) -> List[Dict[str, Any]]:
        """Tutti gli eventi per esportazione"""
        return self.events

    def clear_logs(self):
        """Pulisce i log"""
        self.events = []
        self._save_local()

# Singleton globale
fallback_engine = FallbackEngine()
