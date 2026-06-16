"""
FACE MEMORY SERVICE - Genesi Core
Servizio centralizzato per memorizzazione e identificazione di volti e animali.
Questo modulo è LA FONTE UNICA di verità per tutto il riconoscimento visivo,
indipendente dalla piattaforma (WhatsApp, Telegram, Web).

Principi:
- Nessun salvataggio di nomi placeholder (UNKNOWN, ecc.)
- Lo stato "awaiting_faces" persiste finché TUTTI gli sconosciuti sono identificati
- Le correzioni dell'utente aggiornano SEMPRE gli embedding globali
- Zero duplicazione della logica tra piattaforme
"""

import os
import json
import logging
import re
import time
from core.log import log

logger = logging.getLogger(__name__)

FACES_DIR = "data/faces"
FACES_PENDING_DIR = "data/faces_pending"  # immagini awaiting — sopravvivono al restart

# Nomi non validi da non salvare mai
_INVALID_NAMES = {
    # Placeholder generici
    "unknown", "sconosciuto", "sconosciuta", "sconosciuti", "sconosciute",
    "ignoto", "ignota", "persona", "ragazzo", "ragazza",
    "uomo", "donna", "bambino", "bambina", "uomo_sconosciuto", "donna_sconosciuta",
    "nessuno", "qualcuno", "qualcosa",
    # Specie animali (non sono nomi propri per umani; per animali usa sanitize_pet_name)
    "animale", "cane", "gatto", "gatta", "uccello", "coniglio", "criceto",
    # Pronomi
    "io", "lui", "lei", "tu", "noi", "voi", "loro",
    # Sostantivi relazionali nudi
    "mamma", "papa", "papà", "padre", "madre",
    "figlio", "figlia", "fratello", "sorella",
    "marito", "moglie", "nonno", "nonna",
    "zio", "zia", "cugino", "cugina", "nipote",
}

# Pattern: possessivo/articolo + sostantivo relazionale (es. mia_mamma, suo_marito, il_figlio)
_RELATIONAL_PATTERN = re.compile(
    r"^(mia|mio|sua|suo|tua|tuo|nostra|nostro|la|il|lo|le)_"
    r"(mamma|papa|pap.|padre|madre|figlio|figlia|fratello|sorella|"
    r"marito|moglie|nonno|nonna|zio|zia|cugino|cugina|nipote)",
    re.IGNORECASE,
)


def _is_relational_descriptor(clean_name: str) -> bool:
    """True se il nome è un descrittore relazionale (es. 'mia_mamma', 'suo_marito_gianvito')."""
    return bool(_RELATIONAL_PATTERN.match(clean_name))


def _is_identity_question(text: str) -> bool:
    """True se l'utente sta CHIEDENDO chi sono i soggetti della foto (vs. fornire nomi).

    Usato per distinguere 'Conosci chi sono in foto?' (domanda → re-ask) da
    'da sinistra Mariella, Rita' (nomi → estrazione) o testo non correlato.
    """
    if not text:
        return False
    low = text.lower()
    has_q = "?" in text or any(
        w in low for w in (
            "chi ", "chi?", "sai chi", "riconosci", "conosci", "li conosci", "sapresti",
            # richieste di elencare/dire i nomi (non solo domande con 'chi')
            "dimmi", "dicci", "sai dirmi", "puoi dirmi", "elenca", "quali sono",
            "come si chiama", "come si chiamano", "nomi", "nome di",
        )
    )
    has_subject = any(
        k in low for k in ("foto", "immagine", "soggett", "person", "volt", "facc",
                            "quest", "lì", "li ", "loro", "ritratt")
    )
    return has_q and has_subject


def _ensure_dir():
    if not os.path.exists(FACES_DIR):
        os.makedirs(FACES_DIR, exist_ok=True)


async def save_known_face(name: str, image_path: str, description_in_image: str, gender: str = "?"):
    """
    Salva il riferimento di un volto (umano) associandolo all'immagine originale
    e alla descrizione visiva. Aggiorna gli embedding biometrici globali.

    Args:
        name: Nome proprio del volto (non può essere un placeholder)
        image_path: Percorso all'immagine sorgente
        description_in_image: Descrizione fisica + posizione (es. "[INDEX:0] donna capelli castani")
        gender: Genere ('M', 'F', o '?')
    """
    _ensure_dir()
    clean_name = name.strip().lower().replace(" ", "_")

    # Blocca nomi placeholder / non validi / descrittori relazionali
    if not clean_name or clean_name in _INVALID_NAMES or _is_relational_descriptor(clean_name):
        logger.warning("FACE_SAVE_BLOCKED name=%s reason=invalid_name", name)
        log("FACE_SAVE_BLOCKED", name=name, clean=clean_name)
        return False

    import shutil
    new_img_name = f"{clean_name}_{int(time.time())}.jpg"
    new_img_path = os.path.join(FACES_DIR, new_img_name)

    try:
        shutil.copy2(image_path, new_img_path)
    except Exception as e:
        logger.error("FACE_COPY_ERROR name=%s err=%s", name, e)
        return False

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
        logger.info("FACE_MEMORY_SAVED name=%s gender=%s desc=%s", name, gender_norm, description_in_image[:60])
        log("FACE_MEMORY_SAVED", name=name, gender=gender_norm)

        # Aggiorna embedding biometrico globale
        from core.biometric_service import compute_and_save_embeddings
        saved = await compute_and_save_embeddings(name, new_img_path, description_hint=description_in_image)
        logger.info("BIOMETRIC_EMBEDDING_SAVED name=%s faces_count=%d", name, saved)
        return True
    except Exception as e:
        logger.error("FACE_SAVE_ERROR name=%s err=%s", name, e)
        return False


async def get_known_faces() -> list[dict]:
    """Ritorna la lista di tutte le facce note con i loro metadati."""
    _ensure_dir()
    faces = []
    for fname in os.listdir(FACES_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(FACES_DIR, fname), "r", encoding="utf-8") as f:
                    faces.append(json.load(f))
            except Exception as e:
                logger.warning("FACE_LOAD_ERROR file=%s err=%s", fname, e)
    return faces


# ─── Stato "In attesa di identificazione volti" ────────────────────────────────
# Chiave di storage: short_term_chat:awaiting_faces_{session_id}
# Il valore include:
#   - img_path: percorso all'immagine tmp
#   - description: analisi visiva completa con tag UNKNOWN/TOTAL
#   - unknown_count: numero di sconosciuti ancora da identificare
#   - identified: lista di nomi già identificati in questa sessione

async def set_awaiting_faces(session_id: str, img_path: str, description: str, unknown_count: int = 0):
    """
    Salva lo stato di attesa identificazione volti per una sessione.
    Mantiene lo stato finché TUTTI gli sconosciuti sono stati identificati.
    """
    from core.storage import storage
    session_key = f"short_term_chat:awaiting_faces_{session_id}"
    await storage.save(session_key, {
        "img_path": img_path,
        "description": description,
        "unknown_count": unknown_count,
        "identified": [],
        "ts": int(time.time())
    })
    logger.info("AWAITING_FACES_SET session=%s unknown_count=%d", session_id, unknown_count)
    log("AWAITING_FACES_SET", session=session_id, unknown_count=unknown_count)


_AWAITING_TTL = 1800  # 30 min: finestra per nomi/correzioni volti (era 600 = 10min,
                      # troppo corto: l'utente perdeva i nomi se rispondeva tardi)


async def get_awaiting_faces(session_id: str) -> dict | None:
    """Recupera lo stato di attesa volti per una sessione (scade dopo _AWAITING_TTL)."""
    from core.storage import storage
    session_key = f"short_term_chat:awaiting_faces_{session_id}"
    data = await storage.load(session_key, default=None)
    if data and time.time() - data.get("ts", 0) > _AWAITING_TTL:
        try:
            await storage.delete(session_key)
        except Exception:
            pass
        return None
    return data


async def pop_awaiting_faces(session_id: str) -> dict | None:
    """Recupera e RIMUOVE lo stato di attesa volti."""
    from core.storage import storage
    session_key = f"short_term_chat:awaiting_faces_{session_id}"
    data = await storage.load(session_key, default=None)
    if data:
        await storage.delete(session_key)
    return data


async def update_awaiting_faces_identified(session_id: str, new_names: list[str]) -> int:
    """
    Aggiorna la lista di nomi già identificati nella sessione corrente.
    Ritorna il numero di sconosciuti ancora da identificare.
    """
    from core.storage import storage
    session_key = f"short_term_chat:awaiting_faces_{session_id}"
    data = await storage.load(session_key, default=None)
    if not data:
        return 0
    existing = data.get("identified", [])
    for n in new_names:
        if n not in existing:
            existing.append(n)
    data["identified"] = existing
    unknown_count = data.get("unknown_count", 0)
    remaining = max(0, unknown_count - len(existing))
    data["remaining"] = remaining
    await storage.save(session_key, data)
    logger.info("AWAITING_FACES_UPDATED session=%s identified=%s remaining=%d", session_id, existing, remaining)
    log("AWAITING_FACES_UPDATED", session=session_id, remaining=remaining, identified=len(existing))
    return remaining


# ─── Estrazione nomi da testo (logica centralizzata, piattaforma-indipendente) ─

async def try_extract_faces_from_text(
    text: str,
    tmp_img: str,
    desc_img: str,
    session_uid: str,
    speaker_name: str | None = None,
) -> tuple[bool, list[str]]:
    """
    FUNZIONE CENTRALIZZATA — usata identicamente da WhatsApp, Telegram e Web.

    Tenta di estrarre i nomi delle persone/animali dal testo dell'utente e li salva.
    Gestisce:
    - Liste ordinate: "da sinistra Mariella, Rita, Zoe, Iolanda"
    - Posizioni esplicite: "quella a destra è Iolanda"
    - Risposte parziali: salva quelli noti, aggiorna il contatore dei rimanenti
    - Auto-riferimento: "sono io" → mappato a speaker_name (chi sta scrivendo)
    - Blocco nomi placeholder: non salva mai UNKNOWN, sconosciuto, ecc.

    Args:
        speaker_name: nome di chi sta scrivendo (per mappare 'io'/'sono io').

    Returns:
        (saved: bool, saved_names: list[str]) — True se almeno un nome è stato salvato
    """
    if not text or not tmp_img or not desc_img:
        return False, []

    # CRITICO: rimuovi i blocchi [SISTEMA: ...] eventualmente APPESI al messaggio
    # a valle (reask, conferme di memorizzazione). NON sono input dell'utente e
    # possono contenere nomi propri (es. l'elenco dei volti noti) che verrebbero
    # ri-estratti e salvati su volti SBAGLIATI, corrompendo gli embedding.
    if "[SISTEMA:" in text:
        text = re.sub(r"\[SISTEMA:.*?\]", "", text, flags=re.DOTALL).strip()
        if not text:
            return False, []

    if not os.path.exists(tmp_img):
        logger.warning("EXTRACT_FACES_NO_IMG session=%s img=%s", session_uid, tmp_img)
        return False, []

    from core.llm_service import llm_service

    # Estrai conteggio soggetti dalla descrizione per contesto
    count_hint = ""
    m = re.search(r"\[TOTAL_HUMANS:(\d+)\]", desc_img)
    if m:
        count_hint = f"\nNell'immagine sono presenti {m.group(1)} persone in totale."
    m2 = re.search(r"\[TOTAL_PETS:(\d+)\]", desc_img)
    if m2:
        count_hint += f"\nNell'immagine sono presenti {m2.group(1)} animali in totale."

    # Recupera nomi già identificati in questa sessione
    awaiting = await get_awaiting_faces(str(session_uid))
    already_known = awaiting.get("identified", []) if awaiting else []
    already_str = f"\nNomi già identificati in questa sessione: {', '.join(already_known)}." if already_known else ""

    # Auto-riferimento: se chi scrive dice "sono io" il nome è il suo (speaker_name).
    speaker_hint = ""
    if speaker_name and str(speaker_name).strip():
        _sp = str(speaker_name).strip()
        speaker_hint = (
            f"\nCHI STA SCRIVENDO SI CHIAMA: {_sp}. "
            f"Se l'utente usa la prima persona riferita a sé ('sono io', 'questo/a sono io', "
            f"'ci sono anch'io', 'la persona sono io'), il nome da associare a quel soggetto è '{_sp}'."
        )

    extract_prompt = (
        "L'utente sta fornendo i nomi delle persone e/o degli animali domestici presenti in una foto.\n"
        f"Descrizione visiva della foto (dall'analisi AI): {desc_img}\n"
        f"{count_hint}{already_str}{speaker_hint}\n"
        f"Risposta dell'utente: {text}\n\n"
        "COMPITO: Estrai SOLO i nomi propri NUOVI (non già elencati in 'Nomi già identificati') "
        "e associa ciascuno alla sua posizione nella foto (0=primo da sinistra, 1=secondo, ecc.).\n"
        "REGOLE FERREE:\n"
        "1. Se l'utente elenca nomi in ordine ('da sinistra Mariella, Rita, Zoe, Iolanda'), "
        "   assegna position_index 0,1,2,3 nell'ordine fornito.\n"
        "2. Se l'utente usa posizioni esplicite ('quella a destra è Iolanda'), "
        "   deduci la posizione dalla descrizione visiva.\n"
        "3. MAI inserire 'UNKNOWN', 'sconosciuto', 'ignoto' o simili come nome. "
        "   Se una persona o animale non ha un nome fornito dall'utente, OMETTI quella voce.\n"
        "4. Aggiungi 'type': 'human' o 'pet'.\n"
        "5. Aggiungi 'gender': 'M', 'F' o '?' (dal nome o dai [GENDER_VISUAL_HINTS]).\n"
        "6. Aggiungi 'visual_desc': caratteristiche fisiche del soggetto dalla descrizione visiva.\n"
        "7. Per animali ('type':'pet'): aggiungi 'species': 'cane'/'gatto'/'uccello'/ecc. "
        "   dalla descrizione visiva.\n"
        "8. Se l'utente non fornisce nomi (parla d'altro), restituisci [].\n"
        "9. MAI estrarre descrittori relazionali come nomi "
        "   (es. 'mia mamma', 'mio figlio', 'la moglie'). "
        "   Estrai SOLO il nome proprio di battesimo. "
        "   Se l'utente dice 'quella è mia mamma Iolanda', il nome è 'Iolanda'.\n"
        "10. Per animali: MAI usare specie o razza come nome ('il mio gatto', 'gatto persiano' "
        "    NON sono nomi). Il nome è quello dato dall'utente all'animale (es. 'Mignolo', 'Rio'). "
        "    Se l'utente non ha nominato l'animale, OMETTI quella voce.\n"
        "11. AUTO-RIFERIMENTO: se l'utente parla in prima persona di sé ('sono io', "
        "    'questo sono io'), quel soggetto è SEMPRE 'type':'human' ed è la PERSONA che scrive "
        "    (vedi 'CHI STA SCRIVENDO'). MAI associare un auto-riferimento a un animale.\n\n"
        "Output ESCLUSIVAMENTE come array JSON:\n"
        "[{\"name\": \"Mariella\", \"position_index\": 0, \"type\": \"human\", "
        "\"gender\": \"F\", \"visual_desc\": \"donna capelli biondi a sinistra\"}, "
        "{\"name\": \"Mignolo\", \"position_index\": 1, \"type\": \"pet\", "
        "\"species\": \"gatto\", \"gender\": \"M\", \"visual_desc\": \"gatto tigrato grigio\"}]\n"
        "Nessun testo fuori dal JSON."
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

        if not parsed_faces or not isinstance(parsed_faces, list):
            return False, []

        saved_count = 0
        saved_names = []

        for face_data in parsed_faces:
            name = (face_data.get("name") or "").strip()
            pos_idx = face_data.get("position_index", 0)
            subject_type = face_data.get("type", "human")
            gender = face_data.get("gender", "?")
            visual_desc = face_data.get("visual_desc", "")

            # Blocca nomi non validi — path diverso per pet e umani
            clean_n = name.lower().replace(" ", "_")
            if not name or _is_relational_descriptor(clean_n):
                logger.warning("EXTRACT_FACES_SKIP_RELATIONAL name=%s", name)
                continue

            if subject_type == "pet":
                from core.name_utils import sanitize_pet_name
                clean_pet = sanitize_pet_name(name)
                if not clean_pet:
                    logger.warning("EXTRACT_PET_SKIP_INVALID name=%s reason=species_or_breed", name)
                    continue
                name = clean_pet
            else:
                if clean_n in _INVALID_NAMES:
                    logger.warning("EXTRACT_FACES_SKIP_INVALID name=%s", name)
                    continue

            f_desc = f"[INDEX:{pos_idx}]"
            if visual_desc:
                f_desc += f" {visual_desc}"

            if subject_type == "pet":
                try:
                    from core.biometric_pets_service import compute_and_save_pet_embeddings
                    pet_species = face_data.get("species", "")
                    res = await compute_and_save_pet_embeddings(name, tmp_img, f_desc, species=pet_species)
                    logger.info("PET_SAVED name=%s index=%s visual=%s", name, pos_idx, visual_desc)
                    log("PET_SAVED", name=name, index=pos_idx)
                    saved_count += 1
                    saved_names.append(name)
                except Exception as ep:
                    logger.error("PET_SAVE_ERROR name=%s err=%s", name, ep)
            else:
                ok = await save_known_face(name, tmp_img, f_desc, gender=gender)
                if ok:
                    logger.info("FACE_SAVED FROM TEXT name=%s index=%s gender=%s visual=%s",
                                name, pos_idx, gender, visual_desc)
                    saved_count += 1
                    saved_names.append(name)

        if saved_count > 0:
            # Aggiorna lo stato awaiting con i nuovi nomi identificati
            remaining = await update_awaiting_faces_identified(str(session_uid), saved_names)
            logger.info("EXTRACT_FACES_DONE saved=%d remaining=%d", saved_count, remaining)
            log("EXTRACT_FACES_DONE", saved=saved_count, remaining=remaining, names=",".join(saved_names))
            return True, saved_names

    except Exception as e:
        logger.warning("EXTRACT_FACES_ERROR err=%s", e)

    return False, []


async def handle_photo_identification(
    session_id: str,
    img_bytes: bytes,
    analysis: str,
    caption: str | None = None,
    speaker_name: str | None = None,
) -> dict:
    """
    HANDLER CENTRALIZZATO per la gestione foto con soggetti sconosciuti.
    Chiamato da tutti i bot (Telegram, WhatsApp, Web) con la stessa logica.

    - Salva il tmp_img se ci sono sconosciuti
    - Se la caption contiene nomi, li estrae subito
    - Ritorna un dict con le istruzioni per il messaggio [SISTEMA] da iniettare

    Returns:
        {
            "faces_saved": bool,
            "saved_names": list[str],
            "remaining": int,       # sconosciuti ancora da identificare
            "sistema_msg": str,     # messaggio [SISTEMA] da iniettare nel prompt
            "tmp_img": str | None,  # percorso immagine tmp salvata
        }
    """
    import uuid
    import re as _re

    has_unknown_faces = "[UNKNOWN_FACES_DETECTED]" in analysis
    has_unknown_pets = "[UNKNOWN_PETS_DETECTED]" in analysis
    faces_saved = False
    saved_names = []
    tmp_img = None
    sistema_msg = ""

    # Calcola numero soggetti dalla descrizione
    _total_h = _re.search(r'\[TOTAL_HUMANS:(\d+)\]', analysis)
    _total_p = _re.search(r'\[TOTAL_PETS:(\d+)\]', analysis)
    n_humans = int(_total_h.group(1)) if _total_h else 0
    n_pets = int(_total_p.group(1)) if _total_p else 0

    if has_unknown_faces or has_unknown_pets:
        # Salva in data/faces_pending/ (persistente — sopravvive a restart e /tmp cleanup)
        try:
            os.makedirs(FACES_PENDING_DIR, exist_ok=True)
        except Exception:
            pass
        tmp_img = os.path.join(FACES_PENDING_DIR, f"genesi_face_{uuid.uuid4().hex[:10]}.jpg")
        try:
            with open(tmp_img, "wb") as f:
                f.write(img_bytes)
        except Exception as e:
            logger.error("PHOTO_ID_TMP_SAVE_ERROR err=%s", e)
            tmp_img = None

        # Calcola il numero di sconosciuti
        # = totale - quanti sono già stati riconosciuti dal biometrico
        # (approssimazione: conta le occorrenze di UNKNOWN nella descrizione
        #  come marker aggiunto dal vision service)
        # Conteggio sconosciuti dai marker AFFIDABILI iniettati dal vision service
        # ([UNKNOWN_HUMANS:N]/[UNKNOWN_PETS:N], derivati dal biometrico reale).
        # Fallback legacy (regex posizioni / totale) solo se i marker mancano.
        _m_uh = _re.search(r'\[UNKNOWN_HUMANS:(\d+)\]', analysis)
        _m_up = _re.search(r'\[UNKNOWN_PETS:(\d+)\]', analysis)
        if _m_uh or _m_up:
            unknown_count = (int(_m_uh.group(1)) if _m_uh else 0) + (int(_m_up.group(1)) if _m_up else 0)
        else:
            # Legacy: il biometrico marcava ogni sconosciuto con 'N° da sinistra'
            biometric_unknown = len(_re.findall(r'\d+° da sinistra', analysis))
            if biometric_unknown:
                unknown_count = biometric_unknown
            elif n_humans > 0:
                unknown_count = n_humans  # caso peggiore: tutti sconosciuti
            elif n_pets > 0:
                unknown_count = n_pets
            else:
                unknown_count = (analysis.count("[UNKNOWN_FACES_DETECTED]")
                                 + analysis.count("[UNKNOWN_PETS_DETECTED]"))

        # Aggiorna lo stato awaiting
        await set_awaiting_faces(session_id, tmp_img or "", analysis, unknown_count=unknown_count)

        # Se la caption già contiene nomi, estrai subito
        if caption and tmp_img:
            faces_saved, saved_names = await try_extract_faces_from_text(
                caption, tmp_img, analysis, session_id, speaker_name=speaker_name
            )
            if faces_saved:
                # Controlla se ci sono ancora sconosciuti
                awaiting = await get_awaiting_faces(session_id)
                remaining = awaiting.get("remaining", 0) if awaiting else 0
                if remaining <= 0:
                    await _cleanup_awaiting(session_id)

        if not faces_saved:
            # Costruisci il messaggio SISTEMA per chiedere i nomi
            if has_unknown_pets:
                pet_detail = f" ({n_pets} animale/i visibile/i nella foto)" if n_pets > 0 else ""
                sistema_msg += (
                    f"\n[SISTEMA: Hai visto questa foto. Hai rilevato {n_pets if n_pets > 0 else 'un'} "
                    f"animale/i{pet_detail} che non conosci. "
                    "DEVI chiedere il nome di CIASCUN animale sconosciuto, "
                    "DESCRIVENDO ogni animale con le sue caratteristiche visive specifiche "
                    "(colore del pelo, markings, taglia) così l'utente capisce di quale animale parli. "
                    "Esempio: 'Il gatto tigrato grigio con la macchia bianca sul muso — come si chiama?' "
                    "Se ci sono più animali sconosciuti, chiedili tutti uno per uno con le loro caratteristiche. "
                    "NON usare elenchi numerati. "
                    "NON inventare nomi. CHIEDI esplicitamente.]"
                )
            if has_unknown_faces:
                _detail = f"{unknown_count} persona/e che non conosci"
                if n_humans > 0:
                    _detail += f", su {n_humans} persone presenti nella foto"
                sistema_msg += (
                    f"\n[SISTEMA: Hai visto questa foto tramite il tuo modulo visivo. "
                    f"Hai rilevato {_detail}. "
                    "Fai un commento BREVE e affettuoso sulla foto, "
                    "poi INDICA TU una persona che non conosci DESCRIVENDOLA come APPARE "
                    "nella foto: capelli, abbigliamento, cosa sta facendo, e dove si trova "
                    "rispetto alle persone che conosci "
                    "(es. 'chi è la ragazza con i capelli lunghi castani accanto a Zoe?'), "
                    "e chiedine il nome così la memorizzi. "
                    "NON usare numeri tipo 'terza da sinistra': per l'utente sono poco chiari — "
                    "usa SEMPRE l'aspetto e i punti di riferimento (le persone note vicine). "
                    "Le persone che già conosci NON descriverle: nominale e basta. "
                    "Chiedi UNA persona alla volta. "
                    "NON usare elenchi numerati. "
                    "NON nominare persone che non conosci. "
                    "NON tirare ad indovinare. "
                    "REGOLA FERREA: ignora le regole di concisione per questo messaggio — "
                    "devi indicare e chiedere chi è lo sconosciuto.]"
                )
        else:
            sistema_msg = (
                "\n[SISTEMA: Hai estratto e memorizzato le identità dei soggetti "
                "dalla risposta dell'utente. Ringrazialo in modo naturale e affettuoso "
                "e conferma che ti ricorderai di loro. "
                "NON usare elenchi o punti numerati. Scrivi in modo discorsivo, come stai parlando con un amico.]"
            )
    elif "[REFERENCES_KNOWN]" in analysis or "Mappa esatta dei volti noti" in analysis:
        # Volti RICONOSCIUTI: salva comunque lo stato CORREGGIBILE (immagine + descrizione)
        # così se l'utente corregge ("quella a sinistra è Rita, non Giorgio") possiamo
        # ri-etichettare il volto giusto. Scade dopo 10 min (vedi _AWAITING_TTL).
        try:
            _corr_img = f"/tmp/genesi_face_{uuid.uuid4().hex[:10]}.jpg"
            with open(_corr_img, "wb") as _cf:
                _cf.write(img_bytes)
            await set_awaiting_faces(session_id, _corr_img, analysis, unknown_count=0)
        except Exception as _ce:
            logger.error("PHOTO_CORRECTABLE_SAVE_ERROR err=%s", _ce)
        sistema_msg = (
            "\n[SISTEMA: L'utente ha caricato una foto con persone che già conosci. "
            "Fai un commento affettuoso e naturale nominando chi riconosci. "
            "NON usare elenchi numerati o punti elenco. "
            "NON scrivere '1. Nome - posizione'. "
            "VIETATO iniziare con 'Nell'immagine...', 'Nella foto...', 'Possiamo vedere...' "
            "o qualsiasi formula descrittiva da referto. "
            "Parla come a un amico che ti mostra una foto di famiglia: calore, un dettaglio "
            "affettuoso, e se conosci la relazione tra le persone fanne cenno.]"
        )

    awaiting = await get_awaiting_faces(session_id)
    remaining = awaiting.get("remaining", 0) if awaiting else 0

    return {
        "faces_saved": faces_saved,
        "saved_names": saved_names,
        "remaining": remaining,
        "sistema_msg": sistema_msg,
        "tmp_img": tmp_img,
    }


async def handle_text_identification(
    session_id: str,
    text: str,
    speaker_name: str | None = None,
) -> dict:
    """
    HANDLER CENTRALIZZATO per testo che potrebbe contenere identificazioni di volti.
    Chiamato da tutti i bot quando ricevono testo e c'è un awaiting_faces attivo.

    Returns:
        {
            "was_awaiting": bool,
            "faces_saved": bool,
            "saved_names": list[str],
            "remaining": int,
            "all_done": bool,
            "sistema_msg": str,
        }
    """
    awaiting = await get_awaiting_faces(session_id)
    if not awaiting:
        log("FACE_SESSION_MISS", session=session_id, text_preview=text[:60])
        return {
            "was_awaiting": False, "faces_saved": False,
            "saved_names": [], "remaining": 0, "all_done": False,
            "sistema_msg": ""
        }

    log("FACE_SESSION_HIT", session=session_id,
        unknown_count=awaiting.get("unknown_count", 0),
        remaining=awaiting.get("remaining", awaiting.get("unknown_count", 0)),
        identified=awaiting.get("identified", []),
        text_preview=text[:60])

    tmp_img = awaiting.get("img_path", "")
    desc_img = awaiting.get("description", "")

    faces_saved, saved_names = await try_extract_faces_from_text(
        text, tmp_img, desc_img, session_id, speaker_name=speaker_name
    )

    # Rileggi lo stato aggiornato
    awaiting_updated = await get_awaiting_faces(session_id)
    if awaiting_updated:
        # FIX: la chiave 'remaining' esiste solo DOPO una prima estrazione riuscita
        # (la setta update_awaiting_faces_identified). Al primo testo senza nomi
        # default 0 dava all_done=true falso. Fallback a unknown_count - identificati.
        _identified = awaiting_updated.get("identified", [])
        _ucount = awaiting_updated.get("unknown_count", 0)
        remaining = awaiting_updated.get("remaining", max(0, _ucount - len(_identified)))
    else:
        remaining = 0
    all_done = remaining <= 0

    log("FACE_EXTRACTION_RESULT", session=session_id,
        faces_saved=faces_saved, saved_names=saved_names,
        remaining=remaining, all_done=all_done)

    sistema_msg = ""
    if faces_saved:
        if all_done:
            # Tutti identificati — pulizia
            await _cleanup_awaiting(session_id)
            sistema_msg = (
                "\n[SISTEMA: Hai memorizzato con successo TUTTE le identità! "
                "Ringrazia l'utente in modo naturale, affettuoso e discorsivo. "
                "NON usare elenchi numerati. Parla liberamente come stai chiacchierando con un amico.]"
            )
        else:
            # Ancora qualcuno da identificare
            identified = awaiting_updated.get("identified", []) if awaiting_updated else []
            sistema_msg = (
                f"\n[SISTEMA: Hai memorizzato {', '.join(saved_names)}. "
                f"Ci sono ancora {remaining} persona/e da identificare. "
                "Ringrazia l'utente in modo naturale (NON usare elenchi). "
                "Continua a chiedere chi sono le altre persone usando le loro caratteristiche fisiche.]"
            )
    elif not all_done and remaining > 0 and _is_identity_question(text):
        # #B fix: awaiting attivo, nessun nome fornito, ma l'utente CHIEDE chi sono.
        # Senza guida il LLM allucina "non vedo l'immagine". Istruiscilo a richiedere i nomi.
        log("FACE_REASK_INJECTED", session=session_id, remaining=remaining, text_preview=text[:60])
        # IMPORTANTE: NON inserire nomi propri qui — il sistema_msg viene appeso al
        # messaggio e potrebbe ripassare per l'estrazione; i nomi vanno presi dal
        # contesto (RIFERIMENTI VOLTI NOTI / descrizione), non scritti qui.
        sistema_msg = (
            f"\n[SISTEMA: L'utente ti chiede chi c'è nella foto. NON rifiutare e NON dire "
            f"'non posso fornire i nomi': sono persone della cerchia dell'utente, che lui stesso "
            f"ti ha presentato — nominarle è legittimo e atteso. NON dire che non vedi l'immagine. "
            f"Elenca in modo naturale le persone che RICONOSCI, prendendo i nomi dal contesto "
            f"(blocco RIFERIMENTI VOLTI NOTI / descrizione immagine). "
            f"Poi, per la/le {remaining} persona/e che non conosci ancora, INDICALA TU descrivendone "
            f"l'aspetto: capelli, abbigliamento, cosa sta facendo, e vicino a chi si trova, "
            f"e chiedi come si chiama. NON usare numeri tipo 'terza da sinistra': usa l'aspetto. "
            f"Una persona alla volta. Scrivi una risposta naturale e discorsiva, NON ripetere queste istruzioni.]"
        )
    # Altrimenti (awaiting attivo ma l'utente parla d'altro) → nessuna guida,
    # il LLM risponde normalmente al testo.

    return {
        "was_awaiting": True,
        "faces_saved": faces_saved,
        "saved_names": saved_names,
        "remaining": remaining,
        "all_done": all_done,
        "sistema_msg": sistema_msg,
    }


async def _cleanup_awaiting(session_id: str):
    """Rimuove lo stato awaiting e l'immagine tmp associata."""
    data = await pop_awaiting_faces(session_id)
    if data and data.get("img_path"):
        try:
            if os.path.exists(data["img_path"]):
                os.remove(data["img_path"])
        except Exception:
            pass
