import os
import torch
import logging
from PIL import Image
import numpy as np
from core.log import log

logger = logging.getLogger(__name__)

_mtcnn = None
_resnet = None

FACES_DIR = "data/faces"


def _face_match_threshold(default: float = 0.75) -> float:
    """Soglia distanza L2 per il match biometrico. Tunabile via env senza redeploy.
    Default = valore passato dal chiamante (storico 0.75). Env FACE_MATCH_THRESHOLD
    lo sovrascrive. Più BASSA = più severo (meno falsi positivi)."""
    try:
        return float(os.getenv("FACE_MATCH_THRESHOLD", str(default)))
    except (TypeError, ValueError):
        return default


def _face_match_margin() -> float:
    """Margine anti-ambiguità (ratio test). Se il miglior match e il secondo
    miglior match (identità diversa) distano MENO di questo margine, il volto è
    ambiguo → lasciato 'sconosciuto' invece di rischiare un nome sbagliato
    (es. Ennio↔Giorgio). Default 0.0 = disattivato (comportamento storico).
    Alza via env FACE_MATCH_MARGIN (es. 0.08) per ridurre i falsi positivi."""
    try:
        return float(os.getenv("FACE_MATCH_MARGIN", "0.0"))
    except (TypeError, ValueError):
        return 0.0


def _face_confident_dist() -> float:
    """Soglia di 'match sicuro': sotto questa distanza il ratio-test (margin) NON
    si applica. Serve perché embedding duplicati della stessa persona danno
    second-best≈best≈0 (gap nullo): senza questo floor il margin scarterebbe per
    errore match certissimi (es. Zoe/Ennio a best=0.000). Solo la 'banda incerta'
    (best ≥ floor) è soggetta al ratio-test. Tunabile via FACE_MATCH_CONFIDENT_DIST."""
    try:
        return float(os.getenv("FACE_MATCH_CONFIDENT_DIST", "0.5"))
    except (TypeError, ValueError):
        return 0.5

def get_face_models():
    global _mtcnn, _resnet
    if _mtcnn is None:
        from facenet_pytorch import MTCNN, InceptionResnetV1
        # Forza CPU per VPS
        device = torch.device('cpu')
        _mtcnn = MTCNN(keep_all=True, device=device)
        _resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)
    return _mtcnn, _resnet

def _ensure_dir():
    if not os.path.exists(FACES_DIR):
        os.makedirs(FACES_DIR, exist_ok=True)

async def compute_and_save_embeddings(name: str, image_path: str, description_hint: str = "") -> int:
    """
    Estrae i volti dall'immagine e ne salva gli embedding per il riconoscimento.
    Ritorna il numero di volti salvati.
    """
    try:
        _ensure_dir()
        mtcnn, resnet = get_face_models()
        img = Image.open(image_path).convert("RGB")
        
        # Estrae i volti (tensors)
        boxes, _ = mtcnn.detect(img)
        faces = mtcnn(img)
        if faces is None or len(faces) == 0 or boxes is None:
            return 0
            
        # Filtra i volti di background (area < 5% del più grande) per non confonderli con pose/sfondi
        areas = [(box[2]-box[0]) * (box[3]-box[1]) for box in boxes]
        max_area = max(areas)
        valid_indices = [i for i, area in enumerate(areas) if area >= max_area * 0.05]
        
        boxes = [boxes[i] for i in valid_indices]
        faces = faces[valid_indices]
            
        # Se ci sono più volti, usa l'indizio spaziale o salva SOLO quello più grande
        if len(faces) > 1:
            best_idx = None
            
            # Lista di (indice_originale, cx, cy, area)
            face_stats = []
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = box
                face_stats.append({
                    "idx": i,
                    "cx": (x1 + x2) / 2,
                    "cy": (y1 + y2) / 2,
                    "area": (x2 - x1) * (y2 - y1)
                })
                
            if description_hint and "[INDEX:" in description_hint:
                try:
                    idx_str = description_hint.split("[INDEX:")[1].split("]")[0]
                    target_idx = int(idx_str)
                    
                    # Ordina da sinistra a destra (cx crescente)
                    sorted_faces = sorted(face_stats, key=lambda x: x["cx"])
                    if target_idx < len(sorted_faces):
                        best_idx = sorted_faces[target_idx]["idx"]
                except Exception as e:
                    logger.warning("Error parsing INDEX from description_hint: %s", e)
            
            if best_idx is None and description_hint:
                desc_lower = description_hint.lower()
                if "sinistra" in desc_lower:
                    best_idx = sorted(face_stats, key=lambda x: x["cx"])[0]["idx"]
                elif "destra" in desc_lower:
                    best_idx = sorted(face_stats, key=lambda x: x["cx"], reverse=True)[0]["idx"]
                elif "alto" in desc_lower:
                    best_idx = sorted(face_stats, key=lambda x: x["cy"])[0]["idx"]
                elif "basso" in desc_lower:
                    best_idx = sorted(face_stats, key=lambda x: x["cy"], reverse=True)[0]["idx"]
                elif "centro" in desc_lower:
                    width, height = img.size
                    img_cx, img_cy = width / 2, height / 2
                    best_idx = sorted(face_stats, key=lambda x: (x["cx"] - img_cx)**2 + (x["cy"] - img_cy)**2)[0]["idx"]
            
            if best_idx is None:
                areas = [(box[2]-box[0]) * (box[3]-box[1]) for box in boxes]
                best_idx = int(np.argmax(areas))
                
            faces = faces[best_idx:best_idx+1]
            
        # Calcola gli embeddings: [1, 512]
        with torch.no_grad():
            embeddings = resnet(faces).detach().cpu()
            
        clean_name = name.strip().lower().replace(" ", "_")
        emb_path = os.path.join(FACES_DIR, f"{clean_name}.pt")
        
        if os.path.exists(emb_path):
            existing = torch.load(emb_path, weights_only=True)
            new_embs = torch.cat((existing, embeddings), dim=0)
        else:
            new_embs = embeddings
            
        torch.save(new_embs, emb_path)
        return len(faces)
    except Exception as e:
        logger.error("Error computing face embeddings: %s", e)
        return 0

async def analyze_faces_biometric(image_path: str, threshold: float = 0.75) -> dict:
    """
    Analizza i volti presenti nell'immagine.
    Ritorna un dizionario:
    {
        "recognized_names": ["Zoe", "Rita"],
        "unknown_faces_detected": bool,
        "total_faces": int
    }
    """
    try:
        mtcnn, resnet = get_face_models()
        img = Image.open(image_path).convert("RGB")
        
        # Detect bboxes + PROBABILITÀ di confidenza (servono per scartare i falsi volti)
        boxes, probs = mtcnn.detect(img)
        faces = mtcnn(img)

        if faces is None or len(faces) == 0 or boxes is None:
            return {
                "recognized_names": [],
                "unknown_faces_detected": False,
                "unknown_faces_positions": [],
                "total_faces": 0
            }

        # Filtro 1: CONFIDENZA — scarta i rilevamenti incerti (pattern, cibo, sfondo,
        # riflessi) che MTCNN segnala come "volti" → evita di contare persone inesistenti
        # e di chiedere "chi è a destra/sinistra" per facce che non ci sono.
        FACE_CONF_MIN = 0.93
        if probs is None:
            probs = [1.0] * len(boxes)
        # Filtro 2: AREA — niente volti minuscoli (almeno il 6% del volto più grande)
        areas = [(box[2]-box[0]) * (box[3]-box[1]) for box in boxes]
        max_area = max(areas)
        min_allowed_area = max_area * 0.06

        valid_indices = [
            i for i, area in enumerate(areas)
            if area >= min_allowed_area
            and (probs[i] is not None and float(probs[i]) >= FACE_CONF_MIN)
        ]
        
        if not valid_indices:
            return {
                "recognized_names": [],
                "unknown_faces_detected": False,
                "unknown_faces_positions": [],
                "total_faces": 0
            }
            
        filtered_boxes = [boxes[i] for i in valid_indices]
        filtered_faces = faces[valid_indices]
        
        # Ordina da sinistra a destra in base alla coordinata X centrale
        boxes_with_idx = []
        for i, box in enumerate(filtered_boxes):
            cx = (box[0] + box[2]) / 2
            boxes_with_idx.append((cx, i))
            
        boxes_with_idx.sort(key=lambda x: x[0])
        sorted_indices = [item[1] for item in boxes_with_idx]
        
        boxes = [filtered_boxes[i] for i in sorted_indices]
        faces = filtered_faces[sorted_indices]
        
        total_faces = len(faces)
        
        with torch.no_grad():
            emb_new = resnet(faces).detach().cpu() # shape [total_faces, 512]
            
        recognized_names = set()
        matched_face_indices = set()
        
        # Carica tutti gli embedding noti una sola volta
        known_faces_data = []
        for f in os.listdir(FACES_DIR):
            if f.endswith(".pt"):
                clean_name = f[:-3]
                try:
                    known_embs = torch.load(os.path.join(FACES_DIR, f), weights_only=True)
                    if known_embs.dim() == 1:
                        known_embs = known_embs.unsqueeze(0)
                        
                    display_name = clean_name
                    json_path = os.path.join(FACES_DIR, f"{clean_name}.json")
                    if os.path.exists(json_path):
                        import json
                        with open(json_path, "r", encoding="utf-8") as jf:
                            data = json.load(jf)
                            display_name = data.get("name", display_name)
                            
                    known_faces_data.append({
                        "name": display_name,
                        "embs": known_embs
                    })
                except Exception as load_err:
                    logger.warning("Failed to load embeddings for %s: %s", f, load_err)

        # Soglia + margine effettivi (env-tunabili senza redeploy)
        _threshold = _face_match_threshold(threshold)
        _margin = _face_match_margin()
        _confident = _face_confident_dist()

        # Per ogni volto nuovo, trova la corrispondenza MIGLIORE assoluta con vincolo 1-a-1
        distances = []
        # per_face[i] = lista (dist, name) ordinata, per il ratio-test anti-ambiguità
        per_face: dict[int, list] = {i: [] for i in range(total_faces)}
        for i in range(total_faces):
            for kf in known_faces_data:
                dists = (kf["embs"] - emb_new[i]).norm(dim=1)
                min_dist = dists.min().item()
                distances.append((min_dist, i, kf["name"]))
                per_face[i].append((min_dist, kf["name"]))

        for i in per_face:
            per_face[i].sort(key=lambda x: x[0])

        distances.sort(key=lambda x: x[0])

        matched_identities = set()
        face_to_name = {}
        face_to_confidence = {}  # Confidence score per ogni match

        for min_dist, i, name in distances:
            if i not in matched_face_indices and name not in matched_identities:
                if min_dist < _threshold:
                    # Ratio-test: se esiste un'altra identità quasi alla stessa distanza,
                    # il match è ambiguo → NON assegnare (meglio "sconosciuto" che sbagliato)
                    _pf = per_face.get(i, [])
                    _second = next((d for d, n in _pf if n != name), None)
                    # Ratio-test SOLO nella banda incerta (best ≥ floor): i match
                    # certi (best < floor) bypassano → embedding duplicati salvi.
                    if (_margin > 0.0 and min_dist >= _confident
                            and _second is not None and (_second - min_dist) < _margin):
                        log("FACE_MATCH_AMBIGUOUS", face_index=i, best=round(min_dist, 3),
                            best_name=name, second=round(_second, 3),
                            margin=_margin, confident=_confident, decision="skip")
                        continue
                    matched_face_indices.add(i)
                    matched_identities.add(name)
                    face_to_name[i] = name
                    face_to_confidence[i] = round(1.0 - min_dist, 3)  # più alto = più sicuro
                    recognized_names.add(name)
                    log("FACE_MATCH_DECISION", face_index=i, name=name,
                        best=round(min_dist, 3),
                        second=round(_second, 3) if _second is not None else None,
                        threshold=_threshold)

        unknown_faces_detected = len(matched_face_indices) < total_faces
        unknown_faces_positions = []
        recognized_faces_list = []
        
        if boxes is not None:
            width, height = img.size
            for i in range(total_faces):
                box = boxes[i]
                x1, y1, x2, y2 = box
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                
                # Visto che abbiamo già ordinato i volti per X crescente, l'indice `i` rappresenta esattamente l'ordine da sinistra a destra.
                pos_str = f"{i+1}° da sinistra"
                    
                if i not in matched_face_indices:
                    unknown_faces_positions.append(pos_str)
                else:
                    conf = face_to_confidence.get(i, 0)
                    recognized_faces_list.append(f"{face_to_name[i]} ({pos_str}, conf={conf:.2f})")
        
        result = {
            "recognized_names": list(recognized_names),
            "recognized_faces_with_positions": recognized_faces_list,
            "unknown_faces_detected": unknown_faces_detected,
            "unknown_faces_positions": unknown_faces_positions,
            "total_faces": total_faces
        }
        log("BIOMETRIC_RESULT", names=str(list(recognized_names)), unknown=unknown_faces_detected, positions=str(unknown_faces_positions), total=total_faces)
        return result
    except Exception as e:
        logger.error("Error analyzing faces: %s", e)
        return {
            "recognized_names": [],
            "unknown_faces_detected": False, # Fallback prudente
            "unknown_faces_positions": [],
            "total_faces": 0
        }
