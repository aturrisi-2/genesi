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
                # Log raw output for debugging (first 200 chars to avoid log bloat)
                logger.debug("OPENCLAW_RAW_OUTPUT user=%s sample=%.200s", user_id, output.replace('\n', ' '))
                
                # Semplice post-processing per pulire eventuali log ANSI o pensieri (Thinking blocks)
                import re
                
                # Rimuove blocchi <thought>...</thought>
                output = re.sub(r'<thought>.*?</thought>', '', output, flags=re.DOTALL | re.IGNORECASE)
                # Rimuove blocchi [Thought: ...] o similar
                output = re.sub(r'\[Thought:.*?\]', '', output, flags=re.DOTALL | re.IGNORECASE)
                # Rimuove blocchi [System note: ...]
                output = re.sub(r'\[System note:.*?\]', '', output, flags=re.DOTALL | re.IGNORECASE)
                
                # Se l'output sembra codice Javascript puro o dump di file (inizia con bracket o parole chiave JS)
                # e non contiene punteggiatura o parole italiane comuni, potrebbe essere un errore del modello.
                js_indicators = ['const ', 'let ', 'var ', 'function', 'expect(', ').toEqual', '});', '].forEach']
                if any(ind in output for ind in js_indicators) and len(output) > 200:
                    # Se c'è molto codice, proviamo a estrarre solo la parte finale se sembra umana,
                    # altrimenti riportiamo un errore pulito.
                    lines = output.split('\n')
                    human_lines = [l for l in lines if not any(ind in l for ind in js_indicators) and len(l.strip()) > 3]
                    if human_lines:
                        output = " ".join(human_lines)
                    else:
                        logger.warning("OPENCLAW_CODE_OUTPUT_DETECTED user=%s", user_id)
                        return "Scusami Alfio, ho avuto un piccolo corto circuito tecnico. Puoi ripetermi cosa volevi fare? [DOMANDA]"

                output = output.strip()
                
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
