import uuid, os, tempfile, logging
from core.face_memory_service import set_awaiting_faces, get_awaiting_faces, pop_awaiting_faces, try_extract_faces_from_text

logger = logging.getLogger(__name__)

async def process_awaiting_faces(
    user_id: str,
    img_bytes: bytes,
    analysis: str,
    caption: str | None,
    session_uid: str,
) -> tuple[bool, str]:
    """Gestisce il flusso completo di attesa volti/pets.

    1️⃣ Salva temporaneamente l’immagine su disco.
    2️⃣ Registra lo stato di attesa tramite `set_awaiting_faces`.
    3️⃣ Se è presente una didascalia, tenta di estrarre i volti/pet con
       `try_extract_faces_from_text`.
    4️⃣ Se l’estrazione ha successo, rimuove il file temporaneo.
    5️⃣ Restituisce `(faces_saved, extra_msg)` dove `faces_saved` indica se
       sono state memorizzate nuove identità e `extra_msg` è un eventuale
       messaggio extra da aggiungere alla risposta di Genesi.
    """
    # 1️⃣ Salvataggio temporaneo
    tmp_path = os.path.join(tempfile.gettempdir(), f"genesi_face_{uuid.uuid4().hex[:8]}.jpg")
    try:
        with open(tmp_path, "wb") as f:
            f.write(img_bytes)
    except Exception as e:
        logger.error("Failed to write temporary face image: %s", e)
        return False, ""

    # 2️⃣ Registra attesa
    await set_awaiting_faces(user_id, tmp_path, analysis)

    faces_saved = False
    extra_msg = ""

    # 3️⃣ Se c’è caption, prova estrazione
    if caption:
        awaiting_data = await get_awaiting_faces(user_id)
        if awaiting_data:
            faces_saved = await try_extract_faces_from_text(
                caption, awaiting_data.get("img_path"), analysis, session_uid
            )
            if faces_saved:
                popped = await pop_awaiting_faces(user_id)
                if popped and popped.get("img_path"):
                    try:
                        os.remove(popped["img_path"])
                    except Exception as e:
                        logger.warning(
                            "Failed to remove temp face image %s: %s",
                            popped["img_path"],
                            e,
                        )
                extra_msg = "\n[SISTEMA: Hai estratto e memorizzato con successo le identità dei volti o degli animali.]"
    return faces_saved, extra_msg
