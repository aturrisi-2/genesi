# core/psychological_memory.py
# Memoria psicologica dedicata, isolata per-utente.
# NON condivisa con la memoria episodica standard.
# NON accessibile fuori dal ramo psicologico.

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from core.log import log as _log

PSY_MEMORY_DIR = Path("data/psychological/memory")
PSY_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# Limite massimo di entry per utente (evita crescita infinita)
MAX_ENTRIES = 100


def store(user_id: str, entry_type: str, content: str, 
          severity: str = "mild", tags: Optional[List[str]] = None) -> dict:
    """
    Salva un'entry nella memoria psicologica dell'utente.
    
    entry_type: "theme" | "boundary" | "vulnerability" | "progress" | "crisis"
    severity: "mild" | "moderate" | "severe" | "critical"
    tags: etichette libere per categorizzazione
    """
    memory = _load(user_id)
    
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": entry_type,
        "content": content,
        "severity": severity,
        "tags": tags or [],
    }
    
    memory["entries"].append(entry)
    
    # Aggiorna temi ricorrenti
    _update_recurring_themes(memory, content, entry_type)
    
    # Trim se supera il limite
    if len(memory["entries"]) > MAX_ENTRIES:
        memory["entries"] = memory["entries"][-MAX_ENTRIES:]
    
    _save(user_id, memory)
    _log("MEMORY_SAVE", type="psychological", user_id=user_id,
         entry_type=entry_type, severity=severity)
    return entry


def get_context(user_id: str, limit: int = 5) -> dict:
    """
    Recupera il contesto psicologico per il prompt.
    Restituisce solo informazioni rilevanti, non tutto lo storico.
    """
    memory = _load(user_id)
    
    recent = memory["entries"][-limit:] if memory["entries"] else []
    themes = memory.get("recurring_themes", {})
    boundaries = memory.get("boundaries", [])
    
    # Filtra solo contenuti utili per il prompt
    context_entries = []
    for entry in recent:
        context_entries.append({
            "type": entry["type"],
            "content": entry["content"],
            "severity": entry["severity"],
        })
    
    return {
        "has_history": len(memory["entries"]) > 0,
        "recent_entries": context_entries,
        "recurring_themes": dict(list(themes.items())[:5]),
        "boundaries": boundaries[:5],
        "total_interactions": len(memory["entries"]),
    }


def add_boundary(user_id: str, boundary: str):
    """Aggiunge un confine da rispettare per questo utente."""
    memory = _load(user_id)
    if boundary not in memory.get("boundaries", []):
        memory.setdefault("boundaries", []).append(boundary)
        _save(user_id, memory)
        _log("MEMORY_SAVE", type="psychological_boundary", user_id=user_id)


def get_recurring_themes(user_id: str) -> dict:
    """Restituisce i temi ricorrenti per l'utente."""
    memory = _load(user_id)
    return memory.get("recurring_themes", {})


def _update_recurring_themes(memory: dict, content: str, entry_type: str):
    """Aggiorna conteggio temi ricorrenti basato su keyword."""
    themes = memory.setdefault("recurring_themes", {})
    content_lower = content.lower()
    
    theme_keywords = {
        "solitudine": ["solo", "sola", "solitudine", "isolato", "isolata"],
        "ansia": ["ansia", "ansioso", "ansiosa", "panico", "agitato", "agitata"],
        "tristezza": ["triste", "tristezza", "piango", "piangere", "depresso", "depressa"],
        "rabbia": ["arrabbiato", "arrabbiata", "furioso", "furiosa", "incazzato"],
        "autostima": ["non valgo", "inutile", "inadeguato", "inadeguata", "non sono abbastanza"],
        "relazioni": ["lasciato", "lasciata", "tradito", "tradita", "separazione"],
        "lutto": ["morto", "morta", "lutto", "perso", "mancanza"],
        "lavoro": ["lavoro", "burnout", "licenziato", "licenziata", "capo", "colleghi"],
        "famiglia": ["famiglia", "genitori", "padre", "madre", "figlio", "figlia"],
        "sonno": ["dormire", "insonnia", "incubi", "non dormo"],
    }
    
    for theme, keywords in theme_keywords.items():
        if any(kw in content_lower for kw in keywords):
            themes[theme] = themes.get(theme, 0) + 1


def _load(user_id: str) -> dict:
    path = PSY_MEMORY_DIR / f"{user_id}.json"
    if not path.exists():
        return {"entries": [], "recurring_themes": {}, "boundaries": []}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return {"entries": [], "recurring_themes": {}, "boundaries": []}


def _save(user_id: str, memory: dict):
    path = PSY_MEMORY_DIR / f"{user_id}.json"
    with open(path, "w") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)
