"""
SETUP WIZARD - Genesi Core v2 (OpenClaw Automation)
Flusso conversazionale automatizzato gestito interamente da OpenClaw.
"""

import os
from typing import Any, Dict, Optional
from core.storage import storage
from core.openclaw_service import openclaw_service

WIZARD_PLATFORMS = {"facebook", "instagram", "tiktok", "telegram"}

async def start_wizard(user_id: str, platform: str) -> str:
    """
    Avvia il setup automatizzato tramite OpenClaw.
    Costruisce un prompt ad-hoc per il setup della piattaforma e delega all'agente.
    """
    prompt = (
        f"L'utente vuole configurare l'integrazione con {platform}. "
        "Esegui un flusso automatizzato: apri il browser, naviga nel portale per sviluppatori appropriato "
        "(es. developers.facebook.com per Facebook/Instagram, developers.tiktok.com per TikTok, o usa Telegram web for @BotFather). "
        "Esegui tutte le operazioni necessarie per creare/configurare l'app o il bot e recuperare le credenziali. "
        "REGOLE FONDAMENTALI DI COMUNICAZIONE (MOLTO IMPORTANTE):\n"
        "1. Se hai bisogno di informazioni dall'utente (es. password, email, nome app, codice OTP/2FA), "
        "fermati e fai UNA SOLA domanda alla volta. Non chiedere più cose contemporaneamente.\n"
        "2. Usa un tono amichevole, diretto e conciso. NON dare spiegazioni tecniche (es. non dire all'utente che stai usando uno script o aprendo il browser). "
        "Parla come un assistente umano intelligente che sta semplicemente chiedendo le info mancanti per procedere.\n"
        "3. La tua risposta DEVE terminare ESATTAMENTE con la stringa '[DOMANDA]' se ti serve un input.\n"
        "4. Quando hai finito e hai le credenziali necessarie (o se qualcosa è andato storto in modo definitivo), "
        "scrivile o aggiornale DIRETTAMENTE nel file '.env' del server usando un tuo tool bash, senza spiegare all'utente che lo stai facendo. "
        "5. Dopo aver scritto nel file .env o aver concluso l'operazione, fai un breve saluto amichevole per dire che è tutto pronto "
        "e termina la tua risposta ESATTAMENTE con la stringa '[COMPLETATO]'."
    )
    
    try:
        response = await openclaw_service.execute_task(user_id, prompt)
        
        if "[DOMANDA]" in response:
            await storage.save(f"openclaw_session:{user_id}", {"active": True})
            return response.replace("[DOMANDA]", "").strip()
        else:
            await storage.delete(f"openclaw_session:{user_id}")
            return response.replace("[COMPLETATO]", "").strip()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("SETUP_WIZARD_OPENCLAW_ERROR: %s", str(e), exc_info=True)
        return f"❌ Errore durante l'avvio della configurazione via OpenClaw: {str(e)}"

