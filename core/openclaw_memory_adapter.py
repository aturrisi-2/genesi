import logging
import json
import re
import asyncio
from datetime import datetime
from core.llm_service import llm_service
from core.storage import storage

logger = logging.getLogger(__name__)

class OpenClawMemoryAdapter:
    """
    Adapter per intercettare passivamente l'output del braccio meccanico (OpenClaw)
    ed estrarre deduzioni psicologiche, preferenze o attori sociali per
    arricchire la Memoria Semantica (Profilo) di Genesi, senza gravare sull'utente.
    """
    async def extract_and_store(self, user_id: str, raw_openclaw_output: str, task_prompt: str):
        if not raw_openclaw_output or len(raw_openclaw_output) < 20:
            return
            
        system_prompt = '''Sei un analista psicologico e comportamentale. Il tuo compito è leggere i log di navigazione di un assistente web (OpenClaw) e il comando originale dell'utente, per estrarre passivamente informazioni sulla sua identità.
ESTRAI:
1. Preferenze e abitudini di acquisto o vita (es. preferisce hotel 4 stelle, cerca voli economici)
2. Attori sociali (ha prenotato per due, per la moglie, ha comprato un regalo per X)
3. Interessi (sta leggendo notizie di politica, sport)

Rispondi SOLO con un JSON valido in questo formato:
{
  "preferences": ["preferisce hotel con colazione inclusa", "compra spesso su amazon prime"],
  "social_actors": [{"name": "Marta", "role": "moglie"}],
  "interests": ["politica estera", "tecnologia"]
}
Se non c'è nulla di deducibile o rilevante, restituisci array vuoti.'''

        user_content = f"Comando Utente: {task_prompt}\n\nRisultato Navigazione:\n{raw_openclaw_output[:3000]}"
        
        try:
            # Chiamata LLM leggera in background
            llm_response = await llm_service._call_with_protection(
                "gpt-4o-mini", system_prompt, user_content, user_id=user_id, route="classification"
            )
            
            if not llm_response:
                return
                
            json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                return
                
            # Aggiornamento Profilo Semantico
            profile = await storage.load(f"profile:{user_id}", default={})
            updated = False
            
            # Preferenze
            prefs = data.get("preferences", [])
            if prefs:
                existing_prefs = profile.get("preferences", [])
                for p in prefs:
                    if p not in existing_prefs:
                        existing_prefs.append(p)
                profile["preferences"] = existing_prefs
                updated = True
                
            # Interessi
            interests = data.get("interests", [])
            if interests:
                existing_int = profile.get("interests", [])
                for i in interests:
                    if i not in existing_int:
                        existing_int.append(i)
                profile["interests"] = existing_int
                updated = True
                
            # Social actors -> Entities
            actors = data.get("social_actors", [])
            if actors:
                entities = profile.get("entities", {})
                for actor in actors:
                    role = actor.get("role", "unknown")
                    name = actor.get("name", "unknown")
                    # Se non è unknown e non esiste, o menziona
                    if role != "unknown" and name != "unknown":
                        if role not in entities:
                            entities[role] = {"name": name, "role": role, "mentions": 1}
                            updated = True
                        else:
                            entities[role]["mentions"] = entities[role].get("mentions", 0) + 1
                            updated = True
                profile["entities"] = entities
                
            if updated:
                profile["updated_at"] = datetime.now().isoformat()
                await storage.save(f"profile:{user_id}", profile)
                logger.info("OPENCLAW_MEMORY_INJECTED user=%s updates=%s", user_id, str(data))
                
        except Exception as e:
            logger.error("OPENCLAW_MEMORY_ERROR: %s", str(e))

openclaw_adapter = OpenClawMemoryAdapter()
