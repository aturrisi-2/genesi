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
    if not clean_name:
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
    except Exception as e:
        logger.error("Error saving face json: %s", e)

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
