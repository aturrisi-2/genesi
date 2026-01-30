# core/ocr/image_ocr.py

import os
import logging
from pathlib import Path
from typing import Tuple

try:
    import pytesseract
    from PIL import Image, ImageEnhance
    import numpy as np
except ImportError as e:
    logging.error(f"Image OCR dependencies missing: {e}")
    raise ImportError("Install image OCR dependencies: pip install pytesseract pillow numpy")

# Configurazione Tesseract per immagini
TESSERACT_LANG = 'ita'
TESSERACT_CONFIG_BASE = '--psm 6'
TESSERACT_CONFIG_SCREENSHOT = '--psm 11'

logger = logging.getLogger(__name__)


def extract_text_from_image(image_path: str) -> str:
    """
    Estrae testo da un'immagine con preprocessing multi-pass.
    
    Args:
        image_path: Percorso del file immagine
        
    Returns:
        Testo estratto o stringa vuota
    """
    if not os.path.exists(image_path):
        logger.error(f"OCR[IMAGE]: File not found: {image_path}")
        return ""
    
    try:
        with Image.open(image_path) as img:
            # Converti in RGB per compatibilità
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # OCR base
            text_base = _ocr_base(img)
            
            # OCR preprocessato
            text_preprocessed = _ocr_preprocessed(img)
            
            # Scelta deterministica del risultato migliore
            selected_text = _select_best_ocr(text_base, text_preprocessed)
            
            return selected_text
            
    except Exception as e:
        logger.error(f"OCR[IMAGE]: Failed to process {image_path}: {str(e)}")
        return ""


def _ocr_base(img: Image.Image) -> str:
    """OCR base senza preprocessing."""
    try:
        text = pytesseract.image_to_string(
            img,
            lang=TESSERACT_LANG,
            config=TESSERACT_CONFIG_BASE
        )
        return text.strip()
    except Exception as e:
        logger.warning(f"OCR[IMAGE]: Base OCR failed: {str(e)}")
        return ""


def _ocr_preprocessed(img: Image.Image) -> str:
    """OCR con preprocessing per screenshot."""
    try:
        preprocessed_img = _preprocess_image_for_ocr(img)
        text = pytesseract.image_to_string(
            preprocessed_img,
            lang=TESSERACT_LANG,
            config=TESSERACT_CONFIG_SCREENSHOT
        )
        return text.strip()
    except Exception as e:
        logger.warning(f"OCR[IMAGE]: Preprocessed OCR failed: {str(e)}")
        return ""


def _preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """
    Preprocessa l'immagine per migliorare l'OCR su screenshot.
    """
    # 1. Conversione in scala di grigi
    gray = img.convert('L')
    
    # 2. Aumento contrasto
    enhancer = ImageEnhance.Contrast(gray)
    contrasted = enhancer.enhance(2.0)
    
    # 3. Binarizzazione con threshold adattivo
    img_array = np.array(contrasted)
    
    # Calcola threshold locale (deterministico)
    threshold = np.mean(img_array) + np.std(img_array) * 0.5
    binary = np.where(img_array > threshold, 255, 0).astype(np.uint8)
    
    # 4. Ridimensionamento (2x per migliorare lettura testo piccolo)
    binary_img = Image.fromarray(binary)
    width, height = binary_img.size
    resized = binary_img.resize((width * 2, height * 2), Image.Resampling.LANCZOS)
    
    return resized.convert('RGB')


def _select_best_ocr(text_base: str, text_preprocessed: str) -> str:
    """
    Scelta deterministica del risultato OCR migliore.
    """
    base_len = len(text_base.strip())
    prep_len = len(text_preprocessed.strip())
    base_alpha = sum(c.isalpha() for c in text_base)
    prep_alpha = sum(c.isalpha() for c in text_preprocessed)
    
    # Metriche deterministiche
    base_score = _calculate_ocr_score(text_base)
    prep_score = _calculate_ocr_score(text_preprocessed)
    
    logger.info(f"OCR[IMAGE]: base_len={base_len}, base_alpha={base_alpha}, base_score={base_score}")
    logger.info(f"OCR[IMAGE]: prep_len={prep_len}, prep_alpha={prep_alpha}, prep_score={prep_score}")
    
    # Scelta deterministica: usa il punteggio più alto
    if prep_score > base_score:
        logger.info(f"OCR[IMAGE]: selected=preprocessed")
        return text_preprocessed
    else:
        logger.info(f"OCR[IMAGE]: selected=base")
        return text_base


def _calculate_ocr_score(text: str) -> float:
    """
    Calcola un punteggio deterministico per la qualità OCR.
    """
    if not text.strip():
        return 0.0
    
    # Punteggio basato su metriche testuali deterministiche
    length_score = len(text.strip())
    alpha_score = sum(c.isalpha() for c in text) * 2.0  # Peso maggiore per caratteri alfabetici
    word_score = len(text.split()) * 1.5
    
    # Bonus per pattern comuni in italiano
    common_patterns = ['il', 'la', 'lo', 'un', 'una', 'che', 'con', 'per', 'del', 'della']
    pattern_bonus = sum(text.lower().count(pattern) for pattern in common_patterns) * 3.0
    
    return length_score + alpha_score + word_score + pattern_bonus
