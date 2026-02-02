# core/ocr/ocr_engine.py

import os
import tempfile
from pathlib import Path
from typing import Optional
import logging

try:
    import pdf2image
    import pytesseract
    OCR_AVAILABLE = True
    
    # Configure Tesseract path for Windows
    if os.name == 'nt':
        tesseract_path = r"C:\Users\TURRISIA\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            logging.info(f"OCR Engine: Configured Tesseract path: {tesseract_path}")
        else:
            logging.warning("OCR Engine: Tesseract not found at expected path")
            
        # Configure Poppler path for Windows
        poppler_path = r"C:\Users\TURRISIA\AppData\Local\Microsoft\WinGet\packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin"
        if os.path.exists(poppler_path):
            os.environ['PATH'] = os.environ.get('PATH', '') + os.pathsep + poppler_path
            logging.info(f"OCR Engine: Configured Poppler path: {poppler_path}")
        else:
            logging.warning("OCR Engine: Poppler not found at expected path")
    else:
        # For non-Windows, ensure tesseract is in PATH
        try:
            pytesseract.get_tesseract_version()
            logging.info("OCR Engine: Tesseract found in PATH")
        except Exception as e:
            logging.warning(f"OCR Engine: Tesseract not found in PATH: {e}")
    
except ImportError as e:
    logging.error(f"OCR dependencies missing: {e}")
    OCR_AVAILABLE = False

# Import per OCR immagini
from .image_ocr import extract_text_from_image
from .image_classifier import classify_image_for_ocr

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
    if not OCR_AVAILABLE:
        logger.warning("OCR[ENGINE]: OCR dependencies not available")
        return ""
    
    if not os.path.exists(file_path):
        logger.error(f"OCR[ENGINE]: File not found: {file_path}")
        return ""
    
    try:
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
            # Classifica l'immagine PRIMA di fare OCR
            classification = classify_image_for_ocr(file_path)
            
            logger.info(
                f"OCR[ENGINE]: routing=image kind={classification['image_kind']} confidence={classification['confidence']} text_density={classification['signals']['estimated_text_density']}"
            )
            
            # Nuova logica: esegui OCR se c'è testo rilevato sopra soglia minima
            text_density = classification['signals']['estimated_text_density']
            min_text_threshold = 0.15  # Soglia minima per considerare testo presente
            
            if text_density >= min_text_threshold:
                logger.info(f"OCR[ENGINE]: text_detected={text_density:.3f} >= threshold={min_text_threshold} -> executing OCR")
                return extract_text_from_image(file_path)
            else:
                logger.info(f"OCR[ENGINE]: text_detected={text_density:.3f} < threshold={min_text_threshold} -> skipping OCR (pure image)")
                return ""
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
                        lang='eng',
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
    if not OCR_AVAILABLE:
        return False
    
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception as e:
        logger.error(f"Tesseract not available: {str(e)}")
        return False


# Inizializzazione check
if not check_tesseract_available():
    logger.warning("Tesseract OCR not properly installed. OCR functionality will be limited.")
