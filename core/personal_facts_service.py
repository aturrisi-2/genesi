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
from typing import List, Dict, Optional

from core.storage import storage
from core.log import log as _structured_log

logger = logging.getLogger("genesi")

_EXTRACTION_PROMPT = """\
Sei un assistente che estrae fatti personali appresi durante la conversazione.

ESTRAI fatti duraturi che l'utente ha rivelato su se stesso o la sua famiglia:
- Dove sono stati o stanno i familiari ("mia figlia è stata a Cork in Irlanda")
- Preferenze specifiche ("i miei piloti F1 preferiti sono Leclerc e Hamilton", "tifo per la Ferrari")
- Abitudini e routine ("di solito ceno alle 20:00", "mi sveglio alle 7")
- Hobby e passioni specifiche ("colleziono vinili", "gioco a padel il sabato")
- Fatti sulla famiglia o amici ("mio figlio studia medicina", "mia moglie lavora in ospedale")
- Amici e relazioni rilevanti ("il mio migliore amico si chiama Marco", "la mia collega Giulia")
- Valori e credenze importanti ("ci tengo molto alla famiglia", "per me il lavoro è tutto", "la lealtà è fondamentale")
- Sfide ricorrenti ("fatico a dormire", "ho difficoltà con la gestione del tempo", "mi perdo nei dettagli")
- Aspetti della personalità rilevati dal parlato ("sono una persona ansiosa", "tendo ad essere perfezionista", "sono molto riservato")
- Contesto attuale importante ("sta attraversando un periodo difficile al lavoro", "è in un momento di transizione")
- Obiettivi e aspirazioni ("voglio imparare a suonare la chitarra", "voglio smettere di fumare", "sto cercando di perdere peso")
- Argomenti o temi di cui abbiamo parlato ("Abbiamo parlato di Formula 1")

NON ESTRARRE:
- Dati strutturati già nel profilo: nome, città di residenza, nome del coniuge, nomi dei figli, animali domestici
- Appuntamenti o eventi temporali (quelli vanno agli episodi)
- Domande generiche su meteo, notizie, calcoli, orari pubblici
- Frasi di saluto o conversazione generica

Per ogni fatto estratto:
- "text": il fatto in terza persona ("L'utente cena di solito alle 20:00" / "L'utente tende ad essere perfezionista")
- "category": una di: ["famiglia", "interessi", "abitudini", "luoghi", "conversazione", "valori", "sfide", "personalità", "obiettivi", "relazioni", "altro"]
- "key": stringa breve univoca snake_case (es. "cena_ore_20", "f1_piloti_preferiti", "tende_perfezionista")

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
        ts = datetime.utcnow().isoformat()

        def _fact(text_str: str, category: str, key: str) -> Dict:
            return {"id": str(uuid.uuid4())[:8], "text": text_str,
                    "category": category, "key": key, "saved_at": ts}

        # 1. Dove sono/vivono i familiari ("mia figlia è a Cork")
        family_loc = re.search(
            r"(mia figlia|mio figlio|mio marito|mia moglie|mio padre|mia madre)"
            r" (?:è|si trova|abita|vive) a ([A-Z][a-zÀ-ÿ]+(?: [A-Z][a-zÀ-ÿ]+)*)",
            text, re.IGNORECASE)
        if family_loc:
            role = family_loc.group(1).lower().strip()
            loc = family_loc.group(2).strip().title()
            results.append(_fact(f"{role.capitalize()} è a {loc}.", "famiglia",
                                 f"{role.replace(' ', '_')}_a_{loc.lower().replace(' ', '_')}"))

        # 2. Orario pasti ("ceno alle 20", "pranzo alle 13")
        for meal, label in [("cen[oi]|mangio la sera", "cena"), ("pranzo|mangio a pranzo", "pranzo"), ("faccio colazione", "colazione")]:
            meal_m = re.search(
                rf"(?:di solito|solitamente|sempre)?[^.]*?(?:{meal})[^.]*?(?:alle|verso le) (\d{{1,2}}(?::\d{{2}})?)",
                text, re.IGNORECASE)
            if meal_m:
                t = meal_m.group(1)
                results.append(_fact(f"Fa {label} di solito alle {t}.", "abitudini", f"{label}_ore_{t.replace(':', '_')}"))

        # 3. Sport/attività fisica ("vado in palestra", "faccio jogging")
        sport_m = re.search(
            r"(?:vado|faccio|pratico|mi alleno|gioco a)\s+(in palestra|a correre|jogging|yoga|pilates|nuoto|calcio|tennis|basket|ciclismo|bici|boxe|crossfit|padel)",
            text, re.IGNORECASE)
        if sport_m:
            act = sport_m.group(1).lower().strip()
            results.append(_fact(f"Pratica {act}.", "interessi", f"sport_{act.replace(' ', '_')}"))

        # 4. Interessi espliciti ("mi piace/mi piacciono X")
        like_m = re.findall(
            r"mi (?:piace|piacciono|appassiona|interessa)\s+(?:molto\s+)?(?:la |le |il |i |l['']\s*)?([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{2,30}?)(?:[,.]|$)",
            text, re.IGNORECASE)
        for item in like_m[:2]:
            item = item.strip().lower()
            if len(item) > 2 and item not in ("sapere", "parlare", "sentire", "capire"):
                results.append(_fact(f"Gli piace: {item}.", "interessi", f"piace_{item[:30].replace(' ', '_')}"))

        # 5. Hobby/passioni ("ho una passione per", "sono appassionato di")
        hobby_m = re.search(
            r"(?:ho una passione per|sono appassionato(?:a)? di|il mio hobby è|nel tempo libero)\s+(?:la |le |il |i |l['']\s*)?([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{2,30}?)(?:[,.]|$)",
            text, re.IGNORECASE)
        if hobby_m:
            hobby = hobby_m.group(1).strip().lower()
            results.append(_fact(f"Hobby/passione: {hobby}.", "interessi", f"hobby_{hobby[:30].replace(' ', '_')}"))

        # 6. Studi ("ho studiato", "mi sono laureato in", "studio")
        study_m = re.search(
            r"(?:ho studiato|mi sono laureato(?:a)? in|studio|sto studiando)\s+([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{2,40}?)(?:[,.]|$)",
            text, re.IGNORECASE)
        if study_m:
            field = study_m.group(1).strip().lower()
            if len(field) > 3:
                results.append(_fact(f"Ha studiato/studia: {field}.", "biografia", f"studio_{field[:30].replace(' ', '_')}"))

        # 7. Auto/mezzo di trasporto ("ho una macchina", "vado al lavoro in treno")
        transport_m = re.search(
            r"(?:vado|vengo|mi sposto|viaggio) (?:al lavoro|in città|ogni giorno)? (?:in|con la|col)\s+(macchina|auto|moto|treno|bici|bicicletta|metro|autobus|scooter)",
            text, re.IGNORECASE)
        if transport_m:
            t = transport_m.group(1).lower()
            results.append(_fact(f"Si sposta in {t}.", "abitudini", f"trasporto_{t}"))

        # 8. Orario di lavoro ("lavoro dalle 9 alle 18", "finisco di lavorare alle 17")
        work_hours_m = re.search(
            r"(?:lavoro|finisco di lavorare|inizio a lavorare|entro|esco dal lavoro)[^.]*?(?:alle|verso le|dalle)\s*(\d{1,2}(?::\d{2})?)",
            text, re.IGNORECASE)
        if work_hours_m:
            wh = work_hours_m.group(1)
            results.append(_fact(f"Orario di lavoro indicativo: ore {wh}.", "abitudini", f"lavoro_ore_{wh.replace(':', '_')}"))

        # 9. Luogo di lavoro ("lavoro in centro", "lavoro da casa", "ufficio a Milano")
        workplace_m = re.search(
            r"(?:lavoro|sono) (?:in smart working|da casa|in ufficio|in remoto|al piano|nel centro)",
            text, re.IGNORECASE)
        if workplace_m:
            wp = workplace_m.group(0).strip().lower()
            results.append(_fact(f"Modalità lavoro: {wp}.", "lavoro", f"workplace_{wp[:20].replace(' ', '_')}"))

        # 10. Situazione finanziaria/economica implicita ("ho il mutuo", "affitto casa")
        finance_m = re.search(
            r"(ho il mutuo|pago l['']\s*affitto|sono in affitto|ho comprato casa|ho investito in)",
            text, re.IGNORECASE)
        if finance_m:
            fin = finance_m.group(1).lower()
            results.append(_fact(f"Situazione abitativa: {fin}.", "biografia", f"abitazione_{fin[:30].replace(' ', '_')}"))

        # 11. Salute/benessere ("soffro di", "ho problemi di")
        health_m = re.search(
            r"(?:soffro di|ho problemi di|sono celiaco|sono diabetico|sono allergico a|ho l['']\s*ansia|ho la pressione)\s*([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{1,30}?)(?:[,.]|$)",
            text, re.IGNORECASE)
        if health_m:
            cond = health_m.group(0).strip().lower()
            results.append(_fact(f"Salute/benessere: {cond}.", "salute", f"salute_{cond[:30].replace(' ', '_')}"))

        # 12. Preferenza musicale ("ascolto", "mi piace la musica")
        music_m = re.search(
            r"(?:ascolto|mi piace la musica|sono fan di|il mio genere musicale)\s*(?:molto\s*)?([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{1,25}?)(?:[,.]|$)",
            text, re.IGNORECASE)
        if music_m:
            genre = music_m.group(1).strip().lower()
            if len(genre) > 2 and genre not in ("tanto", "molto", "sempre", "spesso"):
                results.append(_fact(f"Musica preferita: {genre}.", "interessi", f"musica_{genre[:20].replace(' ', '_')}"))

        # 13. Cucina/cibo preferito ("adoro la pizza", "sono vegetariano", "sono vegano")
        food_m = re.search(
            r"(sono vegetariano|sono vegano|sono celiaco|sono intollerante al lattosio|non mangio carne|adoro la pasta|adoro la pizza|il mio piatto preferito è)",
            text, re.IGNORECASE)
        if food_m:
            fd = food_m.group(1).lower()
            results.append(_fact(f"Alimentazione: {fd}.", "abitudini", f"cibo_{fd[:30].replace(' ', '_')}"))

        # 14. Amici / relazioni non familiari ("il mio migliore amico", "la mia migliore amica", "la mia collega")
        friend_m = re.search(
            r"(?:il mio migliore amico|la mia migliore amica|il mio amico|la mia amica|il mio collega|la mia collega|il mio coinquilino|la mia coinquilina)\s+(?:si chiama|è)\s+(\w+)",
            text, re.IGNORECASE)
        if friend_m:
            name = friend_m.group(1).strip()
            prefix = friend_m.group(0).split("si chiama")[0].split("è")[0].strip().lower()
            results.append(_fact(f"Relazione: {prefix}, si chiama {name}.", "relazioni", f"amico_{name.lower()}"))

        # 15. Tendenze psicologiche ("tendo a", "di solito mi sento", "spesso mi capita di")
        psych_m = re.search(
            r"(?:tendo a|di solito mi sento|spesso mi sento|ho la tendenza a|mi capita spesso di)\s+([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{2,40}?)(?:[,.]|$)",
            text, re.IGNORECASE)
        if psych_m:
            trait = psych_m.group(1).strip().lower()
            if len(trait) > 3 and trait not in ("bene", "male", "così", "così"):
                results.append(_fact(f"Tendenza: tende a {trait}.", "personalità", f"tendenza_{trait[:30].replace(' ', '_')}"))

        # 16. Obiettivi espliciti ("voglio imparare", "voglio smettere", "voglio iniziare", "sto cercando di")
        goal_m = re.search(
            r"(?:voglio|vorrei)\s+(?:imparare|smettere di|iniziare a|diventare|riuscire a|provare a)\s+([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{2,40}?)(?:[,.]|$)",
            text, re.IGNORECASE)
        if goal_m:
            goal = goal_m.group(0).strip().lower()
            results.append(_fact(f"Obiettivo: {goal}.", "obiettivi", f"obiettivo_{goal[:30].replace(' ', '_')}"))

        # 17. Situazione attuale ("sto attraversando", "in questo periodo", "ultimamente")
        situation_m = re.search(
            r"(?:sto attraversando|in questo periodo|ultimamente|di recente|negli ultimi tempi)\s+([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{4,60}?)(?:[,.]|$)",
            text, re.IGNORECASE)
        if situation_m:
            sit = situation_m.group(0).strip().lower()
            if len(sit) > 10:
                results.append(_fact(f"Contesto attuale: {sit}.", "sfide", f"situazione_{sit[:30].replace(' ', '_')}"))

        # 18. Valori espliciti ("ci tengo molto a", "per me è importante", "la cosa più importante")
        value_m = re.search(
            r"(?:ci tengo molto a|per me è (?:molto )?importante|la (?:cosa|cosa più) importante per me è|per me conta)\s+([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{2,40}?)(?:[,.]|$)",
            text, re.IGNORECASE)
        if value_m:
            val = value_m.group(1).strip().lower()
            if len(val) > 3:
                results.append(_fact(f"Valore importante: {val}.", "valori", f"valore_{val[:30].replace(' ', '_')}"))

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
                    # Per interessi: accumula preferenze invece di sovrascrivere
                    merged = self._try_merge_preferences(new_f, existing_facts[conflict_idx])
                    if merged:
                        existing_facts[conflict_idx] = merged
                        fact_index = {f["key"]: i for i, f in enumerate(existing_facts)}
                        logger.info("PERSONAL_FACT_MERGED key=%s user=%s", merged["key"], user_id)
                    else:
                        existing_facts[conflict_idx] = new_f
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

    @staticmethod
    def _try_merge_preferences(new_f: Dict, existing_f: Dict) -> Optional[Dict]:
        """
        Se entrambi i fatti sono preferenze accumulative ("Gli piace: X"),
        aggiunge il nuovo item invece di sovrascrivere.
        Es: "Gli piace: pizza." + "Gli piace: pasta." → "Gli piace: pizza, pasta."
        """
        import re as _re
        _PAT = _re.compile(r'^(?:Gli|Le|Gli piace anche)(?:\s+piace(?:iono)?)?\s*[:\-]\s*(.+?)\.?\s*$', _re.IGNORECASE)
        _PIACE_PAT = _re.compile(r'[Gg]li piace[:\s]|piace[:\s]', _re.IGNORECASE)

        new_text = new_f.get("text", "")
        ex_text = existing_f.get("text", "")

        # Solo se entrambi hanno pattern "Gli piace:"
        if not (_PIACE_PAT.search(new_text) and _PIACE_PAT.search(ex_text)):
            return None

        ex_m = _PAT.match(ex_text)
        new_m = _PAT.match(new_text)
        if not (ex_m and new_m):
            return None

        existing_items = [i.strip().rstrip(".") for i in ex_m.group(1).split(",") if i.strip()]
        new_item = new_m.group(1).strip().rstrip(".")

        # Evita duplicati (case-insensitive)
        if any(new_item.lower() == ei.lower() for ei in existing_items):
            return None

        merged_items = existing_items + [new_item]
        merged_text = f"Gli piace: {', '.join(merged_items)}."
        return {
            **existing_f,
            "text": merged_text,
            "saved_at": new_f["saved_at"],
        }

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

        # Priorità a match diretti con score > 0
        matches = [f for score, f in scored if score > 0]
        if matches:
            return matches[:limit]
        # Fallback: ritorna i più recenti (as docstring promised)
        return sorted(facts, key=lambda f: f.get("saved_at", ""), reverse=True)[:limit]


personal_facts_service = PersonalFactsService()
