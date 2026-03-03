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
        "AUTONOMIA TECNICA ASSOLUTA (TASSATIVA): L'utente si aspetta che tu faccia TUTTO da solo e usi SEMPRE IL TUO BROWSER senza esitare e senza chiedere il permesso "
        "o proporre alternative manuali. DEVI muoverti in modo completamente autonomo.\n"
        "NON CHIEDERE ALL'UTENTE DETTAGLI TECNICI COME NOMI DI APP, URL DI REDIRECT, PRIVACY POLICY o permessi. "
        "Inventa tu valori ragionevoli (es. App Name: 'Genesi Integration', URL: 'https://localhost/callback' o 'https://localhost/privacy').\n"
        "L'UNICA COSA CHE SEI AUTORIZZATO A CHIEDERGLI in chat sono le sue credenziali personali strette "
        "(es. la sua Email per fare login, la sua Password, di accettare una notifica sul telefono, o di inserire un OTP).\n"
        "REGOLE FONDAMENTALI DI COMUNICAZIONE:\n"
        "1. Se hai bisogno di informazioni dall'utente (es. password, email, codice OTP/2FA), "
        "TI E' ASSOLUTAMENTE PROIBITO CHIEDERE PIU' DI UNA SINGOLA INFORMAZIONE ALLA VOLTA. "
        "Esempio SBAGLIATO: 'Inserisci la tua email e la password'. "
        "Esempio CORRETTO: 'Qual è la tua email di accesso?' (e solo dopo che ti ha risposto, chiederai la password).\n"
        "2. Usa un tono amichevole e colloquiale. PARLA COME UN UMANO E NON USARE GERGO TECNICO. "
        "Non spiegare cosa stai facendo nel browser (es. non dire 'sto creando la tua app' o 'inserisco l'URL di redirect').\n"
        "3. La tua risposta DEVE terminare ESATTAMENTE con la stringa '[DOMANDA]' se ti serve un input.\n"
        "4. Quando hai finito e hai le credenziali necessarie (o se qualcosa è andato storto in modo definitivo), "
        "scrivile o aggiornale DIRETTAMENTE nel file '.env' del server usando un tuo tool bash, COMPLETAMENTE IN SILENZIO. "
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

