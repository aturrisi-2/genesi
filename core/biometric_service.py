"""
Biometric face recognition — InsightFace ArcFace (buffalo_l).

Migrated from facenet_pytorch/VGGFace2 to InsightFace for superior robustness
across expressions, angles, and lighting conditions.

On first load:
  - Renames old VGGFace2 .pt/.npy files to .bak_v1 (incompatible embedding space)
  - Downloads buffalo_l models to ~/.insightface/models/ (~326 MB, one-time)

Storage: numpy array [N, 512] L2-normalized ArcFace embeddings in data/faces/<name>.npy
Threshold: 0.6 euclidean on L2-normalized vectors (≈ cosine similarity 0.82)
           Robust to expression/angle/lighting changes, unlike old VGGFace2 approach.
"""

import os
import cv2
import json
import logging
import numpy as np
from core.log import log

logger = logging.getLogger(__name__)

FACES_DIR = "data/faces"
_VERSION_FILE = os.path.join(FACES_DIR, ".model_version")
_CURRENT_VERSION = "v2_arcface"

_face_app = None


def _ensure_dir():
    os.makedirs(FACES_DIR, exist_ok=True)


def _migrate_old_embeddings():
    """Rename incompatible old embeddings (.pt VGGFace2) to .bak_v1 on first run."""
    if not os.path.exists(FACES_DIR):
        _ensure_dir()
        with open(_VERSION_FILE, "w") as f:
            f.write(_CURRENT_VERSION)
        return

    version = ""
    if os.path.exists(_VERSION_FILE):
        with open(_VERSION_FILE) as f:
            version = f.read().strip()
    if version == _CURRENT_VERSION:
        return

    renamed = 0
    for fname in os.listdir(FACES_DIR):
        if fname.endswith(".pt") or (fname.endswith(".npy") and fname != ".model_version"):
            old_path = os.path.join(FACES_DIR, fname)
            ext = ".pt" if fname.endswith(".pt") else ".npy"
            bak_path = os.path.join(FACES_DIR, fname[: -len(ext)] + f"{ext}.bak_v1")
            try:
                os.rename(old_path, bak_path)
                renamed += 1
            except Exception as e:
                logger.warning("MIGRATION_RENAME_ERROR file=%s err=%s", fname, e)

    if renamed:
        logger.info("BIOMETRIC_MIGRATED renamed=%d — re-register faces after VGGFace2→ArcFace upgrade", renamed)
        log("BIOMETRIC_MIGRATED", renamed=renamed)

    with open(_VERSION_FILE, "w") as f:
        f.write(_CURRENT_VERSION)


def get_face_models():
    global _face_app
    if _face_app is None:
        _ensure_dir()
        _migrate_old_embeddings()
        from insightface.app import FaceAnalysis
        _face_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _face_app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("INSIGHTFACE_LOADED model=buffalo_l providers=CPU")
    return _face_app


def _load_bgr(image_path: str) -> np.ndarray:
    """Load image as BGR numpy array for InsightFace."""
    img = cv2.imread(image_path)
    if img is None:
        from PIL import Image
        pil = Image.open(image_path).convert("RGB")
        img = np.array(pil)[:, :, ::-1].copy()
    return img


def _get_valid_faces(app, image_path: str, min_det_score: float = 0.5):
    """Detect faces, filter low-confidence detections and tiny background faces."""
    img = _load_bgr(image_path)
    all_faces = app.get(img)
    if not all_faces:
        return [], img

    faces = [f for f in all_faces if getattr(f, "det_score", 1.0) >= min_det_score]
    if not faces:
        return [], img

    areas = [(f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]) for f in faces]
    max_area = max(areas)
    faces = [f for f, a in zip(faces, areas) if a >= max_area * 0.05]

    return faces, img


async def compute_and_save_embeddings(name: str, image_path: str, description_hint: str = "") -> int:
    """
    Estrae il volto dall'immagine e salva l'embedding ArcFace (numpy .npy).
    Ritorna il numero di volti salvati (0 o 1).
    Ogni foto aggiuntiva della stessa persona aumenta la robustezza del riconoscimento.
    """
    try:
        _ensure_dir()
        app = get_face_models()
        faces, _ = _get_valid_faces(app, image_path)

        if not faces:
            return 0

        if len(faces) > 1:
            faces_sorted = sorted(faces, key=lambda f: (f.bbox[0] + f.bbox[2]) / 2)
            best_face = None

            if description_hint and "[INDEX:" in description_hint:
                try:
                    idx = int(description_hint.split("[INDEX:")[1].split("]")[0])
                    if idx < len(faces_sorted):
                        best_face = faces_sorted[idx]
                except Exception:
                    pass

            if best_face is None and description_hint:
                dl = description_hint.lower()
                if "sinistra" in dl:
                    best_face = faces_sorted[0]
                elif "destra" in dl:
                    best_face = faces_sorted[-1]
                elif "centro" in dl:
                    best_face = faces_sorted[len(faces_sorted) // 2]
                elif "alto" in dl:
                    best_face = sorted(faces, key=lambda f: (f.bbox[1] + f.bbox[3]) / 2)[0]
                elif "basso" in dl:
                    best_face = sorted(faces, key=lambda f: (f.bbox[1] + f.bbox[3]) / 2)[-1]

            if best_face is None:
                best_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

            faces = [best_face]

        emb_np = faces[0].embedding  # (512,) float32, già L2-normalizzato
        clean_name = name.strip().lower().replace(" ", "_")
        emb_path = os.path.join(FACES_DIR, f"{clean_name}.npy")

        if os.path.exists(emb_path):
            existing = np.load(emb_path)  # [N, 512] or (512,)
            if existing.ndim == 1:
                existing = existing[np.newaxis, :]
            emb_np = np.vstack([existing, emb_np[np.newaxis, :]])  # [N+1, 512]
        else:
            emb_np = emb_np[np.newaxis, :]  # [1, 512]

        np.save(emb_path, emb_np)
        logger.info("ARCFACE_EMBEDDING_SAVED name=%s total_samples=%d", name, emb_np.shape[0])
        return 1

    except Exception as e:
        logger.error("EMBEDDING_SAVE_ERROR name=%s err=%s", name, e)
        return 0


async def analyze_faces_biometric(image_path: str, threshold: float = 0.6) -> dict:
    """
    Riconosce i volti nell'immagine con ArcFace.

    threshold=0.6 (euclidean su vettori L2-normalizzati) ≈ cosine similarity 0.82.
    Robusto a: espressioni diverse, angolazioni, illuminazione, invecchiamento leggero.
    """
    empty = {
        "recognized_names": [],
        "recognized_faces_with_positions": [],
        "unknown_faces_detected": False,
        "unknown_faces_positions": [],
        "total_faces": 0,
    }
    try:
        app = get_face_models()
        faces, _ = _get_valid_faces(app, image_path)

        if not faces:
            return empty

        faces = sorted(faces, key=lambda f: (f.bbox[0] + f.bbox[2]) / 2)
        total_faces = len(faces)

        emb_new = np.stack([f.embedding for f in faces])  # [N, 512]

        # Carica tutti gli embedding noti
        known_faces_data = []
        for fname in os.listdir(FACES_DIR):
            if not fname.endswith(".npy"):
                continue
            clean_name = fname[:-4]
            fpath = os.path.join(FACES_DIR, fname)
            try:
                known_embs = np.load(fpath)  # [M, 512] or (512,)
                if known_embs.ndim == 1:
                    known_embs = known_embs[np.newaxis, :]
                display_name = clean_name
                json_path = os.path.join(FACES_DIR, f"{clean_name}.json")
                if os.path.exists(json_path):
                    with open(json_path, "r", encoding="utf-8") as jf:
                        display_name = json.load(jf).get("name", display_name)
                known_faces_data.append({"name": display_name, "embs": known_embs})
            except Exception as load_err:
                logger.warning("LOAD_EMB_ERROR file=%s err=%s", fname, load_err)

        # Greedy 1-to-1: abbina ogni viso nuovo al noto più vicino (se < threshold)
        distances = []
        for i in range(total_faces):
            for kf in known_faces_data:
                dists = np.linalg.norm(kf["embs"] - emb_new[i], axis=1)
                min_dist = float(dists.min())
                distances.append((min_dist, i, kf["name"]))
        distances.sort(key=lambda x: x[0])

        matched_face_indices: set = set()
        matched_identities: set = set()
        face_to_name: dict = {}
        face_to_confidence: dict = {}

        for dist, i, name in distances:
            if i not in matched_face_indices and name not in matched_identities:
                if dist < threshold:
                    matched_face_indices.add(i)
                    matched_identities.add(name)
                    face_to_name[i] = name
                    face_to_confidence[i] = round(max(0.0, 1.0 - dist / threshold), 3)

        recognized_names = set(face_to_name.values())
        unknown_faces_positions = []
        recognized_faces_list = []

        for i in range(total_faces):
            pos_str = f"{i + 1}° da sinistra"
            if i not in matched_face_indices:
                unknown_faces_positions.append(pos_str)
            else:
                conf = face_to_confidence.get(i, 0)
                recognized_faces_list.append(f"{face_to_name[i]} ({pos_str}, conf={conf:.2f})")

        result = {
            "recognized_names": list(recognized_names),
            "recognized_faces_with_positions": recognized_faces_list,
            "unknown_faces_detected": len(matched_face_indices) < total_faces,
            "unknown_faces_positions": unknown_faces_positions,
            "total_faces": total_faces,
        }
        log("BIOMETRIC_RESULT", names=str(list(recognized_names)),
            unknown=result["unknown_faces_detected"],
            positions=str(unknown_faces_positions), total=total_faces)
        return result

    except Exception as e:
        logger.error("BIOMETRIC_ANALYZE_ERROR err=%s", e)
        return empty
