import logging
import re
from core.storage import storage

logger = logging.getLogger(__name__)

class CognitiveMemoryEngine:
    async def evaluate_event(self, user_id, message, extracted_profile_data):
        # Initialize field and value
        field = None
        value = None

        # Semantic classification using regex
        name_match = re.search(r"mi chiamo (\w+)", message, re.IGNORECASE)
        profession_match = re.search(r"faccio il (\w+)", message, re.IGNORECASE)
        spouse_match = re.search(r"(?:mia moglie|mio marito) si chiama (\w+)", message, re.IGNORECASE)
        children_match = re.search(r"i miei figli si chiamano (\w+) e (\w+)", message, re.IGNORECASE)
        dog_match = re.search(r"il mio cane si chiama (\w+)", message, re.IGNORECASE)
        cat_match = re.search(r"la mia gatta si chiama (\w+)", message, re.IGNORECASE)

        if name_match:
            field = "name"
            value = name_match.group(1)
        elif profession_match:
            field = "profession"
            value = profession_match.group(1)
        elif spouse_match:
            field = "spouse"
            value = spouse_match.group(1)
        elif children_match:
            field = "children"
            value = [{"name": children_match.group(1)}, {"name": children_match.group(2)}]
        elif dog_match:
            field = "pets"
            value = {"type": "dog", "name": dog_match.group(1)}
        elif cat_match:
            field = "pets"
            value = {"type": "cat", "name": cat_match.group(1)}

        # Ensure field and value are initialized
        if field and value:
            persist = True
            memory_type = "profile"
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
