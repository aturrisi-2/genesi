"""
PERSONAL FACTS SERVICE — Genesi Memory System

Estrae e persiste fatti personali appresi dalla conversazione:
- Dove sono stati i familiari ("Zoe è stata a Cork")
- Preferenze specifiche ("piloti F1 preferiti: Leclerc e Hamilton")
- Abitudini e routine ("di solito cena alle 20:00", "tifo per la Ferrari")
- Fatti recenti sulla famiglia non catturati dal profilo strutturato

Complementare a:
- episode_memory: eventi temporali con data e follow-up
- global_memory_service: pattern comportamentali astratti
- profile: dati strutturati (nome, città, coniuge, figli, animali)

Fail-silent: errori non interrompono il flusso chat.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict

from core.storage import storage
from core.log import log as _structured_log

logger = logging.getLogger("genesi")

_EXTRACTION_PROMPT = """\
Sei un assistente che estrae fatti personali appresi durante la conversazione.

ESTRAI SOLO fatti duraturi che l'utente ha rivelato su se stesso o la sua famiglia:
- Dove sono stati o stanno i familiari ("mia figlia è stata a Cork in Irlanda")
- Preferenze specifiche non ancora nel profilo ("i miei piloti F1 preferiti sono Leclerc e Hamilton", "tifo per la Ferrari")
- Abitudini e routine ("di solito ceno alle 20:00", "mi sveglio alle 7")
- Hobby e passioni specifiche ("colleziono vinili", "gioco a padel il sabato")
- Fatti sulla famiglia o amici ("mio figlio studia medicina", "mia moglie lavora in ospedale")
- Argomenti o temi di cui abbiamo parlato ("Abbiamo parlato di Formula 1", "Mi ha raccontato del suo lavoro come medico")

NON ESTRARRE:
- Dati strutturati già nel profilo: nome, città di residenza, nome del coniuge, nomi dei figli, animali domestici
- Appuntamenti o eventi temporali (quelli vanno agli episodi)
- Domande generiche su meteo, notizie, calcoli, orari pubblici
- Frasi di saluto o conversazione generica

Per ogni fatto estratto:
- "text": il fatto in terza persona ("L'utente cena di solito alle 20:00" / "Oggi abbiamo parlato di Formula 1")
- "category": una di: ["famiglia", "interessi", "abitudini", "luoghi", "conversazione", "altro"]
- "key": stringa breve univoca snake_case (es. "cena_ore_20", "f1_piloti_preferiti", "zoe_cork_irlanda")

Rispondi SOLO con JSON valido:
{{"facts": [{{"text":"...","category":"...","key":"..."}}]}}
Se nessun fatto significativo: {{"facts": []}}
"""


class PersonalFactsService:
    """
    Estrae e persiste fatti personali dalla conversazione.
    Usare extract_and_save() dal background task dopo ogni risposta.
    """

    MAX_FACTS = 100

    async def extract_and_save(self, user_message: str, assistant_response: str, user_id: str) -> None:
        """
        Estrae fatti da user_message + assistant_response e li salva.
        Fail-silent — chiamare da asyncio background task.
        """
        try:
            combined = f"UTENTE: {user_message}\nGENESI: {assistant_response}"
            new_facts = await self._extract(combined, user_id)
            if new_facts:
                await self._save_facts(user_id, new_facts)
        except Exception as e:
            logger.debug("PERSONAL_FACTS_EXTRACT_ERROR err=%s", e)

    async def _extract(self, text: str, user_id: str) -> List[Dict]:
        """Chiama LLM per estrarre fatti personali + Fallback Regex."""
        # Regex baseline first (zero cost, 100% reliability)
        facts = self._extract_regex(text)
        
        try:
            from core.llm_service import llm_service

            raw = await llm_service._call_model(
                "openai/gpt-4o-mini",
                _EXTRACTION_PROMPT,
                text,
                user_id=user_id,
                route="memory"
            )
            if raw:
                clean = raw.strip()
                if clean.startswith("```"):
                    clean = clean.split("```")[1]
                    if clean.startswith("json"):
                        clean = clean[4:]
                clean = clean.strip()

                parsed = json.loads(clean)
                raw_facts = parsed.get("facts", [])
                if isinstance(raw_facts, list):
                    for f in raw_facts:
                        if not isinstance(f, dict) or not f.get("text"):
                            continue
                        # Avoid duplicates from regex
                        is_duplicate = any(f.get("key") == rf.get("key") for rf in facts)
                        if not is_duplicate:
                            facts.append({
                                "id": str(uuid.uuid4())[:8],
                                "text": str(f["text"]).strip(),
                                "category": str(f.get("category", "altro")),
                                "key": str(f.get("key", str(uuid.uuid4())[:8])).lower().replace(" ", "_"),
                                "saved_at": datetime.utcnow().isoformat(),
                            })
        except Exception as e:
            logger.debug("PERSONAL_FACTS_LLM_ERROR err=%s", e)
            
        return facts

    def _extract_regex(self, text: str) -> List[Dict]:
        """Estrae fatti semplici via regex (fail-safe per quota LLM)."""
        import re
        results = []
        
        # 1. Dove sono/vivono i familiari ("mia figlia è a Cork")
        family_loc = re.search(r"(mia figlia|mio figlio|mio marito|mia moglie|mio padre|mia madre) (?:è|si trova|abita|vive) a ([A-Z][a-zÀ-ÿ]+(?: [A-Z][a-zÀ-ÿ]+)*)", text, re.IGNORECASE)
        if family_loc:
            role = family_loc.group(1).lower().strip()
            loc = family_loc.group(2).strip().title()
            results.append({
                "id": str(uuid.uuid4())[:8],
                "text": f"{role.capitalize()} è a {loc}.",
                "category": "famiglia",
                "key": f"{role.replace(' ', '_')}_a_{loc.lower().replace(' ', '_')}",
                "saved_at": datetime.utcnow().isoformat(),
            })

        # 2. Orario cena/abitudini ("cena alle 20")
        habit_loc = re.search(r"(?:di solito|solitamente|sempre)? (?:ceno|mangio) (?:alle|verso le) (\d{1,2}(?::\d{2})?)", text, re.IGNORECASE)
        if habit_loc:
            time = habit_loc.group(1)
            results.append({
                "id": str(uuid.uuid4())[:8],
                "text": f"L'utente cena di solito alle {time}.",
                "category": "abitudini",
                "key": f"cena_ore_{time.replace(':', '_')}",
                "saved_at": datetime.utcnow().isoformat(),
            })

        return results

    async def _save_facts(self, user_id: str, new_facts: List[Dict]) -> None:
        """
        Salva i fatti aggiornando quelli esistenti.
        Priorità: 1) match esatto per key, 2) match semantico (stessa entità+attributo),
        3) nuovo fatto.
        """
        existing_data = await storage.load(f"personal_facts:{user_id}", default={"facts": []})
        existing_facts = existing_data.get("facts", [])

        # Indice key → posizione per aggiornamento rapido
        fact_index = {f["key"]: i for i, f in enumerate(existing_facts)}

        for new_f in new_facts:
            key = new_f["key"]
            if key in fact_index:
                # Aggiornamento diretto per key identica
                existing_facts[fact_index[key]]["text"] = new_f["text"]
                existing_facts[fact_index[key]]["saved_at"] = new_f["saved_at"]
                logger.info("PERSONAL_FACT_UPDATED key=%s user=%s", key, user_id)
            else:
                # Cerca conflitto semantico (stessa entità+attributo, valore diverso)
                conflict_idx = self._find_semantic_conflict(new_f, existing_facts)
                if conflict_idx >= 0:
                    old_key = existing_facts[conflict_idx]["key"]
                    existing_facts[conflict_idx] = new_f
                    # Aggiorna indice
                    fact_index = {f["key"]: i for i, f in enumerate(existing_facts)}
                    logger.info("PERSONAL_FACT_REPLACED old_key=%s new_key=%s user=%s", old_key, key, user_id)
                else:
                    existing_facts.append(new_f)
                    fact_index[key] = len(existing_facts) - 1
                    logger.info("PERSONAL_FACT_SAVED key=%s user=%s text=%s", key, user_id, new_f["text"][:60])
                    _structured_log("PERSONAL_FACTS", key=key, user_id=user_id)

        # Limite massimo FIFO
        if len(existing_facts) > self.MAX_FACTS:
            existing_facts = existing_facts[-self.MAX_FACTS:]

        await storage.save(f"personal_facts:{user_id}", {
            "facts": existing_facts,
            "updated_at": datetime.utcnow().isoformat()
        })

    @staticmethod
    def _find_semantic_conflict(new_fact: Dict, existing_facts: List[Dict]) -> int:
        """
        Cerca un fatto esistente che descrive la stessa entità+attributo del nuovo fatto.
        Heuristica: ≥2 parole significative in comune + stessa categoria → stesso concetto.
        Restituisce l'indice del conflitto o -1 se nessuno trovato.
        """
        _STOP_WORDS = {
            "l'utente", "utente", "la", "il", "di", "a", "e", "è", "ha", "che",
            "si", "per", "con", "non", "un", "una", "lo", "le", "i", "in",
            "gli", "del", "della", "dei", "delle", "dal", "dalla", "al", "alla",
            "suo", "sua", "suoi", "sue", "anche", "già", "sempre", "mai", "più"
        }

        def sig_words(text: str) -> set:
            return {
                w.lower().strip(".,!?'\"") for w in text.split()
                if len(w) > 3 and w.lower().strip(".,!?'\"") not in _STOP_WORDS
            }

        new_words = sig_words(new_fact["text"])
        new_cat = new_fact.get("category", "")

        for idx, existing in enumerate(existing_facts):
            if existing.get("category") != new_cat:
                continue
            ex_words = sig_words(existing["text"])
            if not new_words or not ex_words:
                continue
            overlap = new_words & ex_words
            # Conflitto: ≥2 parole significative in comune E overlap > 30% del minore dei due insiemi
            if len(overlap) >= 2 and len(overlap) / max(min(len(new_words), len(ex_words)), 1) > 0.3:
                return idx

        return -1

    async def remove_profession_facts(self, user_id: str) -> None:
        """
        Rimuove i fatti personali relativi alla professione/lavoro dell'utente.
        Chiamare quando _handle_memory_correction aggiorna il campo 'profession'.
        """
        _PROFESSION_KEYWORDS = {
            "lavora", "lavoro", "professione", "manager", "direttore", "ingegnere",
            "medico", "dottore", "chirurgo", "cardiologo", "avvocato", "architetto",
            "infermiere", "psicologo", "geometra", "ragioniere", "imprenditore",
            "insegnante", "professore", "sviluppatore", "programmatore", "operaio",
            "construction", "neurochirurg", "cardio",
        }
        try:
            data = await storage.load(f"personal_facts:{user_id}", default={"facts": []})
            existing = data.get("facts", [])
            cleaned = []
            removed = []
            for f in existing:
                text_lower = f.get("text", "").lower()
                key_lower = f.get("key", "").lower()
                combined = text_lower + " " + key_lower
                if any(kw in combined for kw in _PROFESSION_KEYWORDS):
                    removed.append(f.get("key"))
                else:
                    cleaned.append(f)
            if removed:
                data["facts"] = cleaned
                data["updated_at"] = __import__("datetime").datetime.utcnow().isoformat()
                await storage.save(f"personal_facts:{user_id}", data)
                logger.info("PERSONAL_FACTS_PROFESSION_REMOVED user=%s keys=%s", user_id, removed)
        except Exception as e:
            logger.debug("PERSONAL_FACTS_PROFESSION_REMOVE_ERROR err=%s", e)

    async def get_all(self, user_id: str) -> List[Dict]:
        """Restituisce tutti i fatti personali salvati."""
        data = await storage.load(f"personal_facts:{user_id}", default={"facts": []})
        return data.get("facts", [])

    async def get_relevant(self, user_id: str, query: str, limit: int = 8) -> List[Dict]:
        """
        Restituisce i fatti più rilevanti per la query.
        Se nessun match diretto, restituisce i più recenti.
        """
        facts = await self.get_all(user_id)
        if not facts:
            return []

        query_lower = query.lower()
        query_words = set(w for w in query_lower.split() if len(w) > 2)

        scored = []
        for f in facts:
            text_lower = f["text"].lower()
            key_lower = f.get("key", "").lower()
            score = sum(1 for w in query_words if w in text_lower or w in key_lower)
            scored.append((score, f))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Restituisce solo se ci sono match diretti con score > 0
        matches = [f for score, f in scored if score > 0]
        return matches[:limit]


personal_facts_service = PersonalFactsService()
