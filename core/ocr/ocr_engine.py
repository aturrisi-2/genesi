# core/ocr/ocr_engine.py

import os
import tempfile
from pathlib import Path
from typing import Optional
import logging

try:
    import pytesseract
    from PIL import Image
    import pdf2image
except ImportError as e:
    logging.error(f"OCR dependencies missing: {e}")
    raise ImportError("Install OCR dependencies: pip install pytesseract pillow pdf2image")

# Configurazione Tesseract per lingua italiana
TESSERACT_LANG = 'ita'
TESSERACT_CONFIG_BASE = '--psm 6'
TESSERACT_CONFIG_SCREENSHOT = '--psm 11'  # Migliore per screenshot e testo sparso

logger = logging.getLogger(__name__)


def extract_text_with_ocr(file_path: str) -> str:
    """
    Estrae testo grezzo da immagini o PDF scansionati usando Tesseract.
    
    Args:
        file_path: Percorso del file da processare
        
    Returns:
        Testo estratto o stringa vuota in caso di errore
        
    Supportati:
    - Immagini: jpg, jpeg, png, bmp, tiff
    - PDF: scansionati (tramite pdf2image)
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return ""
    
    try:
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
            return _extract_from_image(file_path)
        elif file_ext == '.pdf':
            return _extract_from_pdf(file_path)
        else:
            logger.warning(f"Unsupported file type: {file_ext}")
            return ""
            
    except Exception as e:
        logger.error(f"OCR extraction failed for {file_path}: {str(e)}")
        return ""


def _preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """
    Preprocessa l'immagine per migliorare l'OCR su screenshot.
    """
    # 1. Conversione in scala di grigi
    gray = img.convert('L')
    
    # 2. Aumento contrasto
    from PIL import ImageEnhance
    enhancer = ImageEnhance.Contrast(gray)
    contrasted = enhancer.enhance(2.0)
    
    # 3. Binarizzazione con threshold adattivo
    import numpy as np
    img_array = np.array(contrasted)
    
    # Calcola threshold locale (semplice ma efficace)
    threshold = np.mean(img_array) + np.std(img_array) * 0.5
    binary = np.where(img_array > threshold, 255, 0).astype(np.uint8)
    
    # 4. Ridimensionamento (2x per migliorare lettura testo piccolo)
    from PIL import Image
    binary_img = Image.fromarray(binary)
    width, height = binary_img.size
    resized = binary_img.resize((width * 2, height * 2), Image.Resampling.LANCZOS)
    
    return resized.convert('RGB')


def _extract_from_image(image_path: str) -> str:
    """
    Estrae testo da un'immagine singola con preprocessing migliorato per screenshot.
    """
    try:
        with Image.open(image_path) as img:
            # Converti in RGB per compatibilità
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # OCR base senza preprocessing
            text_base = pytesseract.image_to_string(
                img,
                lang=TESSERACT_LANG,
                config=TESSERACT_CONFIG_BASE
            )
            
            # OCR con preprocessing per screenshot
            try:
                preprocessed_img = _preprocess_image_for_ocr(img)
                text_preprocessed = pytesseract.image_to_string(
                    preprocessed_img,
                    lang=TESSERACT_LANG,
                    config=TESSERACT_CONFIG_SCREENSHOT
                )
                
                # Fallback intelligente: scegli la versione migliore
                base_alpha = sum(c.isalpha() for c in text_base)
                prep_alpha = sum(c.isalpha() for c in text_preprocessed)
                base_len = len(text_base.strip())
                prep_len = len(text_preprocessed.strip())
                
                # Scegli il preprocessato se ha più caratteri alfabetici o è più lungo
                if (prep_alpha > base_alpha) or (prep_len > base_len * 1.2):
                    logger.info(f"OCR: Using preprocessed version (alpha: {prep_alpha} vs {base_alpha}, len: {prep_len} vs {base_len})")
                    return text_preprocessed.strip()
                else:
                    logger.info(f"OCR: Using base version (alpha: {base_alpha} vs {prep_alpha}, len: {base_len} vs {prep_len})")
                    return text_base.strip()
                    
            except Exception as e:
                logger.warning(f"Preprocessed OCR failed, using base: {str(e)}")
                return text_base.strip()
            
    except Exception as e:
        logger.error(f"Failed to extract text from image {image_path}: {str(e)}")
        return ""


def _extract_from_pdf(pdf_path: str) -> str:
    """
    Estrae testo da PDF scansionato convertendo ogni pagina in immagine.
    """
    try:
        # Converti PDF in lista di immagini
        with tempfile.TemporaryDirectory() as temp_dir:
            images = pdf2image.convert_from_path(
                pdf_path,
                output_folder=temp_dir,
                fmt='jpg',
                dpi=200
            )
            
            all_text = []
            
            for i, image in enumerate(images):
                try:
                    # Estrai testo da ogni pagina
                    text = pytesseract.image_to_string(
                        image,
                        lang=TESSERACT_LANG,
                        config=TESSERACT_CONFIG_BASE
                    )
                    
                    if text.strip():
                        all_text.append(f"--- Pagina {i+1} ---\n{text.strip()}")
                    
                except Exception as e:
                    logger.warning(f"Failed to process page {i+1}: {str(e)}")
                    continue
            
            return "\n\n".join(all_text) if all_text else ""
            
    except Exception as e:
        logger.error(f"Failed to process PDF {pdf_path}: {str(e)}")
        return ""


def check_tesseract_available() -> bool:
    """
    Verifica se Tesseract è installato e funzionante.
    """
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception as e:
        logger.error(f"Tesseract not available: {str(e)}")
        return False


# Inizializzazione check
if not check_tesseract_available():
    logger.warning("Tesseract OCR not properly installed. OCR functionality will be limited.")
