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
        Cerca nei manuali e restituisce i paragrafi rilevanti.
        Prima ricerca SEMANTICA (vettoriale sqlite-vec); se non disponibile o vuota,
        fallback alla ricerca per parole chiave.
        """
        if not query or not query.strip():
            return ""

        # 1) Ricerca semantica (vettoriale)
        try:
            from core.vector_memory import search_sync as _vsearch
            hits = _vsearch(query, top_k=6)
            if hits:
                out, total = [], 0
                for h in hits:
                    block = f"[{h['title']}]\n{h['text']}"
                    if h.get("url"):
                        block += f"\n(Fonte: {h['url']})"
                    if total + len(block) > limit_chars:
                        break
                    out.append(block)
                    total += len(block)
                if out:
                    return "\n\n".join(out)
        except Exception as e:
            logger.debug("MANUAL_VECTOR_SEARCH_FALLBACK err=%s", e)

        # 2) Fallback: ricerca per parole chiave (legacy)
        return self._search_keywords(query, limit_chars)

    def _search_keywords(self, query: str, limit_chars: int = 3000) -> str:
        """Ricerca per parole chiave (fallback se il vettoriale non è disponibile)."""
        if not query or not query.strip():
            return ""

        # Estrai parole e pulisci
        words = re.findall(r'\w+', query.lower())
        
        # Parole vuote italiane comuni da escludere
        stop_words = {
            # Articoli e preposizioni
            "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "del", "dello", "della",
            "dei", "degli", "delle", "al", "allo", "alla", "ai", "agli", "alle", "nel", "nello",
            "nella", "nei", "negli", "nelle", "col", "coi", "sul", "sulla", "sui", "sugli",
            "sulle", "di", "a", "da", "in", "con", "su", "per", "tra", "fra", "e", "o", "ma",
            "che", "cosa", "chi", "dove", "quando", "perche", "perché", "questo", "questa",
            "quelli", "quelle", "questi", "queste", "quello", "quella", "ed",
            
            # Verbi ausiliari e comuni
            "ho", "ha", "abbiamo", "hanno", "sono", "è", "e'", "era", "erano", "sia", "siano",
            "essere", "avere", "fa", "fanno", "fatto", "sta", "stanno", "sto", "stai", "stata",
            "stato", "state", "stati", "può", "possono", "potrebbe", "deve", "devono", "dovrebbe",
            
            # Pronomi e particelle
            "si", "se", "ci", "vi", "mi", "ti", "lo", "la", "li", "le", "ne", "gli", "suo",
            "sua", "suoi", "sue", "loro", "mio", "mia", "miei", "mie", "tuo", "tua", "tuoi",
            "tue", "nostro", "nostra", "nostri", "nostre", "vostro", "vostra", "vostri", "vostre",
            
            # Avverbi e quantificatori comuni
            "non", "più", "meno", "molto", "poco", "troppo", "tutto", "tutti", "tutta", "tutte",
            "ogni", "qualche", "alcuni", "alcune", "altro", "altra", "altri", "altre", "solo",
            "sempre", "mai", "già", "ancora", "anche", "come", "invece", "mentre", "qualora",
            "bene", "meglio", "male", "peggio", "sotto", "sopra", "dentro", "fuori", "prima",
            "dopo", "contro", "senza", "circa", "sui", "sua", "suo"
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

        limit_reached = False
        for source, texts in grouped.items():
            if limit_reached:
                break
            
            source_parts = []
            source_header = f"--- MANUALE: {source} ---"
            
            # Stima dello spazio rimanente per l'intestazione
            rem_space = limit_chars - current_len
            if rem_space < 50:
                break
                
            for text in texts:
                formatted_text = f"• {text}"
                header_cost = len(source_header) + 1 if not source_parts else 0
                needed = header_cost + len(formatted_text) + 2
                
                if current_len + needed <= limit_chars:
                    # Ci sta interamente
                    source_parts.append(formatted_text)
                    current_len += len(formatted_text) + 1
                else:
                    # Non ci sta interamente, proviamo a troncare se c'è spazio sufficiente (almeno 100 caratteri)
                    avail = limit_chars - current_len - header_cost - 15
                    if avail >= 100:
                        truncated = formatted_text[:avail] + "... [TRONCATO]"
                        source_parts.append(truncated)
                        current_len += len(truncated) + 1
                    limit_reached = True
                    break
                
            if source_parts:
                result_parts.append(source_header)
                result_parts.extend(source_parts)
                current_len += len(source_header) + 1

        return "\n".join(result_parts)


manual_service = ManualService()
