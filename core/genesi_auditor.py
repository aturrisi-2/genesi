import os
import asyncio
from core.llm_service import llm_service
from core.log import LOG_FILE

class GenesiAuditor:
    """
    Analizza i log di Genesi per identificare pattern di successo, fallimento e aree di miglioramento.
    """

    def __init__(self, log_path=LOG_FILE):
        self.log_path = log_path

    async def generate_report(self, lines_to_read: int = 2000) -> str:
        if not os.path.exists(self.log_path):
            return "File log non trovato. Impossibile generare report."

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                # Leggi le ultime N righe
                lines = f.readlines()
                log_snippet = "".join(lines[-lines_to_read:])

            system_prompt = """Sei l'Auditor di Genesi. Il tuo compito è analizzare i log tecnici del sistema e fornire un riassunto esecutivo per lo sviluppatore.
Analizza i log forniti (in formato ISO_TIMESTAMP TAG key=value) e identifica:

1. COSA STA FUNZIONANDO: (es. routing corretti, tool che rispondono, identità riconosciuta)
2. COSA NON STA FUNZIONANDO: (es. intenti sbagliati, errori API, loop di conversazione, timeout)
3. COSA MIGLIORARE: (es. pattern regex da aggiungere, prompt da affinare, nuovi intenti necessari)
4. COSA AGGIUNGERE: (suggerimenti basati sulle interazioni utente non soddisfatte)

Sii onesto, tecnico ma leggibile. Usa il formato Markdown in ITALIANO.
"""
            user_prompt = f"Ecco gli ultimi log estratti da {self.log_path}:\n\n{log_snippet}"

            print(f"[DEBUG_AUDITOR] Invio {len(lines[-lines_to_read:])} righe di log all'LLM per analisi...")
            
            report = await llm_service._call_with_protection(
                model="gpt-4o",  # Usiamo un modello forte per l'analisi
                prompt=system_prompt,
                message=user_prompt,
                user_id="system_auditor",
                route="deep_analysis"
            )

            # Salva il report su file persistente per consultazione
            with open("GENESI_AUDIT_REPORT.md", "w", encoding="utf-8") as f:
                f.write(f"# REPORT AUDIT GENESI - {os.path.basename(self.log_path)}\n\n")
                f.write(report)

            print(f"[DEBUG_AUDITOR] Report generato con successo: GENESI_AUDIT_REPORT.md")
            return report

        except Exception as e:
            return f"Errore durante l'audit dei log: {str(e)}"

# Singleton instance
genesi_auditor = GenesiAuditor()
