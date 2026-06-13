"""
MANUAL SERVICE - Genesi Core v3
Gestore dei manuali di sistema per la consultazione autonoma di Genesi.
Legge i manuali (.txt, .json) in memory/manuals/ ed estrae le parti rilevanti in base alla query.
"""

import os
import re
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

_MANUALS_DIR = "memory/manuals"
os.makedirs(_MANUALS_DIR, exist_ok=True)


class ManualService:
    """Servizio per gestire e interrogare autonomamente i manuali di sistema."""

    def __init__(self, directory: str = _MANUALS_DIR):
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)

    def list_manuals(self) -> List[str]:
        """Elenca i nomi dei file dei manuali disponibili."""
        try:
            return [f for f in os.listdir(self.directory) if f.endswith(('.txt', '.json'))]
        except Exception as e:
            logger.error("MANUAL_LIST_ERROR: %s", e)
            return []

    def search(self, query: str, limit_chars: int = 3000) -> str:
        """
        Cerca parole chiave della query all'interno dei manuali e restituisce i paragrafi rilevanti.
        """
        if not query or not query.strip():
            return ""

        # Estrai parole e pulisci
        words = re.findall(r'\w+', query.lower())
        
        # Parole vuote italiane comuni da escludere
        stop_words = {
            "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "del", "dello", "della",
            "dei", "degli", "delle", "al", "allo", "alla", "ai", "agli", "alle", "nel", "nello",
            "nella", "nei", "negli", "nelle", "col", "coi", "sul", "sulla", "sui", "sugli",
            "sulle", "di", "a", "da", "in", "con", "su", "per", "tra", "fra", "e", "o", "ma",
            "come", "che", "cosa", "chi", "dove", "quando", "perche", "perché", "questo", "questa",
            "quelli", "quelle", "ho", "ha", "abbiamo", "hanno", "sono", "è", "e'", "era", "erano"
        }
        query_keywords = [w for w in words if w not in stop_words and len(w) > 1]

        if not query_keywords:
            query_keywords = words  # fallback se ci sono solo parole vuote

        matches = []
        manuals = self.list_manuals()

        for filename in manuals:
            filepath = os.path.join(self.directory, filename)
            try:
                if filename.endswith('.txt'):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # Dividi in paragrafi basati su doppi a capo
                    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
                    for p in paragraphs:
                        p_lower = p.lower()
                        # Conta quanti keyword match ci sono (score)
                        score = sum(p_lower.count(kw) for kw in query_keywords)
                        if score > 0:
                            matches.append({
                                "source": filename,
                                "text": p,
                                "score": score
                            })
                elif filename.endswith('.json'):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    chunks = []
                    if isinstance(data, list):
                        chunks = data
                    elif isinstance(data, dict):
                        chunks = data.get("sections", data.get("chunks", []))

                    for chunk in chunks:
                        text = ""
                        title = ""
                        if isinstance(chunk, str):
                            text = chunk
                        elif isinstance(chunk, dict):
                            text = chunk.get("text", chunk.get("content", ""))
                            title = chunk.get("title", "")

                        if not text:
                            continue

                        text_lower = text.lower()
                        score = sum(text_lower.count(kw) for kw in query_keywords)
                        if score > 0:
                            display_text = f"[{title}] {text}" if title else text
                            matches.append({
                                "source": filename,
                                "text": display_text,
                                "score": score
                            })
            except Exception as e:
                logger.error("MANUAL_READ_ERROR file=%s error=%s", filename, e)

        if not matches:
            return ""

        # Ordina per score decrescente
        matches.sort(key=lambda m: m["score"], reverse=True)

        # Costruisci testo risultante entro il limite di caratteri
        result_parts = []
        current_len = 0
        grouped = {}
        
        # Raggruppa i risultati per sorgente
        for m in matches:
            grouped.setdefault(m["source"], []).append(m["text"])

        for source, texts in grouped.items():
            source_header = f"--- MANUALE: {source} ---"
            if current_len + len(source_header) + 10 > limit_chars:
                break
            result_parts.append(source_header)
            current_len += len(source_header) + 1

            for text in texts:
                formatted_text = f"• {text}"
                if current_len + len(formatted_text) + 2 > limit_chars:
                    break
                result_parts.append(formatted_text)
                current_len += len(formatted_text) + 1

        return "\n".join(result_parts)


manual_service = ManualService()
