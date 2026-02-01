# core/ocr/image_classifier.py

import os
import logging
from pathlib import Path
from typing import Dict, Tuple
import math

try:
    from PIL import Image, ImageStat
    CLASSIFIER_AVAILABLE = True
except ImportError as e:
    logging.error(f"Image classifier dependencies missing: {e}")
    CLASSIFIER_AVAILABLE = False

# Limiti di sicurezza per resize deterministico
MAX_IMAGE_PIXELS_SAFE = 100_000_000
TARGET_MAX_EDGE = 4096

logger = logging.getLogger(__name__)


def safe_open_image(path):
    """
    Apre un'immagine in modo sicuro, ridimensionandola
    PRIMA che Pillow sollevi decompression bomb errors.
    """
    if not CLASSIFIER_AVAILABLE:
        logger.warning("IMAGE_CLASSIFIER: dependencies not available")
        return None
        
    img = Image.open(path)
    w, h = img.size
    pixels = w * h

    if pixels <= MAX_IMAGE_PIXELS_SAFE and max(w, h) <= TARGET_MAX_EDGE:
        logger.info(f"IMAGE_CLASSIFIER: image safe {w}x{h}")
        return img

    scale = min(
        math.sqrt(MAX_IMAGE_PIXELS_SAFE / pixels),
        TARGET_MAX_EDGE / max(w, h)
    )

    new_w = int(w * scale)
    new_h = int(h * scale)

    logger.warning(
        f"IMAGE_CLASSIFIER: resizing image {w}x{h} → {new_w}x{new_h}"
    )

    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def classify_image_for_ocr(image_path: str) -> Dict:
    """
    Classifica un'immagine per determinare la strategia OCR appropriata.
    
    Args:
        image_path: Percorso del file immagine
        
    Returns:
        Dizionario con classificazione e segnali analitici:
        {
            "image_kind": "text-heavy" | "ui-screenshot" | "pure-image",
            "confidence": "high" | "medium" | "low", 
            "signals": {
                "resolution": "...",
                "aspect_ratio": "...",
                "estimated_text_density": float,
                "color_variance": float
            }
        }
    """
    if not os.path.exists(image_path):
        logger.error(f"Image classifier: File not found: {image_path}")
        return _get_default_classification()
    
    if not CLASSIFIER_AVAILABLE:
        logger.warning("Image classifier: dependencies not available")
        return _get_default_classification()
    
    try:
        img = safe_open_image(image_path)
        if img is None:
            logger.warning("IMAGE_CLASSIFIER: safe_open_image returned None")
            return _get_default_classification()
            
        logger.info("IMAGE_CLASSIFIER: image opened via safe_open_image")
        
        # Converti in RGB per analisi consistente
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Analisi base
        width, height = img.size
        resolution = f"{width}x{height}"
        aspect_ratio = f"{width/height:.2f}"
        
        # Calcola segnali
        color_variance = _calculate_color_variance(img)
        text_density = _estimate_text_density(img, width, height)
        brightness_distribution = _analyze_brightness_distribution(img)
        structural_signals = _detect_structural_patterns(img, width, height)
        
        # Classificazione
        image_kind, confidence = _classify_image_type(
            width, height, aspect_ratio, color_variance, 
            text_density, brightness_distribution, structural_signals
        )
        
        logger.debug(f"Image classifier: {image_path} -> {image_kind} ({confidence})")
        
        return {
            "image_kind": image_kind,
            "confidence": confidence,
            "signals": {
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "estimated_text_density": text_density,
                "color_variance": color_variance
            }
        }
        
    except Exception as e:
        logger.error(f"Image classifier failed for {image_path}: {str(e)}")
        return _get_default_classification()


def _calculate_color_variance(img):
    """Calcola la varianza dei colori nell'immagine."""
    try:
        stat = ImageStat.Stat(img)
        # Varianza media sui canali RGB
        variance = sum(stat.var) / len(stat.var)
        return variance
    except Exception:
        return 0.0


def _estimate_text_density(img, width: int, height: int) -> float:
    """
    Stima la densità di testo basandosi su segnali visivi.
    Valore tra 0.0 (nessun testo) e 1.0 (tutto testo).
    """
    try:
        # Converti in scala di grigi per analisi
        gray = img.convert('L')
        
        # Calcola edge detection semplice
        pixels = list(gray.getdata())
        
        # Conta transizioni brusche (indicative di testo)
        transitions = 0
        for i in range(1, len(pixels)):
            if abs(pixels[i] - pixels[i-1]) > 30:
                transitions += 1
        
        # Normalizza per dimensione immagine
        total_pixels = width * height
        density = min(transitions / total_pixels * 1000, 1.0)  # Cap a 1.0
        
        return density
        
    except Exception:
        return 0.0


def _analyze_brightness_distribution(img) -> dict:
    """Analizza la distribuzione della luminosità."""
    try:
        gray = img.convert('L')
        stat = ImageStat.Stat(gray)
        
        mean_brightness = stat.mean[0]
        std_brightness = stat.stddev[0]
        
        # Percentuale pixel chiari/scuri
        pixels = list(gray.getdata())
        light_pixels = sum(1 for p in pixels if p > 200)
        dark_pixels = sum(1 for p in pixels if p < 55)
        total_pixels = len(pixels)
        
        light_ratio = light_pixels / total_pixels
        dark_ratio = dark_pixels / total_pixels
        
        return {
            "mean": mean_brightness,
            "std": std_brightness,
            "light_ratio": light_ratio,
            "dark_ratio": dark_ratio
        }
        
    except Exception:
        return {"mean": 128, "std": 50, "light_ratio": 0.3, "dark_ratio": 0.3}


def _detect_structural_patterns(img, width: int, height: int) -> Dict:
    """Rileva pattern strutturali tipici di UI/documenti."""
    try:
        gray = img.convert('L')
        pixels = list(gray.getdata())
        
        # Rileva linee orizzontali
        horizontal_lines = 0
        for y in range(height):
            row_start = y * width
            row = pixels[row_start:row_start + width]
            
            # Conta segmenti uniformi (linee)
            uniform_segments = 0
            current_segment_length = 0
            
            for i in range(1, len(row)):
                if abs(row[i] - row[i-1]) < 10:
                    current_segment_length += 1
                else:
                    if current_segment_length > width * 0.3:  # Segmento lungo
                        uniform_segments += 1
                    current_segment_length = 0
            
            if uniform_segments > 2:
                horizontal_lines += 1
        
        # Rileva linee verticali (campionamento)
        vertical_lines = 0
        for x in range(0, width, 10):  # Campiona ogni 10 pixel
            column = [pixels[y * width + x] for y in range(height)]
            
            uniform_segments = 0
            current_segment_length = 0
            
            for i in range(1, len(column)):
                if abs(column[i] - column[i-1]) < 10:
                    current_segment_length += 1
                else:
                    if current_segment_length > height * 0.2:
                        uniform_segments += 1
                    current_segment_length = 0
            
            if uniform_segments > 1:
                vertical_lines += 1
        
        return {
            "horizontal_lines": horizontal_lines,
            "vertical_lines": vertical_lines,
            "has_grid_structure": horizontal_lines > 5 and vertical_lines > 3
        }
        
    except Exception:
        return {"horizontal_lines": 0, "vertical_lines": 0, "has_grid_structure": False}


def _classify_image_type(
    width: int, height: int, aspect_ratio: str, color_variance: float,
    text_density: float, brightness: Dict, structure: Dict
) -> Tuple[str, str]:
    """
    Classifica il tipo di immagine basandosi su tutti i segnali.
    
    Returns:
        Tuple[image_kind, confidence]
    """
    # Euristiche per TEXT-HEAVY
    text_heavy_score = 0
    if color_variance < 1000:  # Bassa varianza colore
        text_heavy_score += 2
    if text_density > 0.3:  # Alta densità di transizioni
        text_heavy_score += 2
    if brightness["light_ratio"] > 0.6:  # Sfondo chiaro
        text_heavy_score += 1
    if float(aspect_ratio) in [0.71, 0.77, 1.41]:  # Aspect ratio tipici documenti
        text_heavy_score += 1
    
    # Euristiche per UI-SCREENSHOT
    ui_score = 0
    if width >= 1200 and height >= 700:  # Risoluzione tipica schermo
        ui_score += 2
    if structure["has_grid_structure"]:
        ui_score += 2
    if structure["horizontal_lines"] > 5:
        ui_score += 1
    if 500 < color_variance < 5000:  # Varianza media
        ui_score += 1
    
    # Euristiche per PURE-IMAGE
    pure_score = 0
    if color_variance > 3000:  # Alta varianza colore
        pure_score += 2
    if text_density < 0.1:  # Bassa densità testo
        pure_score += 2
    if brightness["std"] > 80:  # Alta varianza luminosità
        pure_score += 1
    
    # Decisione
    scores = {
        "text-heavy": text_heavy_score,
        "ui-screenshot": ui_score,
        "pure-image": pure_score
    }
    
    best_kind = max(scores, key=scores.get)
    best_score = scores[best_kind]
    
    # Calcola confidenza
    if best_score >= 4:
        confidence = "high"
    elif best_score >= 2:
        confidence = "medium"
    else:
        confidence = "low"
    
    return best_kind, confidence


def _get_default_classification() -> Dict:
    """Classificazione di default per errori."""
    return {
        "image_kind": "pure-image",
        "confidence": "low",
        "signals": {
            "resolution": "unknown",
            "aspect_ratio": "0.00",
            "estimated_text_density": 0.0,
            "color_variance": 0.0
        }
    }
