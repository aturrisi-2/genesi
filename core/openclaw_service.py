import os
import logging
import asyncio
import base64
from datetime import datetime
import glob
import subprocess

logger = logging.getLogger(__name__)

# Full path to the openclaw binary on the VPS
OPENCLAW_BIN = "/home/luca/.npm-global/bin/openclaw"
# File di sessione principale di OpenClaw (accumulatore di storia conversazionale)
OPENCLAW_SESSION_FILE = "/home/luca/.openclaw/agents/main/sessions/4b84a9ba-8d95-47c5-8086-3f26269d73aa.jsonl"
OPENCLAW_SESSION_MAX_BYTES = 50_000  # reset se supera 50KB (~15k token)

class OpenClawService:
    def __init__(self):
        # We check if the binary exists, but don't error out during initialization
        pass

    async def execute_task(self, user_id: str, prompt: str, status_callback=None, session_id: str = None) -> str:
        """
        Esegue un task tramite il comando CLI di OpenClaw con feedback in tempo reale.
        Supporta log umanizzati e anteprime screenshot.
        """
        try:
            import time
            if session_id is None:
                session_id = f"genesi_{user_id.replace('-', '_')}_{int(time.time())}"

            # Reset automatico della sessione se troppo grande (evita context overflow)
            try:
                if os.path.exists(OPENCLAW_SESSION_FILE):
                    size = os.path.getsize(OPENCLAW_SESSION_FILE)
                    if size > OPENCLAW_SESSION_MAX_BYTES:
                        with open(OPENCLAW_SESSION_FILE, 'w') as _sf:
                            pass  # truncate
                        logger.info("OPENCLAW_SESSION_RESET size_before=%d user=%s", size, user_id)
            except Exception as _reset_err:
                logger.warning("OPENCLAW_SESSION_RESET_FAILED error=%s", _reset_err)

            logger.info("OPENCLAW_CLI_START user=%s session=%s prompt=%.50s...", user_id, session_id, prompt)
            
            env = os.environ.copy()
            env["PLAYWRIGHT_BROWSERS_PATH"] = "/home/luca/.cache/ms-playwright"
            chrome_exe = "/home/luca/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome"
            env["CHROME_PATH"] = chrome_exe
            env["CHROME_BIN"] = chrome_exe
            env["PATH"] = f"/home/luca/.npm-global/bin:{env.get('PATH', '')}"
            
            # Directory per monitorare gli screenshot su VPS
            # Nota: gli screenshot finiscono in ~/.openclaw/media/browser/
            screenshot_dir = "/home/luca/.openclaw/media/browser"
            
            # Helper per inviare status umanizzati
            async def send_status(text, screenshot=None):
                if status_callback:
                    if asyncio.iscoroutinefunction(status_callback):
                        await status_callback(text, screenshot)
                    else:
                        status_callback(text, screenshot)

            await send_status("Sto accendendo il mio motore di ricerca in background...")

            process = await asyncio.create_subprocess_exec(
                OPENCLAW_BIN, "agent", 
                "--message", prompt, 
                "--agent", "main",
                "--session-id", session_id,
                "--no-color",
                "--verbose", "on", # Attiviamo verbose per catturare più fasi
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Task per monitorare gli screenshot durante l'esecuzione
            start_time = datetime.now()
            last_screenshot_path = None
            
            async def screenshot_watcher():
                nonlocal last_screenshot_path
                while process.returncode is None:
                    try:
                        # Cerchiamo il file più recente nella cartella media locale (sul VPS)
                        png_files = glob.glob(f"{screenshot_dir}/*.png")
                        if not png_files:
                            await asyncio.sleep(4)
                            continue
                            
                        # Prendi il file più recente per data di modifica
                        latest_file = max(png_files, key=os.path.getmtime)
                        
                        # IGNORA screenshot vecchi (antecedenti all'inizio del task)
                        if os.path.getmtime(latest_file) < start_time.timestamp():
                            await asyncio.sleep(4)
                            continue
                        
                        if latest_file != last_screenshot_path:
                            last_screenshot_path = latest_file
                            # Leggiamo il file e convertiamo in base64
                            try:
                                with open(latest_file, "rb") as f:
                                    b64_str = base64.b64encode(f.read()).decode('utf-8')
                                if b64_str:
                                    await send_status("Ho una prima visuale della pagina...", b64_str)
                            except Exception as read_err:
                                logger.error("SCREENSHOT_READ_ERROR: %s", str(read_err))
                    except Exception as watch_err:
                        logger.debug("WATCHER_TICK_ERROR: %s", str(watch_err))
                    await asyncio.sleep(4) # Check ogni 4 secondi

            # Avviamo il watcher in background per le anteprime live
            watcher_task = asyncio.create_task(screenshot_watcher())
            
            # Lettura real-time dell'output per log umanizzati
            all_stdout = []
            
            async def read_stream(stream, is_stderr=False):
                try:
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        line_str = line.decode('utf-8').strip()
                        if not line_str: continue
                        
                        if not is_stderr:
                            all_stdout.append(line_str)
                        
                        # Mapping logs tecnici -> messaggi umani
                        low = line_str.lower()
                        if "navigated to" in low or "goto" in low:
                            url = line_str.split(" ")[-1]
                            await send_status(f"Mi sto collegando a {url}...")
                        elif "clicking" in low or "click" in low:
                            await send_status("Sto interagendo con la pagina...")
                        elif "waiting for" in low:
                            await send_status("Attendo un attimo che la pagina si carichi...")
                        elif "extracted" in low or "found" in low:
                            await send_status("Ho trovato dei risultati interessanti, li sto analizzando...")
                        elif "login" in low or "auth" in low or "password" in low:
                            await send_status("Controllo le credenziali di accesso...")
                        elif "screenshot" in low or "snapshot" in low or "taking" in low:
                            await send_status("Sto scattando una foto della pagina...")
                        elif "action" in low or "perform" in low:
                            await send_status("Eseguo l'operazione sulla pagina...")
                        elif "thinking" in low or "<thought>" in low:
                            await send_status("Sto riflettendo su come procedere...")
                except Exception as stream_err:
                    logger.error("STREAM_READ_ERROR: %s", str(stream_err))

            # Eseguiamo la lettura in parallelo
            await asyncio.gather(
                read_stream(process.stdout),
                read_stream(process.stderr, True),
                process.wait()
            )
            
            # Annulliamo il watcher quando il processo finisce
            watcher_task.cancel()
            try:
                await watcher_task
            except asyncio.CancelledError:
                pass

            if process.returncode == 0:
                output = "\n".join(all_stdout).strip()
                logger.debug("OPENCLAW_RAW_OUTPUT user=%s sample=%.200s", user_id, output.replace('\n', ' '))

                # Rileva overflow di contesto: OpenClaw ha esaurito la finestra del modello
                if "context overflow" in output.lower() or "prompt too large" in output.lower():
                    logger.warning("OPENCLAW_CONTEXT_OVERFLOW user=%s session=%s", user_id, session_id)
                    return "La sessione precedente era diventata troppo lunga. L'ho resettata: riprova a darmi il tuo comando e ripartirò da zero."
                
                import re
                output = re.sub(r'<thought>.*?</thought>', '', output, flags=re.DOTALL | re.IGNORECASE)
                output = re.sub(r'\[Thought:.*?\]', '', output, flags=re.DOTALL | re.IGNORECASE)
                output = re.sub(r'\[System note:.*?\]', '', output, flags=re.DOTALL | re.IGNORECASE)
                
                # Pulizia finale dell'output [COMPLETATO] o [DOMANDA]
                output = output.strip()
                
                # Riduci rumore dei log tecnici se l'output è molto lungo
                if len(output) > 4000:
                    lines = output.split('\n')
                    # Filtra via i log di navigazione/interazione se siamo oltre il limite
                    filtered = [l for l in lines if not any(kw in l.lower() for kw in ["navigated", "goto", "clicking", "waiting", "found", "extracted"])]
                    output = "\n".join(filtered).strip()
                
                # Hard limit finale per sicurezza (Synthesis context window)
                if len(output) > 6000:
                    output = "[... Parte dell'output rimossa per brevità ...]\n" + output[-6000:]

                if not output:
                    return "Azione completata, Alfio. Tutto sotto controllo."
                
                return output
            else:
                logger.error("OPENCLAW_CLI_ERROR user=%s code=%d", user_id, process.returncode)
                return f"Ho avuto un intoppo nel muovere il mio braccio digitale. Riprova tra un attimo."
                
        except Exception as e:
            logger.error("OPENCLAW_CLI_EXCEPTION user=%s error=%s", user_id, str(e), exc_info=True)
            return f"Errore nell'interfaccia con OpenClaw: {str(e)}"

# Singleton instance
openclaw_service = OpenClawService()
