"""
BIOMETRIC PETS SERVICE — Genesi Core
Riconoscimento biometrico animali domestici (cani, gatti, uccelli).
Pipeline parallela a biometric_service.py per umani.

- Detector: Faster R-CNN MobileNet V3 (COCO: Bird=16, Cat=17, Dog=18)
- Embedder: ResNet50 2048D, L2-normalized per cosine similarity
- Threshold: 0.75 (allineato agli umani, riduce falsi positivi)
- Storage: data/pets/{clean_name}.pt (embedding) + .json (metadati)
"""

import os
import json
import torch
import torchvision.transforms as T
import numpy as np
import logging
import time
from PIL import Image
from core.log import log

logger = logging.getLogger(__name__)

PETS_DIR = "data/pets"

# COCO labels per animali domestici
PET_CLASSES = {16: "uccello", 17: "gatto", 18: "cane"}

_detector = None
_embedder = None


def get_pet_models():
    global _detector, _embedder
    if _detector is None:
        import torchvision.models.detection as detection
        import torchvision.models as models
        import torch.nn as nn

        device = torch.device("cpu")

        _detector = detection.fasterrcnn_mobilenet_v3_large_fpn(
            weights=detection.FasterRCNN_MobileNet_V3_Large_FPN_Weights.DEFAULT
        ).eval().to(device)

        base_resnet = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
        _embedder = nn.Sequential(*list(base_resnet.children())[:-1]).eval().to(device)

    return _detector, _embedder


def _ensure_dir():
    if not os.path.exists(PETS_DIR):
        os.makedirs(PETS_DIR, exist_ok=True)


def detect_pets(img_pil: Image.Image, threshold: float = 0.6) -> list[dict]:
    """
    Rileva animali nell'immagine.

    Returns list of dicts: [{box, species, score}]
    - box: [x1, y1, x2, y2]
    - species: "cane" / "gatto" / "uccello"
    - score: detection confidence (0-1)
    """
    detector, _ = get_pet_models()
    transform = T.Compose([T.ToTensor()])
    img_t = transform(img_pil).unsqueeze(0)

    with torch.no_grad():
        predictions = detector(img_t)[0]

    boxes = predictions["boxes"].cpu().numpy()
    labels = predictions["labels"].cpu().numpy()
    scores = predictions["scores"].cpu().numpy()

    detections = []
    for i, label in enumerate(labels):
        if int(label) in PET_CLASSES and scores[i] >= threshold:
            detections.append({
                "box": boxes[i],
                "species": PET_CLASSES[int(label)],
                "score": float(scores[i]),
            })

    return detections


def extract_pet_embedding(img_pil: Image.Image, box) -> torch.Tensor:
    """Estrae embedding 2048D ResNet50 dal crop dell'animale."""
    _, embedder = get_pet_models()

    x1, y1, x2, y2 = box
    w, h = img_pil.size
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w, int(x2)), min(h, int(y2))

    crop = img_pil.crop((x1, y1, x2, y2))

    transform = T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    img_t = transform(crop).unsqueeze(0)

    with torch.no_grad():
        emb = embedder(img_t).squeeze()  # (2048,)

    emb = emb / emb.norm()  # L2 normalize
    return emb


async def compute_and_save_pet_embeddings(
    name: str,
    image_path: str,
    description_hint: str = "",
    species: str = "",
) -> int:
    """
    Rileva l'animale identificato per posizione, ne calcola l'embedding e lo salva.
    Salva sia .pt (embedding) che .json (metadati display).

    Returns: 1 se salvato, 0 se errore
    """
    try:
        _ensure_dir()
        img = Image.open(image_path).convert("RGB")

        detections = detect_pets(img)
        if not detections:
            logger.warning("PET_EMBED_NO_DETECTION name=%s path=%s", name, image_path)
            return 0

        # Filtra i box troppo piccoli (< 10% del massimo)
        areas = [(d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]) for d in detections]
        max_area = max(areas)
        detections = [d for d, a in zip(detections, areas) if a >= max_area * 0.10]

        if not detections:
            return 0

        # Ordina da sinistra a destra
        detections_sorted = sorted(detections, key=lambda d: (d["box"][0] + d["box"][2]) / 2)

        # Scegli per [INDEX:N] o prendi il più grande
        best_idx = None
        if description_hint and "[INDEX:" in description_hint:
            try:
                idx_str = description_hint.split("[INDEX:")[1].split("]")[0]
                target_idx = int(idx_str)
                if target_idx < len(detections_sorted):
                    best_idx = detections_sorted.index(detections_sorted[target_idx])
            except Exception:
                pass

        if best_idx is None:
            areas_sorted = [(d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]) for d in detections_sorted]
            best_idx = int(np.argmax(areas_sorted))

        best = detections_sorted[best_idx]
        embedding = extract_pet_embedding(img, best["box"])

        clean_name = name.strip().lower().replace(" ", "_")
        emb_path = os.path.join(PETS_DIR, f"{clean_name}.pt")
        json_path = os.path.join(PETS_DIR, f"{clean_name}.json")

        # Salva embedding (append se già esistente)
        embedding_2d = embedding.unsqueeze(0)  # [1, 2048]
        if os.path.exists(emb_path):
            existing = torch.load(emb_path, weights_only=True)
            if existing.dim() == 1:
                existing = existing.unsqueeze(0)
            new_embs = torch.cat((existing, embedding_2d), dim=0)
        else:
            new_embs = embedding_2d

        torch.save(new_embs, emb_path)

        # Salva metadati JSON (come save_known_face fa per gli umani)
        detected_species = best.get("species") or species or "animale"
        metadata = {
            "name": name.strip(),
            "species": detected_species,
            "description_in_image": description_hint or f"[INDEX:{best_idx}] {detected_species}",
            "ts": int(time.time()),
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info("PET_MEMORY_SAVED name=%s species=%s", name, detected_species)
        log("PET_MEMORY_SAVED", name=name, species=detected_species)
        return 1

    except Exception as e:
        logger.error("PET_EMBED_ERROR name=%s err=%s", name, e)
        return 0


async def analyze_pets_biometric(image_path: str, threshold: float = 0.75) -> dict:
    """
    Rileva e riconosce animali nell'immagine.

    Threshold 0.75 (allineato agli umani) per ridurre falsi positivi.
    Restituisce dict compatibile con analyze_faces_biometric.
    """
    _empty = {
        "recognized_names": [],
        "recognized_faces_with_positions": [],
        "unknown_faces_detected": False,
        "unknown_faces_positions": [],
        "total_faces": 0,
    }

    try:
        _ensure_dir()
        img = Image.open(image_path).convert("RGB")

        detections = detect_pets(img)
        if not detections:
            return _empty

        # Filtra troppo piccoli
        areas = [(d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]) for d in detections]
        max_area = max(areas)
        detections = [d for d, a in zip(detections, areas) if a >= max_area * 0.10]
        if not detections:
            return _empty

        # Ordina da sinistra a destra
        detections = sorted(detections, key=lambda d: (d["box"][0] + d["box"][2]) / 2)
        total_pets = len(detections)

        # Calcola embeddings per tutti gli animali rilevati
        embs_new = torch.stack([extract_pet_embedding(img, d["box"]) for d in detections])

        # Carica embeddings noti
        known_pets_data = []
        for f in os.listdir(PETS_DIR):
            if not f.endswith(".pt"):
                continue
            clean_name = f[:-3]
            try:
                known_embs = torch.load(os.path.join(PETS_DIR, f), weights_only=True)
                if known_embs.dim() == 1:
                    known_embs = known_embs.unsqueeze(0)

                display_name = clean_name.replace("_", " ").title()
                json_path = os.path.join(PETS_DIR, f"{clean_name}.json")
                if os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as jf:
                            data = json.load(jf)
                            display_name = data.get("name", display_name)
                    except Exception:
                        pass

                known_pets_data.append({"name": display_name, "embs": known_embs})
            except Exception as e:
                logger.debug("PET_LOAD_ERROR file=%s err=%s", f, e)

        # Soglia + margine effettivi (env-tunabili senza redeploy)
        try:
            _threshold = float(os.getenv("PET_MATCH_THRESHOLD", str(threshold)))
        except (TypeError, ValueError):
            _threshold = threshold
        try:
            _margin = float(os.getenv("PET_MATCH_MARGIN", "0.0"))
        except (TypeError, ValueError):
            _margin = 0.0
        try:
            _confident = float(os.getenv("PET_MATCH_CONFIDENT_DIST", "0.5"))
        except (TypeError, ValueError):
            _confident = 0.5

        # Matching greedy: distanza euclidea su embeddings normalizzati
        all_distances = []
        per_pet: dict[int, list] = {i: [] for i in range(total_pets)}
        for i in range(total_pets):
            for kp in known_pets_data:
                dists = (kp["embs"] - embs_new[i]).norm(dim=1)
                min_dist = float(dists.min().item())
                conf = round(1.0 - min_dist, 3)
                all_distances.append((min_dist, conf, i, kp["name"]))
                per_pet[i].append((min_dist, kp["name"]))

        for i in per_pet:
            per_pet[i].sort(key=lambda x: x[0])

        all_distances.sort(key=lambda x: x[0])

        matched_pet_indices = set()
        matched_identities = set()
        pet_to_name = {}
        pet_to_conf = {}

        for min_dist, conf, i, name in all_distances:
            if i not in matched_pet_indices and name not in matched_identities:
                if min_dist < _threshold:
                    _pf = per_pet.get(i, [])
                    _second = next((d for d, n in _pf if n != name), None)
                    if (_margin > 0.0 and min_dist >= _confident
                            and _second is not None and (_second - min_dist) < _margin):
                        log("PET_MATCH_AMBIGUOUS", pet_index=i, best=round(min_dist, 3),
                            best_name=name, second=round(_second, 3),
                            margin=_margin, confident=_confident)
                        continue
                    matched_pet_indices.add(i)
                    matched_identities.add(name)
                    pet_to_name[i] = name
                    pet_to_conf[i] = conf

        # Costruisci output con specie
        recognized_names = set()
        recognized_list = []
        unknown_positions = []

        for i, det in enumerate(detections):
            species = det.get("species", "animale")
            ordinal = f"{i + 1}°"
            pos_str = f"{species} {ordinal} da sinistra"

            if i in matched_pet_indices:
                name = pet_to_name[i]
                conf = pet_to_conf[i]
                recognized_list.append(f"{name} ({pos_str}, conf={conf})")
                recognized_names.add(name)
            else:
                unknown_positions.append(pos_str)

        unknown_detected = len(matched_pet_indices) < total_pets

        result = {
            "recognized_names": list(recognized_names),
            "recognized_faces_with_positions": recognized_list,
            "unknown_faces_detected": unknown_detected,
            "unknown_faces_positions": unknown_positions,
            "total_faces": total_pets,
            # Extra info per il vision prompt
            "species_counts": _count_species(detections),
        }

        log(
            "BIOMETRIC_PETS_RESULT",
            names=str(list(recognized_names)),
            unknown=unknown_detected,
            total=total_pets,
        )
        return result

    except Exception as e:
        logger.error("PET_BIOMETRIC_ERROR err=%s", e)
        return _empty


def _count_species(detections: list[dict]) -> dict:
    """Conta gli animali per specie. Es: {'gatto': 2, 'cane': 1}"""
    counts: dict[str, int] = {}
    for d in detections:
        s = d.get("species", "animale")
        counts[s] = counts.get(s, 0) + 1
    return counts
