# core/ocr/ocr_engine.py

import os
import tempfile
from pathlib import Path
from typing import Optional
import logging

try:
    import pdf2image
    import pytesseract
except ImportError as e:
    logging.error(f"OCR dependencies missing: {e}")
    raise ImportError("Install OCR dependencies: pip install pdf2image pytesseract")

# Import per OCR immagini
from .image_ocr import extract_text_from_image

logger = logging.getLogger(__name__)


def extract_text_with_ocr(file_path: str) -> str:
    """
    Dispatcher OCR: instrada al processore appropriato.
    
    Args:
        file_path: Percorso del file da processare
        
    Returns:
        Testo estratto o stringa vuota in caso di errore
        
    Supportati:
    - Immagini: jpg, jpeg, png, bmp, tiff (gestite da image_ocr)
    - PDF: scansionati (gestito internamente)
    """
    if not os.path.exists(file_path):
        logger.error(f"OCR[ENGINE]: File not found: {file_path}")
        return ""
    
    try:
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
            logger.info(f"OCR[ENGINE]: routing=image")
            return extract_text_from_image(file_path)
        elif file_ext == '.pdf':
            logger.info(f"OCR[ENGINE]: routing=pdf")
            return _extract_from_pdf(file_path)
        else:
            logger.warning(f"OCR[ENGINE]: Unsupported file type: {file_ext}")
            return ""
            
    except Exception as e:
        logger.error(f"OCR[ENGINE]: Extraction failed for {file_path}: {str(e)}")
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
                        lang='ita',
                        config='--psm 6'
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
