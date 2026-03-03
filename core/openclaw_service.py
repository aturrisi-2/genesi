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

    async def execute_task(self, user_id: str, prompt: str, status_callback=None) -> str:
        """
        Esegue un task tramite il comando CLI di OpenClaw con feedback in tempo reale.
        Supporta log umanizzati e anteprime screenshot.
        """
        try:
            logger.info("OPENCLAW_CLI_START user=%s prompt=%.50s...", user_id, prompt)
            session_id = f"genesi_{user_id.replace('-', '_')}"
            
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
            import base64
            from datetime import datetime
            last_screenshot_path = None
            
            async def screenshot_watcher():
                nonlocal last_screenshot_path
                while process.returncode is None:
                    try:
                        # Cerchiamo il file più recente nella cartella media
                        # Usiamo ls -Art per avere i più recenti alla fine
                        cmd = f"ls -Art {screenshot_dir}/*.png | tail -n 1"
                        check = await asyncio.create_subprocess_shell(
                            f"ssh luca@87.106.30.193 \"{cmd}\"",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        out, _ = await check.communicate()
                        path = out.decode().strip()
                        
                        if path and path.endswith(".png") and path != last_screenshot_path:
                            last_screenshot_path = path
                            # Scarichiamo e convertiamo in base64
                            download = await asyncio.create_subprocess_shell(
                                f"ssh luca@87.106.30.193 \"cat {path} | base64 -w 0\"",
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )
                            b64_out, _ = download.communicate()
                            b64_str = b64_out.decode().strip()
                            if b64_str:
                                await send_status("Ho una prima visuale della pagina...", b64_str)
                    except:
                        pass
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
                        elif "login" in low or "auth" in low:
                            await send_status("Controllo le credenziali di accesso...")
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
                
                import re
                output = re.sub(r'<thought>.*?</thought>', '', output, flags=re.DOTALL | re.IGNORECASE)
                output = re.sub(r'\[Thought:.*?\]', '', output, flags=re.DOTALL | re.IGNORECASE)
                output = re.sub(r'\[System note:.*?\]', '', output, flags=re.DOTALL | re.IGNORECASE)
                
                # Pulizia finale dell'output [COMPLETATO] o [DOMANDA]
                output = output.strip()
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
