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
            
        # Filtra i volti di background (area < 15% del più grande) per non confonderli con le pose
        areas = [(box[2]-box[0]) * (box[3]-box[1]) for box in boxes]
        max_area = max(areas)
        valid_indices = [i for i, area in enumerate(areas) if area >= max_area * 0.15]
        
        boxes = [boxes[i] for i in valid_indices]
        faces = faces[valid_indices]
            
        # Se ci sono più volti, usa l'indizio spaziale o salva SOLO quello più grande
        if len(faces) > 1:
            best_idx = None
            if description_hint:
                desc_lower = description_hint.lower()
                
                # Lista di (indice, cx, cy, area)
                face_stats = []
                for i, box in enumerate(boxes):
                    x1, y1, x2, y2 = box
                    face_stats.append({
                        "idx": i,
                        "cx": (x1 + x2) / 2,
                        "cy": (y1 + y2) / 2,
                        "area": (x2 - x1) * (y2 - y1)
                    })
                    
                if "sinistra" in desc_lower:
                    # Ordina per cx crescente (il primo è il più a sinistra)
                    best_idx = sorted(face_stats, key=lambda x: x["cx"])[0]["idx"]
                elif "destra" in desc_lower:
                    # Ordina per cx decrescente (il primo è il più a destra)
                    best_idx = sorted(face_stats, key=lambda x: x["cx"], reverse=True)[0]["idx"]
                elif "alto" in desc_lower:
                    # cy crescente (0 è in alto)
                    best_idx = sorted(face_stats, key=lambda x: x["cy"])[0]["idx"]
                elif "basso" in desc_lower:
                    # cy decrescente
                    best_idx = sorted(face_stats, key=lambda x: x["cy"], reverse=True)[0]["idx"]
                elif "centro" in desc_lower:
                    # Ordina per distanza dal centro immagine
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

async def analyze_faces_biometric(image_path: str, threshold: float = 0.8) -> dict:
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
        
        # Detect bboxes just to count exactly, though mtcnn() does both
        boxes, _ = mtcnn.detect(img)
        faces = mtcnn(img)
        
        if faces is None or len(faces) == 0 or boxes is None:
            return {
                "recognized_names": [],
                "unknown_faces_detected": False,
                "unknown_faces_positions": [],
                "total_faces": 0
            }
            
        # Filtra i volti di background: tieni solo quelli la cui area è almeno il 15% del volto più grande
        areas = [(box[2]-box[0]) * (box[3]-box[1]) for box in boxes]
        max_area = max(areas)
        min_allowed_area = max_area * 0.15
        
        valid_indices = [i for i, area in enumerate(areas) if area >= min_allowed_area]
        
        if not valid_indices:
            return {
                "recognized_names": [],
                "unknown_faces_detected": False,
                "unknown_faces_positions": [],
                "total_faces": 0
            }
            
        boxes = [boxes[i] for i in valid_indices]
        faces = faces[valid_indices]
        
        total_faces = len(faces)
        
        with torch.no_grad():
            emb_new = resnet(faces).detach().cpu() # shape [total_faces, 512]
            
        recognized_names = set()
        matched_face_indices = set()
        
        # Confronta ogni volto trovato con il database
        for f in os.listdir(FACES_DIR):
            if f.endswith(".pt"):
                clean_name = f[:-3]
                try:
                    known_embs = torch.load(os.path.join(FACES_DIR, f), weights_only=True) # [num_known, 512] o [512]
                    if known_embs.dim() == 1:
                        known_embs = known_embs.unsqueeze(0)
                        
                    # Ripristina il nome originale cercandolo dal json (se esiste)
                    display_name = clean_name
                    json_path = os.path.join(FACES_DIR, f"{clean_name}.json")
                    if os.path.exists(json_path):
                        import json
                        with open(json_path, "r", encoding="utf-8") as jf:
                            data = json.load(jf)
                            display_name = data.get("name", display_name)
                    
                    # Per ogni volto nuovo, calcola distanza con tutti i volti noti di questo utente
                    for i in range(total_faces):
                        # L2 distance
                        dists = (known_embs - emb_new[i]).norm(dim=1)
                        min_dist = dists.min().item()
                        if min_dist < threshold:
                            recognized_names.add(display_name)
                            matched_face_indices.add(i)
                except Exception as load_err:
                    logger.warning("Failed to load embeddings for %s: %s", f, load_err)

        unknown_faces_detected = len(matched_face_indices) < total_faces
        unknown_faces_positions = []
        
        if unknown_faces_detected and boxes is not None:
            width, height = img.size
            for i in range(total_faces):
                if i not in matched_face_indices:
                    box = boxes[i]
                    x1, y1, x2, y2 = box
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    
                    pos_x = "a sinistra" if cx < width * 0.4 else ("a destra" if cx > width * 0.6 else "al centro")
                    pos_y = "in alto" if cy < height * 0.4 else ("in basso" if cy > height * 0.6 else "")
                    
                    if pos_y and pos_x != "al centro":
                        pos_str = f"{pos_y} {pos_x}"
                    elif pos_y and pos_x == "al centro":
                        pos_str = pos_y
                    else:
                        pos_str = pos_x
                        
                    unknown_faces_positions.append(pos_str)
        
        result = {
            "recognized_names": list(recognized_names),
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
