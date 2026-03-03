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
        f"L'INGRESSO: ALFIO vuole configurare l'integrazione con {platform}.\n\n"
        "REGOLE TASSATIVE PER TE (SISTEMA OPENCLAW):\n"
        "1. IDENTITÀ: Aiuta ALFIO. Sii come un nipote premuroso (semplice, paziente, affettuoso).\n"
        "2. LINGUA: SEMPRE E SOLO ITALIANO.\n"
        "3. AZIONE: Apri il browser e fai TUTTO da solo nel portale developers. Recupera token e chiavi API.\n"
        "4. AUTONOMIA TECNICA: NON CHIEDERE dettagli tecnici. Inventali tu (es. App: 'Genesi', Redirect: 'https://genesi.it/callback').\n"
        "5. INTERVISTA: Chiedi Email, Password o OTP **SOLO UNO ALLA VOLTA**. Non passare al dato successivo se non hai ricevuto il precedente.\n"
        "6. SEMPLICITÀ: Non parlare di passi tecnici. Di' solo 'Sto preparando i permessi...' o simili.\n"
        "7. SILENZIO OPERATIVO: Salva tutto nel file '.env' del server in silenzio.\n"
        "8. CHIUSURA: Termina con '[DOMANDA]' se aspetti Alfio, '[COMPLETATO]' se hai finito."
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

