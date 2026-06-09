import os
import json
import logging
import time

logger = logging.getLogger(__name__)

FACES_DIR = "data/faces"

def _ensure_dir():
    if not os.path.exists(FACES_DIR):
        os.makedirs(FACES_DIR, exist_ok=True)

async def save_known_face(name: str, image_path: str, description_in_image: str):
    """
    Salva il riferimento di un volto associandolo all'immagine originale
    e alla descrizione visiva (es. "l'uomo a sinistra con il cappello").
    """
    _ensure_dir()
    clean_name = name.strip().lower().replace(" ", "_")
    
    # Previene l'apprendimento di nomi segnaposto
    invalid_names = {"unknown", "sconosciuto", "ignoto", "persona", "ragazzo", "ragazza", "uomo", "donna"}
    if not clean_name or clean_name in invalid_names:
        logger.warning("Tentativo di salvare un volto con nome non valido: %s", name)
        return
        
        
    import shutil
    new_img_name = f"{clean_name}_{int(time.time())}.jpg"
    new_img_path = os.path.join(FACES_DIR, new_img_name)
    
    # Copia l'immagine per tenerla persistente
    try:
        shutil.copy2(image_path, new_img_path)
    except Exception as e:
        logger.error("Error copying face image: %s", e)
        return

    data = {
        "name": name.strip(),
        "image_path": new_img_path,
        "description_in_image": description_in_image,
        "ts": int(time.time())
    }
    
    json_path = os.path.join(FACES_DIR, f"{clean_name}.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("FACE_MEMORY_SAVED name=%s", name)
        
        # Calcola e salva embedding biometrico
        from core.biometric_service import compute_and_save_embeddings
        saved_faces = await compute_and_save_embeddings(name, new_img_path, description_hint=description_in_image)
        logger.info("BIOMETRIC_EMBEDDING_SAVED name=%s faces_count=%d", name, saved_faces)
    except Exception as e:
        logger.error("Error saving face: %s", e)

async def get_known_faces() -> list[dict]:
    """
    Ritorna una lista di facce note: [{"name": "Rita", "image_path": "...", "description_in_image": "..."}]
    """
    _ensure_dir()
    faces = []
    for fname in os.listdir(FACES_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(FACES_DIR, fname), "r", encoding="utf-8") as f:
                    faces.append(json.load(f))
            except Exception as e:
                logger.warning("Error loading face %s: %s", fname, e)
    return faces

# Gestione stato "In attesa di volti" globale

async def set_awaiting_faces(user_or_group_id: str, img_path: str, description: str):
    """Salva globalmente che siamo in attesa dei nomi dei volti per una certa sessione."""
    from core.storage import storage
    session_key = f"awaiting_faces:{user_or_group_id}"
    await storage.save(session_key, {"img_path": img_path, "description": description, "ts": int(time.time())}, expire=3600)

async def get_awaiting_faces(user_or_group_id: str) -> dict:
    """Recupera lo stato di attesa volti per una sessione senza rimuoverlo."""
    from core.storage import storage
    session_key = f"awaiting_faces:{user_or_group_id}"
    return await storage.load(session_key, default=None)

async def pop_awaiting_faces(user_or_group_id: str) -> dict:
    """Recupera e rimuove lo stato di attesa volti per una sessione."""
    from core.storage import storage
    session_key = f"awaiting_faces:{user_or_group_id}"
    data = await storage.load(session_key, default=None)
    if data:
        await storage.delete(session_key)
    return data

async def try_extract_faces_from_text(text: str, tmp_img: str, desc_img: str, session_uid: str) -> bool:
    """Tenta di estrarre i nomi dei volti o degli animali dal testo e salvarli."""
    if not text or not tmp_img or not desc_img:
        return False
        
    if not os.path.exists(tmp_img):
        return False
        
    from core.llm_service import llm_service
    extract_prompt = (
        "L'utente sta elencando le identità delle persone o degli animali domestici in una foto.\n"
        f"Descrizione dei soggetti (dall'analisi visiva): {desc_img}\n"
        f"Testo dell'utente: {text}\n"
        "Estrai le identità dei soggetti (nomi propri di persone o animali) e deduci il loro indice di posizione ESATTO da sinistra a destra nella foto (0 è il primo a sinistra, 1 il secondo, ecc.) basandoti rigorosamente sull'ordine o sulle posizioni fornite dall'utente.\n"
        "Aggiungi una chiave 'type' che vale 'human' o 'pet'.\n"
        "Formatta la risposta ESCLUSIVAMENTE come un array JSON di dizionari, con chiavi 'name', 'position_index', e 'type'.\n"
        "Se l'utente non ha fornito nomi o sta parlando di tutt'altro, ritorna [].\n"
        "Esempio valido: [{\"name\": \"Mariella\", \"position_index\": 0, \"type\": \"human\"}, {\"name\": \"Fido\", \"position_index\": 1, \"type\": \"pet\"}]"
    )
    try:
        raw_ext = await llm_service._call_model("openai/gpt-4o-mini", extract_prompt, text, user_id=session_uid, route="memory")
        clean = raw_ext.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed_faces = json.loads(clean.strip())
        
        if parsed_faces and isinstance(parsed_faces, list):
            for face_data in parsed_faces:
                name = face_data.get("name")
                pos_idx = face_data.get("position_index")
                subject_type = face_data.get("type", "human")
                
                if name and pos_idx is not None:
                    f_desc = f"[INDEX:{pos_idx}]"
                    if subject_type == "pet":
                        try:
                            from core.biometric_pets_service import compute_and_save_pet_embeddings
                            import asyncio
                            asyncio.create_task(compute_and_save_pet_embeddings(name, tmp_img, f_desc))
                            logger.info("PET_SAVED FROM TEXT name=%s index=%s", name, pos_idx)
                        except Exception as ep:
                            logger.error("Error saving pet embedding: %s", ep)
                    else:
                        await save_known_face(name, tmp_img, f_desc)
                        logger.info("FACE_SAVED FROM TEXT name=%s index=%s", name, pos_idx)
            return True
    except Exception as e:
        logger.warning("Error parsing faces names: %s", e)
    
    return False
