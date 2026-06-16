"""
IMAGE VISION SERVICE - Genesi Core v4
Descrizione immagini via GPT-4o vision.
Primario: OpenRouter (quota separata). Fallback: OpenAI diretto.
Descrive FEDELMENTE ogni soggetto con caratteristiche fisiche utili all'identificazione.
"""

import base64
import logging
import os
from openai import AsyncOpenAI
from core.log import log

logger = logging.getLogger(__name__)

# MIME types supportati per vision
_VISION_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def _get_mime(path: str) -> str:
    """Get MIME type from file path."""
    ext = os.path.splitext(path)[1].lower()
    return _VISION_MIME.get(ext, "image/png")


# Singleton clients — creati una sola volta al caricamento del modulo
_VISION_CLIENTS: list | None = None


def _get_vision_clients() -> list:
    """
    Ritorna lista di (AsyncOpenAI client, label) in ordine di priorità.
    OpenRouter primo (billing separato da OpenAI), poi OpenAI diretto.
    I client sono singleton: creati una sola volta e riutilizzati.
    """
    global _VISION_CLIENTS
    if _VISION_CLIENTS is not None:
        return _VISION_CLIENTS

    clients = []
    or_key = os.environ.get("OPENROUTER_API_KEY")
    oa_key = os.environ.get("OPENAI_API_KEY")
    if or_key:
        clients.append((
            AsyncOpenAI(
                api_key=or_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={"HTTP-Referer": "https://genesi.app", "X-Title": "Genesi"},
            ),
            "openrouter",
        ))
    if oa_key:
        clients.append((AsyncOpenAI(api_key=oa_key), "openai"))
    if not clients:
        clients.append((AsyncOpenAI(), "openai_default"))

    _VISION_CLIENTS = clients
    return clients


async def describe_image(path: str) -> str:
    """
    Describe image content using GPT-4o vision.
    Tries OpenRouter first, falls back to OpenAI direct.
    Returns rich, faithful description with physical descriptors for unknown subjects.

    Args:
        path: Absolute path to image file

    Returns:
        Description string with [UNKNOWN_FACES_DETECTED] / [UNKNOWN_PETS_DETECTED] tags if needed
    """
    log("IMAGE_VISION_START", path=path)

    # Read and encode image once
    with open(path, "rb") as f:
        image_data = f.read()

    mime = _get_mime(path)
    b64 = base64.b64encode(image_data).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"

    system_prompt = (
        "Sei l'occhio di un'AI conversazionale familiare. Analizza l'immagine e restituisci ESCLUSIVAMENTE un JSON con le seguenti chiavi:\n"
        "'description': descrizione PRECISA E DETTAGLIATA di OGNI soggetto presente (persone, animali). "
        "PER OGNI PERSONA SCONOSCIUTA: colore capelli, abbigliamento, espressione, posizione nella foto. "
        "PER OGNI ANIMALE SCONOSCIUTO: specie (cane/gatto/uccello), colore e pattern del pelo (es. 'tigrato grigio', "
        "'pelo nero con petto bianco', 'manto dorato'), markings distintivi (macchie, colore orecchie, segni particolari), "
        "taglia (piccolo/medio/grande), posizione nella foto. "
        "ESEMPIO animale: 'un gatto di taglia media, pelo tigrato grigio e bianco, con macchia bianca sul muso, a sinistra'. "
        "PER OGNI SOGGETTO NOTO (persona o animale già identificato nei riferimenti): cita SOLO il nome, "
        "ed eventualmente l'espressione/stato d'animo o cosa sta facendo, per un'interazione naturale. "
        "NON indicare la posizione e NON descrivere l'aspetto fisico dei soggetti NOTI. "
        "La POSIZIONE ESATTA nella foto e la descrizione fisica vanno date SOLO per i soggetti SCONOSCIUTI "
        "(persone o animali non identificati), per permettere all'utente di riconoscerli e salvarli. "
        "NON inventare nomi. NON indovinare chi siano i soggetti sconosciuti.\n"
        "'gender_hints': array di oggetti con 'position' (numero intero 0=primo da sinistra) e 'gender' (M o F) per ogni persona umana. "
        "Es: [{\"position\": 0, \"gender\": \"F\"}, {\"position\": 1, \"gender\": \"M\"}].\n"
        "'unknown_faces_detected': true se c'è ALMENO UNA persona umana NON presente nei riferimenti forniti.\n"
        "'unknown_pets_detected': true se c'è ALMENO UN animale domestico NON presente nei riferimenti forniti.\n"
        "'total_humans': numero intero di persone umane visibili nell'immagine.\n"
        "'total_pets': numero intero di animali domestici visibili nell'immagine.\n"
        "Formato OBBLIGATORIO: {\"description\": \"...\", \"gender_hints\": [...], "
        "\"unknown_faces_detected\": false, \"unknown_pets_detected\": false, "
        "\"total_humans\": 0, \"total_pets\": 0}. Nessun altro testo al di fuori del JSON."
    )

    content_array = []

    # Risultati biometrici (volti umani + animali)
    recognized_names = []
    recognized_faces_list = []
    unknown_faces_detected = False
    unknown_faces_positions = []
    unknown_pets_detected = False
    unknown_pets_positions = []
    bio_total_faces = 0
    bio_total_pets = 0

    try:
        from core.biometric_service import analyze_faces_biometric
        bio_result = await analyze_faces_biometric(path)
        recognized_names = bio_result.get("recognized_names", [])
        recognized_faces_list = bio_result.get("recognized_faces_with_positions", [])
        unknown_faces_detected = bio_result.get("unknown_faces_detected", False)
        unknown_faces_positions = bio_result.get("unknown_faces_positions", [])
        bio_total_faces = bio_result.get("total_faces", 0)

        try:
            from core.biometric_pets_service import analyze_pets_biometric
            pet_result = await analyze_pets_biometric(path)
            pet_names = pet_result.get("recognized_names", [])
            recognized_names.extend(pet_names)
            recognized_faces_list.extend(pet_result.get("recognized_faces_with_positions", []))
            unknown_pets_detected = pet_result.get("unknown_faces_detected", False)
            unknown_pets_positions = pet_result.get("unknown_faces_positions", [])
            bio_total_pets = pet_result.get("total_faces", 0)
        except Exception as e:
            logger.error("Error running biometric pets service: %s", e)

        # ── Inietta riferimenti volti noti ──────────────────────────────────────
        if recognized_faces_list:
            names_str = " | ".join(recognized_faces_list)
            content_array.append({
                "type": "text",
                "text": (
                    f"SOGGETTI NOTI (già identificati dal sistema biometrico): {names_str}. "
                    "REGOLA: cita TUTTI questi nomi nella 'description', senza ometterne nessuno. "
                    "NON aggiungere la loro posizione ('1° da sinistra') né descriverne l'aspetto fisico: "
                    "sono già noti. Interagisci con la scena in modo naturale (espressione, attività, contesto). "
                    "La posizione esatta serve SOLO per gli eventuali soggetti SCONOSCIUTI."
                )
            })

        # ── Volti sconosciuti ───────────────────────────────────────────────────
        unknown_count = bio_total_faces - len([n for n in recognized_names if n])
        if unknown_faces_detected:
            pos_str = ", ".join(unknown_faces_positions) if unknown_faces_positions else "posizione non determinata"
            content_array.append({
                "type": "text",
                "text": (
                    f"ATTENZIONE: Il sistema biometrico ha rilevato {max(unknown_count, len(unknown_faces_positions))} "
                    f"persona/e SCONOSCIUTA/E all'immagine (posizioni: {pos_str}). "
                    "DEVI impostare 'unknown_faces_detected' a true. "
                    "Nella 'description', descrivi OGNI persona sconosciuta con: "
                    "colore capelli, tipo di abbigliamento, posizione relativa (es. 'la donna con capelli biondi e maglia blu a sinistra'). "
                    "Questo è fondamentale per permettere all'utente di identificarle."
                )
            })
        elif bio_total_faces > 0 and not unknown_faces_detected:
            content_array.append({
                "type": "text",
                "text": "Tutte le persone presenti sono state identificate. Imposta 'unknown_faces_detected' a false."
            })

        # ── Animali sconosciuti ─────────────────────────────────────────────────
        if unknown_pets_detected:
            pos_str = ", ".join(unknown_pets_positions) if unknown_pets_positions else "posizione non determinata"
            # Includi info specie dal biometrico se disponibile
            species_counts = pet_result.get("species_counts", {})
            species_hint = ""
            if species_counts:
                parts = [f"{v} {k}" for k, v in species_counts.items()]
                species_hint = f" Il sensore biometrico ha rilevato: {', '.join(parts)}."
            content_array.append({
                "type": "text",
                "text": (
                    f"ATTENZIONE: Sono presenti animali domestici SCONOSCIUTI (posizioni: {pos_str}).{species_hint} "
                    "DEVI impostare 'unknown_pets_detected' a true. "
                    "Nella 'description', descrivi OGNI animale SCONOSCIUTO con queste caratteristiche OBBLIGATORIE: "
                    "1) specie (cane/gatto/uccello), "
                    "2) colore e pattern del pelo (es. 'tigrato grigio e bianco', 'manto nero con petto bianco', 'pelo beige tinta unita'), "
                    "3) markings distintivi (macchie, strisce, colore delle orecchie/zampe, eventuali segni particolari), "
                    "4) taglia approssimativa (piccolo/medio/grande), "
                    "5) posizione nella foto. "
                    "Queste descrizioni permettono all'utente di riconoscere QUALE dei suoi animali è nella foto."
                )
            })

        log(
            "VISION_PROMPT_INJECTED",
            names=str(recognized_names),
            unknown=unknown_faces_detected,
            unknown_pets=unknown_pets_detected,
            total_humans=bio_total_faces,
            total_pets=bio_total_pets,
        )
    except Exception as e:
        logger.error("Error running biometric service: %s", e)

    content_array.append({
        "type": "text",
        "text": "Analizza questa immagine e rispondi SOLO con il JSON richiesto:"
    })
    content_array.append({"type": "image_url", "image_url": {"url": data_url, "detail": "high"}})

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content_array},
    ]

    clients = _get_vision_clients()
    last_error = None

    for client, provider in clients:
        try:
            log("IMAGE_VISION_TRY", provider=provider)
            model_name = "openai/gpt-4o" if provider == "openrouter" else "gpt-4o"
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=1200,
            )
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("Empty content from vision model")

            content_str = response.choices[0].message.content.strip()
            log("VISION_RAW_OUTPUT", provider=provider, content=content_str[:300])

            # Rifiuto del modello (content policy sui volti): trattalo come
            # fallimento provider → si tenta il successivo. Mai usarlo come descrizione.
            _refusal_markers = (
                "i'm sorry", "i am sorry", "i can't assist", "i cannot assist",
                "i can't help", "non posso aiutarti", "non posso assisterti",
                "non posso fornire assistenza",
            )
            if len(content_str) < 150 and any(m in content_str.lower() for m in _refusal_markers):
                log("IMAGE_VISION_REFUSAL", provider=provider)
                last_error = ValueError(f"vision refusal from {provider}")
                continue

            # Pulisci eventuali backtick markdown
            clean_json_str = content_str
            if clean_json_str.startswith("```json"):
                clean_json_str = clean_json_str[7:]
            if clean_json_str.startswith("```"):
                clean_json_str = clean_json_str[3:]
            if clean_json_str.endswith("```"):
                clean_json_str = clean_json_str[:-3]
            clean_json_str = clean_json_str.strip()

            import json
            try:
                parsed = json.loads(clean_json_str)
            except json.JSONDecodeError:
                parsed = {
                    "description": content_str,
                    "unknown_faces_detected": "unknown_faces_detected" in content_str.lower() and "true" in content_str.lower(),
                    "unknown_pets_detected": "unknown_pets_detected" in content_str.lower() and "true" in content_str.lower(),
                    "total_humans": bio_total_faces,
                    "total_pets": bio_total_pets,
                }

            description = parsed.get("description", "")

            # Forza i flag sconosciuti dal biometrico se il LLM li avesse ignorati
            is_unknown_faces = parsed.get("unknown_faces_detected")
            if unknown_faces_detected:
                is_unknown_faces = True
            if is_unknown_faces and str(is_unknown_faces).lower() in ("true", "1", "yes", "si", "sì"):
                description += " [UNKNOWN_FACES_DETECTED]"

            is_unknown_pets = parsed.get("unknown_pets_detected")
            if unknown_pets_detected:
                is_unknown_pets = True
            if is_unknown_pets and str(is_unknown_pets).lower() in ("true", "1", "yes", "si", "sì"):
                description += " [UNKNOWN_PETS_DETECTED]"

            # Aggiungi conteggio soggetti al description per il LLM a valle
            total_humans = parsed.get("total_humans", bio_total_faces)
            total_pets = parsed.get("total_pets", bio_total_pets)
            if total_humans and total_humans > 0:
                description += f" [TOTAL_HUMANS:{total_humans}]"
            if total_pets and total_pets > 0:
                description += f" [TOTAL_PETS:{total_pets}]"

            # Conteggio REALE degli sconosciuti, dal biometrico (affidabile).
            # Serve a valle (face_memory_service) per chiedere/indicare SOLO i
            # soggetti realmente sconosciuti, non tutti.
            # NB: NON iniettiamo le posizioni numeriche ('N° da sinistra') del
            # biometrico: l'ordinamento per bbox non coincide con come l'utente
            # conta le persone (file multiple, facce sfondo) → confonde. Genesi
            # indica gli sconosciuti per ASPETTO, usando la descrizione del vision.
            if is_unknown_faces and str(is_unknown_faces).lower() in ("true", "1", "yes", "si", "sì"):
                _n_unk_h = len(unknown_faces_positions) if unknown_faces_positions else max(
                    0, bio_total_faces - len(recognized_faces_list)
                )
                if _n_unk_h > 0:
                    description += f" [UNKNOWN_HUMANS:{_n_unk_h}]"
            if is_unknown_pets and str(is_unknown_pets).lower() in ("true", "1", "yes", "si", "sì"):
                _n_unk_p = len(unknown_pets_positions) if unknown_pets_positions else max(0, bio_total_pets)
                if _n_unk_p > 0:
                    description += f" [UNKNOWN_PETS:{_n_unk_p}]"

            # Inietta gender_hints nel description per downstream
            gender_hints = parsed.get("gender_hints", [])
            if not isinstance(gender_hints, list):
                gender_hints = []
            if gender_hints:
                hints_str = " | ".join(
                    f"{'M' if h.get('gender') == 'M' else 'F'} a {h.get('position', '?')}"
                    for h in gender_hints
                )
                description += f" [GENDER_VISUAL_HINTS: {hints_str}]"

            log(
                "IMAGE_VISION_OK",
                provider=provider,
                chars=len(description),
                gender_hints_count=len(gender_hints),
                total_humans=total_humans,
                total_pets=total_pets,
            )
            return {
                "description": description,
                "gender_hints": gender_hints,
                "unknown_faces": bool(is_unknown_faces and str(is_unknown_faces).lower() in ("true", "1", "yes", "si", "sì")),
                "unknown_pets": bool(is_unknown_pets and str(is_unknown_pets).lower() in ("true", "1", "yes", "si", "sì")),
                "total_humans": total_humans,
                "total_pets": total_pets,
            }
        except Exception as e:
            logger.warning("IMAGE_VISION_PROVIDER_FAILED provider=%s error=%s", provider, str(e))
            log("IMAGE_VISION_PROVIDER_FAILED", provider=provider, error=str(e)[:120])
            last_error = e
            continue

    # Tutti i provider hanno fallito o rifiutato.
    # Se il biometrico ha comunque riconosciuto qualcosa, costruisci una
    # descrizione dai suoi dati: il riconoscimento resta funzionante anche
    # quando il modello vision rifiuta l'analisi.
    if recognized_faces_list or bio_total_faces > 0 or bio_total_pets > 0:
        parts = []
        if recognized_faces_list:
            parts.append("Soggetti riconosciuti dal sistema biometrico: "
                         + " | ".join(recognized_faces_list) + ".")
        if unknown_faces_detected:
            pos = ", ".join(unknown_faces_positions) or "posizione non determinata"
            parts.append(f"Presenti anche persone non riconosciute ({pos}).")
        if unknown_pets_detected:
            pos = ", ".join(unknown_pets_positions) or "posizione non determinata"
            parts.append(f"Presenti animali non riconosciuti ({pos}).")
        description = " ".join(parts) or "Immagine ricevuta."
        if unknown_faces_detected:
            description += " [UNKNOWN_FACES_DETECTED]"
            _n_unk_h = len(unknown_faces_positions) if unknown_faces_positions else max(
                0, bio_total_faces - len(recognized_faces_list))
            if _n_unk_h > 0:
                description += f" [UNKNOWN_HUMANS:{_n_unk_h}]"
        if unknown_pets_detected:
            description += " [UNKNOWN_PETS_DETECTED]"
            _n_unk_p = len(unknown_pets_positions) if unknown_pets_positions else max(0, bio_total_pets)
            if _n_unk_p > 0:
                description += f" [UNKNOWN_PETS:{_n_unk_p}]"
        if bio_total_faces:
            description += f" [TOTAL_HUMANS:{bio_total_faces}]"
        if bio_total_pets:
            description += f" [TOTAL_PETS:{bio_total_pets}]"
        log("IMAGE_VISION_BIOMETRIC_FALLBACK", chars=len(description),
            total_humans=bio_total_faces, total_pets=bio_total_pets)
        return {
            "description": description,
            "gender_hints": [],
            "unknown_faces": unknown_faces_detected,
            "unknown_pets": unknown_pets_detected,
            "total_humans": bio_total_faces,
            "total_pets": bio_total_pets,
        }

    logger.error("IMAGE_VISION_ERROR error=%s", str(last_error), exc_info=True)
    log("IMAGE_VISION_ERROR", error=str(last_error))
    raise RuntimeError(f"Vision analysis failed: {str(last_error)}")
