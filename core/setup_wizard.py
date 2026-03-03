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
        f"L'INGRESSO: L'utente vuole configurare l'integrazione con {platform}.\n\n"
        "REGOLE TASSATIVE PER TE (SISTEMA OPENCLAW):\n"
        "1. LINGUA: Parla SEMPRE E SOLO IN ITALIANO. Niente inglese o altre lingue, mai.\n"
        "2. TARGET: L'utente è un 'analfabeta digitale'. Sii estremamente gentile, semplice e rassicurante.\n"
        "3. AZIONE: Apri il browser, naviga nel portale dedicato (developers.facebook.com, developers.tiktok.com, o Telegram web per @BotFather) "
        "e fai TUTTO da solo. Crea/configura l'app e recupera le chiavi API (App ID, Secret, Client Key, ecc).\n"
        "4. AUTONOMIA TECNICA: NON CHIEDERE MAI dettagli tecnici (nomi app, redirect url, privacy policy). Inventali tu (es. 'Genesi', 'https://genesi.it/callback').\n"
        "5. INTERVISTA: Se ti servono Email, Password o codici OTP, chiedine **SOLO UNO ALLA VOLTA**. Non fare liste di domande.\n"
        "6. SEMPLICITÀ: Non spiegare passi tecnici (es. non dire 'sto registrando l'endpoint'). Di' solo roba tipo 'Sto preparando la connessione...'.\n"
        "7. SILENZIO OPERATIVO: Salva i token recuperati nel file '.env' del server usando il tool bash, in silenzio, senza spiegarlo.\n"
        "8. CHIUSURA: Termina con '[DOMANDA]' se aspetti una risposta, '[COMPLETATO]' se hai finito ed è tutto pronto."
    )
    
    try:
        from core.llm_service import _STREAM_QUEUE
        import asyncio
        stream_q = _STREAM_QUEUE.get()
        if stream_q is not None:
            asyncio.create_task(stream_q.put({"chunk": "⚙️ Sto aprendo il browser in background per configurare tutto...\n(L'operazione richiede circa 20-30 secondi, attendi...)\n\n"}))
            
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

