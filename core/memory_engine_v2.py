import json
import os
import logging

logger = logging.getLogger(__name__)

class MemoryEngineV2:
    def __init__(self, storage_dir="memory_v2"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def load_user_memory(self, user_id):
        try:
            with open(os.path.join(self.storage_dir, f"{user_id}.json"), "r") as f:
                memory = json.load(f)
                logger.info("MEMORY_V2_LOAD user_id=%s", user_id)
                return memory
        except FileNotFoundError:
            return {}

    def save_user_memory(self, user_id, memory):
        with open(os.path.join(self.storage_dir, f"{user_id}.json"), "w") as f:
            json.dump(memory, f)
            logger.info("MEMORY_V2_SAVE user_id=%s", user_id)

    def update_profile(self, user_id, key, value):
        memory = self.load_user_memory(user_id)
        memory["profile"] = memory.get("profile", {})
        memory["profile"][key] = value
        self.save_user_memory(user_id, memory)
        logger.info("MEMORY_V2_UPDATE user_id=%s key=%s", user_id, key)

    def update_relational(self, user_id, key, value):
        memory = self.load_user_memory(user_id)
        memory["relational"] = memory.get("relational", {})
        memory["relational"][key] = value
        self.save_user_memory(user_id, memory)
        logger.info("MEMORY_V2_UPDATE user_id=%s key=%s", user_id, key)

    def add_preference(self, user_id, category, value):
        memory = self.load_user_memory(user_id)
        memory.setdefault("preferences", {}).setdefault(category, []).append(value)
        self.save_user_memory(user_id, memory)
        logger.info("MEMORY_V2_UPDATE user_id=%s category=%s", user_id, category)

    def add_episodic_event(self, user_id, event):
        memory = self.load_user_memory(user_id)
        memory.setdefault("episodic", []).append(event)
        self.save_user_memory(user_id, memory)
        logger.info("MEMORY_V2_UPDATE user_id=%s event=%s", user_id, event)
