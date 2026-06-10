import os
import json
import logging
import re
import time

logger = logging.getLogger(__name__)

FACES_DIR = "data/faces"

def _ensure_dir():
    if not os.path.exists(FACES_DIR):
        os.makedirs(FACES_DIR, exist_ok=True)

async def save_known_face(name: str, image_path: str, description_in_image: str, gender: str = "?"):
    """
    Salva il riferimento di un volto associandolo all'immagine originale
    e alla descrizione visiva (es. "la donna a sinistra con capelli castani").

    Args:
        name: Nome del volto
        image_path: Percorso all'immagine
        description_in_image: Descrizione del volto (posizione + caratteristiche fisiche)
        gender: Genere dedotto ('M', 'F', o '?')
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

    # Normalizza genere
    gender_norm = str(gender).upper() if gender and str(gender).upper() in ("M", "F") else "?"

    data = {
        "name": name.strip(),
        "image_path": new_img_path,
        "description_in_image": description_in_image,
        "gender": gender_norm,
        "ts": int(time.time())
    }

    json_path = os.path.join(FACES_DIR, f"{clean_name}.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("FACE_MEMORY_SAVED name=%s gender=%s", name, gender_norm)

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
    session_key = f"short_term_chat:awaiting_faces_{user_or_group_id}"
    await storage.save(session_key, {"img_path": img_path, "description": description, "ts": int(time.time())})

async def get_awaiting_faces(user_or_group_id: str) -> dict:
    """Recupera lo stato di attesa volti per una sessione senza rimuoverlo."""
    from core.storage import storage
    session_key = f"short_term_chat:awaiting_faces_{user_or_group_id}"
    return await storage.load(session_key, default=None)

async def pop_awaiting_faces(user_or_group_id: str) -> dict:
    """Recupera e rimuove lo stato di attesa volti per una sessione."""
    from core.storage import storage
    session_key = f"short_term_chat:awaiting_faces_{user_or_group_id}"
    data = await storage.load(session_key, default=None)
    if data:
        await storage.delete(session_key)
    return data

async def try_extract_faces_from_text(text: str, tmp_img: str, desc_img: str, session_uid: str) -> bool:
    """
    Tenta di estrarre i nomi dei volti o degli animali dal testo e salvarli.
    Gestisce sia posizioni esplicite ("Mariella a sinistra") sia ordine implicito
    ("da sinistra: Mariella, Rita, Zoe, Iolanda") derivando le posizioni dalla descrizione visiva.
    Salva TUTTI i soggetti forniti, con descrizione fisica per riferimento futuro.
    """
    if not text or not tmp_img or not desc_img:
        return False

    if not os.path.exists(tmp_img):
        return False

    from core.llm_service import llm_service

    # Estrai conteggio soggetti dalla descrizione per validazione
    unknown_count_hint = ""
    m = re.search(r"\[TOTAL_HUMANS:(\d+)\]", desc_img)
    if m:
        unknown_count_hint = f"\nNell'immagine sono presenti {m.group(1)} persone in totale."
    m2 = re.search(r"\[TOTAL_PETS:(\d+)\]", desc_img)
    if m2:
        unknown_count_hint += f"\nNell'immagine sono presenti {m2.group(1)} animali in totale."

    extract_prompt = (
        "L'utente sta fornendo i nomi delle persone e/o degli animali domestici presenti in una foto.\n"
        f"Descrizione visiva della foto (dall'analisi AI): {desc_img}\n"
        f"{unknown_count_hint}\n"
        f"Risposta dell'utente: {text}\n\n"
        "COMPITO: Estrai TUTTI i nomi propri (di persone o animali) e associa ciascuno "
        "alla sua posizione nella foto (0=primo da sinistra, 1=secondo, ecc.).\n"
        "REGOLE:\n"
        "1. Se l'utente elenca nomi in ordine (es. 'da sinistra Mariella, Rita, Zoe, Iolanda'), "
        "   assegna position_index 0, 1, 2, 3 nell'ordine fornito.\n"
        "2. Se l'utente usa posizioni esplicite (es. 'quella a destra e Iolanda'), "
        "   deduci la posizione dalla descrizione visiva della foto.\n"
        "3. Aggiungi 'type': 'human' o 'pet' per ogni soggetto.\n"
        "4. Aggiungi 'gender': 'M', 'F' o '?' (dal nome, dalla descrizione visiva o "
        "   dai [GENDER_VISUAL_HINTS] se presenti nella descrizione).\n"
        "5. Aggiungi 'visual_desc': breve descrizione fisica del soggetto estratta dalla "
        "   descrizione visiva (es. 'donna capelli castani, maglia rossa'). "
        "   Serve per memorizzare l'aspetto. Usa la descrizione della foto.\n"
        "6. Se l'utente non fornisce nomi (parla di altro), rispondi [].\n\n"
        "Formatta la risposta ESCLUSIVAMENTE come array JSON:\n"
        "[{\"name\": \"Mariella\", \"position_index\": 0, \"type\": \"human\", "
        "\"gender\": \"F\", \"visual_desc\": \"donna capelli biondi a sinistra\"}, ...]\n"
        "Nessun testo aggiuntivo fuori dal JSON."
    )

    try:
        raw_ext = await llm_service._call_model(
            "openai/gpt-4o-mini", extract_prompt, text,
            user_id=str(session_uid), route="memory"
        )
        clean = raw_ext.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed_faces = json.loads(clean.strip())
        logger.info("EXTRACTED_FACES raw=%s parsed=%s", raw_ext[:200], parsed_faces)

        if parsed_faces and isinstance(parsed_faces, list):
            saved_count = 0
            for face_data in parsed_faces:
                name = face_data.get("name")
                pos_idx = face_data.get("position_index")
                if pos_idx is None:
                    pos_idx = 0
                subject_type = face_data.get("type", "human")
                gender = face_data.get("gender", "?")
                visual_desc = face_data.get("visual_desc", "")

                if not name or not name.strip():
                    continue

                # Description con indice + descrizione fisica per embedding futuro
                f_desc = f"[INDEX:{pos_idx}]"
                if visual_desc:
                    f_desc += f" {visual_desc}"

                if subject_type == "pet":
                    try:
                        from core.biometric_pets_service import compute_and_save_pet_embeddings
                        res = await compute_and_save_pet_embeddings(name, tmp_img, f_desc)
                        logger.info(
                            "PET_SAVED FROM TEXT name=%s index=%s gender=%s res=%s visual=%s",
                            name, pos_idx, gender, res, visual_desc
                        )
                        saved_count += 1
                    except Exception as ep:
                        logger.error("Error saving pet embedding: %s", ep)
                else:
                    await save_known_face(name, tmp_img, f_desc, gender=gender)
                    logger.info(
                        "FACE_SAVED FROM TEXT name=%s index=%s gender=%s visual=%s",
                        name, pos_idx, gender, visual_desc
                    )
                    saved_count += 1

            return saved_count > 0

    except Exception as e:
        logger.warning("Error parsing faces names: %s", e)

    return False
