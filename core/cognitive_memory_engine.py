import logging
import re
from core.storage import storage
from core.brain_state import brain_state

logger = logging.getLogger(__name__)

def _is_strong_emotional(message: str) -> bool:
    """Detect strong emotional patterns using substring matching."""
    strong_patterns = [
        "disperat",
        "devastat",
        "distrutt",
        "non ce la faccio",
        "sto mal",
        "malissimo",
        "piango",
        "a pezzi",
        "non so più cosa fare",
        "sono a terra",
        "mi sento perso",
        "molto triste"
    ]
    
    m = message.lower()
    has_strong = any(p in m for p in strong_patterns)
    
    # FASE 5: Strong Emotional Persistence
    # Controlla "sempre" + emozione forte
    has_always = "sempre" in m
    
    # Controlla ripetizione (semplificato - in realtà richiederebbe storico)
    has_repetition = any(m.count(word) >= 2 for word in ["triste", "felice", "arrabbiato", "preoccupato"])
    
    return has_strong or (has_always and has_strong) or has_repetition

class CognitiveMemoryEngine:
    async def evaluate_event(self, user_id, message, extracted_profile_data):
        # Initialize field and value
        field = None
        value = None
        persist = False
        memory_type = None
        
        # FASE 3: Carica stato brain completo
        brain_state.load_from_storage(user_id)
        
        # Load existing profile data (sync)
        try:
            existing_profile_data = storage._storage.get(f"profile:{user_id}", {})
        except:
            existing_profile_data = {}
        
        # Initialize extracted_profile_data with existing data
        if existing_profile_data:
            extracted_profile_data.update(existing_profile_data)
        
        # GUARD: Non cercare di estrarre identità da domande esplicite sulla propria identità
        if "?" in message or any(q in message.lower() for q in ["chi sono", "come mi chiamo", "che lavoro", "dove vivo", "cosa sai di me"]):
            logger.info("COGNITIVE_IDENTITY_QUESTION_SKIP reason=question_detected message=%s", message)
            return {"persist": False, "memory_type": None, "key": None, "value": None, "confidence": 0.0}

        # Check for strong emotional patterns first
        if _is_strong_emotional(message):
            return {
                "persist": True,
                "memory_type": "emotional",
                "key": "emotional_state",
                "value": message.strip(),
                "confidence": 0.9
            }

        # Semantic classification using regex
        name_match = re.search(r"mi chiamo (\w+)", message, re.IGNORECASE)
        # Limita la cattura a max 3 parole per evitare di salvare frasi di contesto come professione
        profession_match = re.search(r"(?:faccio|sono|lavoro come)\s+(?:il\s+|la\s+|l\s+)?(\w+(?:\s+\w+){0,2})", message, re.IGNORECASE)
        city_match = re.search(r"vivo a (\w+)", message, re.IGNORECASE)
        spouse_match = re.search(r"(?:mia moglie|mio marito) si chiama (\w+)", message, re.IGNORECASE)
        children_match = re.search(r"i miei figli si chiamano (\w+) e (\w+)", message, re.IGNORECASE)
        dog_match = re.search(r"il mio cane si chiama (\w+)", message, re.IGNORECASE)
        cat_match = re.search(r"la mia gatta si chiama (\w+)", message, re.IGNORECASE)

        # Preference extraction — categorized
        pref_result = self._extract_preference(message)
        if pref_result:
            pref_category, pref_value = pref_result
            preferences = extracted_profile_data.get("preferences", {})
            if not isinstance(preferences, dict):
                preferences = {}
            cat_list = preferences.get(pref_category, [])
            if pref_value not in cat_list:
                cat_list.append(pref_value)
                preferences[pref_category] = cat_list
                extracted_profile_data["preferences"] = preferences
                persist = True
                memory_type = "profile"
                logger.info("COGNITIVE_PREFERENCE_EXTRACT category=%s value=%s", pref_category, pref_value)

        # Extract all profile fields and update the extracted_profile_data
        if name_match:
            extracted_name = name_match.group(1)
            extracted_profile_data["name"] = extracted_name
            persist = True
            memory_type = "profile"
            field = "name"
            value = extracted_name
            logger.info("COGNITIVE_NAME_EXTRACT value=%s", value)
            
            # FIX DEFINITIVO: Scrittura diretta su storage
            profile = await storage.load(f"profile:{user_id}", default={}) or {}
            profile["name"] = extracted_name
            await storage.save(f"profile:{user_id}", profile)
            logger.info("STORAGE_DIRECT_WRITE user=%s name=%s", user_id, extracted_name)
            
        if city_match:
            extracted_profile_data["city"] = city_match.group(1)
            persist = True
            memory_type = "profile"
            field = "city"
            value = city_match.group(1)
            logger.info("COGNITIVE_CITY_EXTRACT value=%s", value)
            
        # Parole/frasi che indicano situazioni o attività — NON professioni
        _PROFESSION_STOPWORDS = {
            "account", "collega", "miei", "quali", "appuntamento", "promemoria",
            "a cena", "a casa", "a lavoro", "in giro", "in vacanza", "in viaggio",
            "tempo", "fuori", "qui", "bene", "male", "stanco", "stanca",
            "andato", "andata", "tornato", "pronto", "pronta", "sveglio", "sveglia",
        }
        # Preposizioni/articoli che non possono aprire una professione
        _PROFESSION_BAD_STARTERS = {
            "a", "da", "con", "per", "di", "in", "su", "tra", "fra",
            "un", "una", "dello", "della", "delle", "degli",
        }

        if profession_match:
            new_profession = profession_match.group(1).strip().lower()  # lowercase come richiesto

            # GUARD: evita di salvare situazioni/attività come professione
            if any(kw in new_profession for kw in _PROFESSION_STOPWORDS):
                logger.info("COGNITIVE_PROFESSION_SKIP value=%s reason=stopword", new_profession)
            elif new_profession.split()[0].lower() in _PROFESSION_BAD_STARTERS:
                logger.info("COGNITIVE_PROFESSION_SKIP value=%s reason=bad_starter", new_profession)
            elif len(new_profession.split()) > 3:
                logger.info("COGNITIVE_PROFESSION_SKIP value=%s reason=too_long", new_profession)
            else:
                old_profession = extracted_profile_data.get("profession")
                
                # Handle profession contradiction
                if old_profession and old_profession != new_profession:
                    # Update to new profession
                    extracted_profile_data["profession"] = new_profession
                    field = "profession"
                    value = new_profession
                    persist = True
                    memory_type = "profile"
                    logger.info("COGNITIVE_PROFESSION_UPDATED old=%s new=%s", old_profession, new_profession)
                else:
                    # First time setting profession
                    extracted_profile_data["profession"] = new_profession
                    field = "profession"
                    value = new_profession
                    persist = True
                    memory_type = "profile"
                
                logger.info("COGNITIVE_PROFESSION_EXTRACT value=%s", value)
                
                # FIX DEFINITIVO: Scrittura diretta su storage
                profile = await storage.load(f"profile:{user_id}", default={}) or {}
                profile["profession"] = new_profession
                await storage.save(f"profile:{user_id}", profile)
                logger.info("STORAGE_DIRECT_WRITE user=%s profession=%s", user_id, new_profession)

        if spouse_match:
            extracted_spouse = spouse_match.group(1)
            extracted_profile_data["spouse"] = extracted_spouse
            persist = True
            memory_type = "profile"
            field = "spouse"
            value = extracted_spouse
            logger.info("COGNITIVE_SPOUSE_EXTRACT value=%s", value)
            
            # FIX DEFINITIVO: Scrittura diretta su storage
            profile = await storage.load(f"profile:{user_id}", default={}) or {}
            profile["spouse"] = extracted_spouse
            await storage.save(f"profile:{user_id}", profile)
            logger.info("STORAGE_DIRECT_WRITE user=%s spouse=%s", user_id, extracted_spouse)

        if children_match:
            extracted_profile_data["children"] = [{"name": children_match.group(1)}, {"name": children_match.group(2)}]
            persist = True
            memory_type = "profile"
            field = "children"
            value = [{"name": children_match.group(1)}, {"name": children_match.group(2)}]
            logger.info("COGNITIVE_CHILDREN_EXTRACT value=%s", value)

        if dog_match:
            extracted_profile_data["pets"] = {"type": "dog", "name": dog_match.group(1)}
            persist = True
            memory_type = "profile"
            field = "pets"
            value = {"type": "dog", "name": dog_match.group(1)}
            logger.info("COGNITIVE_PETS_EXTRACT value=%s", value)

        if cat_match:
            extracted_profile_data["pets"] = {"type": "cat", "name": cat_match.group(1)}
            persist = True
            memory_type = "profile"
            field = "pets"
            value = {"type": "cat", "name": cat_match.group(1)}
            logger.info("COGNITIVE_PETS_EXTRACT value=%s", value)

        # Emotional event detection - use substring matching
        strong_keywords = [
            "disperato",
            "distrutto",
            "depresso",
            "non ce la faccio",
            "sto malissimo",
            "a pezzi",
            "mi sento perso"
        ]
        
        msg_lower = message.lower()
        for k in strong_keywords:
            if k in msg_lower:
                persist = True
                memory_type = "emotional"
                field = "emotional_state"
                value = message.strip()
                logger.info("COGNITIVE_EMOTIONAL_EVENT detected keyword=%s", k)
                break

        # Ensure field and value are initialized
        if field is not None and value is not None:
            persist = True
            if memory_type == "emotional":
                logger.info("COGNITIVE_EVAL type=emotional field=%s confidence=0.9", field)
                logger.info("COGNITIVE_DECISION persist=true")
                logger.info("COGNITIVE_EMOTIONAL_UPDATE field=%s value=%s", field, value)
            else:
                logger.info("COGNITIVE_EVAL type=identity field=%s confidence=0.9", field)
                logger.info("COGNITIVE_DECISION persist=true")
                logger.info("COGNITIVE_MEMORY_UPDATE field=%s value=%s", field, value)
            
            # Handle list types
            if field == "children" or field == "pets":
                existing_value = extracted_profile_data.get(field, [])
                if isinstance(existing_value, list):
                    existing_value.extend(value)
                else:
                    extracted_profile_data[field] = value
            else:
                extracted_profile_data[field] = value
            
            # Save to storage if persist=True
            if persist and memory_type == "profile":
                # Save to sync storage for immediate persistence
                storage._storage[f"profile:{user_id}"] = extracted_profile_data
                # Also trigger async save in background (fire and forget)
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.create_task(storage.save(f"profile:{user_id}", extracted_profile_data))
                except RuntimeError:
                    # No event loop, skip async save - sync storage is enough
                    pass
                logger.info("COGNITIVE_PROFILE_SAVED user=%s field=%s", user_id, field)
        else:
            persist = False
            memory_type = None
            logger.info("COGNITIVE_DECISION persist=false reason=low_relevance")

        return {
            "persist": persist,
            "memory_type": memory_type,
            "key": field,
            "value": value,
            "confidence": 0.9  # High confidence for name and profession
        }

    def _extract_preference(self, message: str):
        """Extract categorized preference from message. Returns (category, value) or None."""
        msg_lower = message.lower()

        # Music preferences
        music_patterns = [
            r"mi piace (?:la |l')?musica (\w[\w\s]*)",
            r"ascolto (?:la |l')?musica (\w[\w\s]*)",
            r"ascolto (\w[\w\s]*?) (?:come|di) musica",
            r"mi piace (?:il |l')?(rock|pop|jazz|blues|metal|rap|hip hop|classica|elettronica|reggae|funk|soul|r&b|techno|house|trap|indie)",
            r"ascolto (?:il |l')?(rock|pop|jazz|blues|metal|rap|hip hop|classica|elettronica|reggae|funk|soul|r&b|techno|house|trap|indie)",
            r"la mia musica preferita [eè] (?:la |il |l')?(\w[\w\s]*)",
        ]
        for pat in music_patterns:
            m = re.search(pat, msg_lower)
            if m:
                return ("music", m.group(1).strip())

        # Food preferences
        food_patterns = [
            r"mi piac(?:e|ciono) (?:le |i |l[ae] |gli )?(\w[\w\s]*?) (?:da mangiare|come (?:cibo|frutto|frutta|verdura|piatto))",
            r"(?:il mio|la mia) (?:cibo|frutto|frutta|piatto|verdura) preferit[oa] [eè] (?:la |il |le |i |l')?(\w[\w\s]*)",
            r"mi piace mangiare (?:la |il |le |i |l')?(\w[\w\s]*)",
            r"adoro (?:la |il |le |i |l')?(\w[\w\s]*?) (?:da mangiare|come cibo)",
            r"mi piac(?:e|ciono) (?:le |i |l[ae] |gli )?(banane|mele|arance|fragole|pizza|pasta|sushi|cioccolato|gelato|pane|riso|pesce|carne|verdure|insalata)",
            r"(?:il mio|la mia) frutto preferito (?:sono|[eè]) (?:le |i |l[ae] |gli )?(\w[\w\s]*)",
        ]
        for pat in food_patterns:
            m = re.search(pat, msg_lower)
            if m:
                return ("food", m.group(1).strip())

        # General preferences (catch-all "mi piace X")
        general_patterns = [
            r"mi piace (?:molto |tanto )?(\w[\w\s]{2,30})",
            r"adoro (\w[\w\s]{2,30})",
            r"la mia passione [eè] (?:la |il |l')?(\w[\w\s]*)",
        ]
        for pat in general_patterns:
            m = re.search(pat, msg_lower)
            if m:
                val = m.group(1).strip()
                # Skip if it's a person reference or too short
                if len(val) < 3 or val in ("il", "la", "le", "lo", "un", "una"):
                    continue
                return ("general", val)

        return None

    def compute_scores(self, message):
        # Implement scoring logic
        scores = {
            'identity_score': self._compute_identity_score(message),
            'relational_score': self._compute_relational_score(message),
            'emotional_score': self._compute_emotional_score(message),
            'repetition_score': self._compute_repetition_score(message),
            'future_relevance_score': self._compute_future_relevance_score(message)
        }
        return scores

    def should_persist(self, scores):
        # Calculate total score as weighted average
        total_score = sum(scores.values()) / len(scores)
        return total_score >= 0.6

    def apply_decay(self, user_id):
        # Implement decay logic
        logger.info("APPLY_DECAY user_id=%s", user_id)
        # Placeholder for decay logic
        pass

    def resolve_conflicts(self, existing_memory, new_data):
        # Resolve conflicts by prioritizing new_data
        return {**existing_memory, **new_data}

    def _compute_identity_score(self, message):
        # Dummy implementation
        return 0.5

    def _compute_relational_score(self, message):
        # Dummy implementation
        return 0.5

    def _compute_emotional_score(self, message):
        # Dummy implementation
        return 0.5

    def _compute_repetition_score(self, message):
        # Dummy implementation
        return 0.5

    def _compute_future_relevance_score(self, message):
        # Dummy implementation
        return 0.5
