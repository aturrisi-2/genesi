import os
import torch
import torchvision.transforms as T
import numpy as np
import logging
from PIL import Image
from core.log import log
import time
import json

logger = logging.getLogger(__name__)

PETS_DIR = "data/pets"
_detector = None
_embedder = None

# COCO labels per animali domestici (Bird=16, Cat=17, Dog=18)
PET_CLASSES = {16, 17, 18}

def get_pet_models():
    global _detector, _embedder
    if _detector is None:
        import torchvision.models.detection as detection
        import torchvision.models as models
        import torch.nn as nn
        
        device = torch.device('cpu')
        
        # Detector: Faster R-CNN (veloce e leggero per CPU)
        _detector = detection.fasterrcnn_mobilenet_v3_large_fpn(weights=detection.FasterRCNN_MobileNet_V3_Large_FPN_Weights.DEFAULT).eval().to(device)
        
        # Feature Extractor: ResNet50 senza layer finale
        base_resnet = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
        _embedder = nn.Sequential(*list(base_resnet.children())[:-1]).eval().to(device)
        
    return _detector, _embedder

def _ensure_dir():
    if not os.path.exists(PETS_DIR):
        os.makedirs(PETS_DIR, exist_ok=True)

def detect_pets(img_pil: Image.Image, threshold: float = 0.6) -> list:
    detector, _ = get_pet_models()
    transform = T.Compose([T.ToTensor()])
    img_t = transform(img_pil).unsqueeze(0)
    
    with torch.no_grad():
        predictions = detector(img_t)[0]
        
    boxes = predictions['boxes'].cpu().numpy()
    labels = predictions['labels'].cpu().numpy()
    scores = predictions['scores'].cpu().numpy()
    
    pet_boxes = []
    for i, label in enumerate(labels):
        if label in PET_CLASSES and scores[i] >= threshold:
            pet_boxes.append(boxes[i])
            
    return pet_boxes

def extract_pet_embedding(img_pil: Image.Image, box) -> torch.Tensor:
    _, embedder = get_pet_models()
    
    x1, y1, x2, y2 = box
    # Ritaglia in modo sicuro
    width, height = img_pil.size
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(width, int(x2)), min(height, int(y2))
    
    crop = img_pil.crop((x1, y1, x2, y2))
    
    # Preprocessing standard per ImageNet
    transform = T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    img_t = transform(crop).unsqueeze(0)
    
    with torch.no_grad():
        emb = embedder(img_t).squeeze() # shape (2048,)
        
    # Normalizza embedding per cosine similarity a distanza l2
    emb = emb / emb.norm()
    return emb

async def compute_and_save_pet_embeddings(name: str, image_path: str, description_hint: str = "") -> int:
    """
    Rileva animali, ne calcola l'embedding e salva.
    """
    try:
        _ensure_dir()
        img = Image.open(image_path).convert("RGB")
        
        boxes = detect_pets(img)
        if not boxes:
            return 0
            
        # Filtra i box piccoli
        areas = [(box[2]-box[0]) * (box[3]-box[1]) for box in boxes]
        max_area = max(areas)
        valid_indices = [i for i, area in enumerate(areas) if area >= max_area * 0.10]
        
        boxes = [boxes[i] for i in valid_indices]
        
        best_idx = None
        face_stats = []
        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = box
            face_stats.append({
                "idx": i,
                "cx": (x1 + x2) / 2,
                "cy": (y1 + y2) / 2
            })
            
        if description_hint and "[INDEX:" in description_hint:
            try:
                idx_str = description_hint.split("[INDEX:")[1].split("]")[0]
                target_idx = int(idx_str)
                sorted_faces = sorted(face_stats, key=lambda x: x["cx"])
                if target_idx < len(sorted_faces):
                    best_idx = sorted_faces[target_idx]["idx"]
            except Exception:
                pass
                
        if best_idx is None:
            areas = [(box[2]-box[0]) * (box[3]-box[1]) for box in boxes]
            best_idx = int(np.argmax(areas))
            
        target_box = boxes[best_idx]
        embedding = extract_pet_embedding(img, target_box)
        
        clean_name = name.strip().lower().replace(" ", "_")
        emb_path = os.path.join(PETS_DIR, f"{clean_name}.pt")
        
        # Salviamo la shape [1, 2048]
        embedding = embedding.unsqueeze(0)
        
        if os.path.exists(emb_path):
            existing = torch.load(emb_path, weights_only=True)
            new_embs = torch.cat((existing, embedding), dim=0)
        else:
            new_embs = embedding
            
        torch.save(new_embs, emb_path)
        return 1
    except Exception as e:
        logger.error("Error computing pet embeddings: %s", e)
        return 0

async def analyze_pets_biometric(image_path: str, threshold: float = 0.70) -> dict:
    """
    Rileva e riconosce animali nell'immagine.
    Restituisce dict simile ai volti umani.
    """
    try:
        _ensure_dir()
        img = Image.open(image_path).convert("RGB")
        
        boxes = detect_pets(img)
        if not boxes:
            return {
                "recognized_names": [],
                "recognized_faces_with_positions": [],
                "unknown_faces_detected": False,
                "unknown_faces_positions": [],
                "total_faces": 0
            }
            
        areas = [(box[2]-box[0]) * (box[3]-box[1]) for box in boxes]
        max_area = max(areas)
        min_allowed_area = max_area * 0.10
        valid_indices = [i for i, area in enumerate(areas) if area >= min_allowed_area]
        
        filtered_boxes = [boxes[i] for i in valid_indices]
        if not filtered_boxes:
            return {
                "recognized_names": [],
                "recognized_faces_with_positions": [],
                "unknown_faces_detected": False,
                "unknown_faces_positions": [],
                "total_faces": 0
            }
            
        # Ordina per X crescente
        boxes_with_idx = []
        for i, box in enumerate(filtered_boxes):
            cx = (box[0] + box[2]) / 2
            boxes_with_idx.append((cx, i))
            
        boxes_with_idx.sort(key=lambda x: x[0])
        sorted_indices = [item[1] for item in boxes_with_idx]
        boxes = [filtered_boxes[i] for i in sorted_indices]
        
        total_pets = len(boxes)
        
        embs_new = []
        for box in boxes:
            embs_new.append(extract_pet_embedding(img, box))
        embs_new = torch.stack(embs_new) # [total_pets, 2048]
        
        known_pets_data = []
        for f in os.listdir(PETS_DIR):
            if f.endswith(".pt"):
                clean_name = f[:-3]
                try:
                    known_embs = torch.load(os.path.join(PETS_DIR, f), weights_only=True)
                    if known_embs.dim() == 1:
                        known_embs = known_embs.unsqueeze(0)
                        
                    display_name = clean_name
                    json_path = os.path.join(PETS_DIR, f"{clean_name}.json")
                    if os.path.exists(json_path):
                        with open(json_path, "r", encoding="utf-8") as jf:
                            data = json.load(jf)
                            display_name = data.get("name", display_name)
                            
                    known_pets_data.append({
                        "name": display_name,
                        "embs": known_embs
                    })
                except Exception as e:
                    pass

        recognized_names = set()
        matched_indices = set()
        face_to_name = {}
        
        distances = []
        for i in range(total_pets):
            for kp in known_pets_data:
                # Distanza euclidea tra embeddings normalizzati (vicino a cosine)
                dists = (kp["embs"] - embs_new[i]).norm(dim=1)
                min_dist = dists.min().item()
                distances.append((min_dist, i, kp["name"]))
                
        distances.sort(key=lambda x: x[0])
        
        matched_identities = set()
        for min_dist, i, name in distances:
            if i not in matched_indices and name not in matched_identities:
                if min_dist < threshold:
                    matched_indices.add(i)
                    matched_identities.add(name)
                    face_to_name[i] = name
                    recognized_names.add(name)

        unknown_pets_detected = len(matched_indices) < total_pets
        unknown_pets_positions = []
        recognized_list = []
        
        for i in range(total_pets):
            pos_str = f"animale {i+1}° da sinistra"
            if i not in matched_indices:
                unknown_pets_positions.append(pos_str)
            else:
                recognized_list.append(f"{face_to_name[i]} ({pos_str})")
                
        result = {
            "recognized_names": list(recognized_names),
            "recognized_faces_with_positions": recognized_list,
            "unknown_faces_detected": unknown_pets_detected,
            "unknown_faces_positions": unknown_pets_positions,
            "total_faces": total_pets
        }
        log("BIOMETRIC_PETS_RESULT", names=str(list(recognized_names)), unknown=unknown_pets_detected, total=total_pets)
        return result
    except Exception as e:
        logger.error("Error analyzing pets: %s", e)
        return {
            "recognized_names": [],
            "recognized_faces_with_positions": [],
            "unknown_faces_detected": False,
            "unknown_faces_positions": [],
            "total_faces": 0
        }
