
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from core.log import log

class CalendarHistory:
    """
    Gestisce la persistenza storica degli impegni sincronizzati da varie fonti.
    """
    def __init__(self, storage_path="data/calendar_history.json"):
        self.path = Path(storage_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.history = self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: return {"items": {}, "last_full_sync": None}
        return {"items": {}, "last_full_sync": None}

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=2, ensure_ascii=False)

    def add_item(self, guid, data):
        """Aggiunge o aggiorna un elemento nello storico."""
        if not guid: return
        self.history["items"][guid] = data
        self.history["last_update"] = datetime.now().isoformat()

    def exists(self, guid):
        return guid in self.history["items"]

    def get_all(self):
        return list(self.history["items"].values())

calendar_history = CalendarHistory()
