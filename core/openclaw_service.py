import os
import logging
import asyncio
import subprocess

logger = logging.getLogger(__name__)

# Full path to the openclaw binary on the VPS
OPENCLAW_BIN = "/home/luca/.npm-global/bin/openclaw"

class OpenClawService:
    def __init__(self):
        # We check if the binary exists, but don't error out during initialization
        pass

    async def execute_task(self, user_id: str, prompt: str) -> str:
        """
        Esegue un task tramite il comando CLI di OpenClaw.
        Questa è la soluzione più affidabile per l'integrazione iniziale.
        """
        try:
            logger.info("OPENCLAW_CLI_START user=%s prompt=%.50s...", user_id, prompt)
            
            # Sanitizza il prompt (molto importante essendo passato a shell)
            # Ma useremo create_subprocess_exec che passa gli argomenti in lista, quindi è più sicuro
            
            # Command to run: openclaw agent --message "prompt" --agent main
            # We use a session ID based on the user_id to maintain continuity in OpenClaw
            session_id = f"genesi_{user_id.replace('-', '_')}"
            
            # Ensure env is passed down (including the API Keys loaded from .env)
            env = os.environ.copy()
            # Adding Playwright browser path for headless mode on VPS
            env["PLAYWRIGHT_BROWSERS_PATH"] = "/home/luca/.cache/ms-playwright"
            
            process = await asyncio.create_subprocess_exec(
                OPENCLAW_BIN, "agent", 
                "--message", prompt, 
                "--agent", "main",
                "--session-id", session_id,
                "--no-color",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode('utf-8').strip()
                logger.info("OPENCLAW_CLI_SUCCESS user=%s output_len=%d", user_id, len(output))
                
                # Semplice post-processing per pulire eventuali log ANSI o header del CLI se presenti
                # Ma dai test sembra ritornare direttamente il testo dell'AI.
                if not output:
                    return "L'azione è stata completata correttamente, ma non ho ricevuto un messaggio di risposta testuale."
                
                return output
            else:
                error_msg = stderr.decode('utf-8').strip()
                logger.error("OPENCLAW_CLI_ERROR user=%s code=%d error=%s", user_id, process.returncode, error_msg)
                return f"Ho provato ad azionare il mio braccio meccanico (OpenClaw), ma c'è stato un intoppo: {error_msg}"
                
        except Exception as e:
            logger.error("OPENCLAW_CLI_EXCEPTION user=%s error=%s", user_id, str(e), exc_info=True)
            return f"Errore critico durante l'interfaccia con OpenClaw: {str(e)}"

# Singleton instance
openclaw_service = OpenClawService()
