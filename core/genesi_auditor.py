import os
import re
import asyncio
from datetime import datetime
from core.llm_service import llm_service
from core.log import LOG_FILE, log

# 🚨 DISABLED TO PREVENT CREDIT DRAIN
GENESI_AUDITOR_DISABLED = True  # SET TO FALSE TO RE-ENABLE


class GenesiAuditor:
    """
    Analizza i log di Genesi per identificare pattern di successo, fallimento e aree di miglioramento.
    Dopo ogni report, inietta i finding nel lab_feedback_cycle → alimenta global_prompt.json.
    """

    def __init__(self, log_path=LOG_FILE):
        self.log_path = log_path

    async def generate_report(self, lines_to_read: int = 1000) -> str:
        # 🚨 DISABLED TO PREVENT CREDIT DRAIN
        if GENESI_AUDITOR_DISABLED:
            return "📊 GenesiAuditor report generation DISABLED to prevent credit drain"
        
        if not os.path.exists(self.log_path):
            return "File log non trovato. Impossibile generare report."

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
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

            report = await llm_service._call_model(
                "openai/gpt-4o-mini",
                system_prompt,
                user_prompt,
                user_id="system_auditor",
                route="memory"
            )

            # Salva il report su file
            with open("GENESI_AUDIT_REPORT.md", "w", encoding="utf-8") as f:
                f.write(f"# REPORT AUDIT GENESI — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n\n")
                f.write(report)

            log("AUDIT_REPORT_SAVED", lines_read=len(lines[-lines_to_read:]))

            # Inietta i finding nel lab_feedback_cycle in background
            asyncio.create_task(self._inject_findings_to_lab(report))

            return report

        except Exception as e:
            return f"Errore durante l'audit dei log: {str(e)}"

    async def _inject_findings_to_lab(self, report: str) -> None:
        """
        Estrae i finding concreti dal report Markdown e li inietta nel lab_feedback_cycle
        come eventi pending, così il prossimo ciclo li trasforma in regole per global_prompt.json.
        """
        try:
            from core.lab_feedback_cycle import lab_feedback_cycle

            findings = _extract_findings_from_report(report)
            if not findings:
                log("AUDIT_INJECT_SKIPPED", reason="no_findings_extracted")
                return

            for category, text in findings:
                lab_feedback_cycle.record_observation(
                    category=category,
                    observation=text,
                    source="genesi_auditor",
                )

            log("AUDIT_INJECTED_TO_LAB", count=len(findings))

        except Exception as e:
            log("AUDIT_INJECT_ERROR", error=str(e)[:100])


def _extract_findings_from_report(report: str) -> list[tuple[str, str]]:
    """
    Parsa il report Markdown e restituisce una lista di (categoria, testo) per ogni
    finding nelle sezioni negative/migliorative.
    Sezioni considerate: "NON STA FUNZIONANDO", "MIGLIORARE", "AGGIUNGERE".
    """
    findings = []

    # Mappa sezioni Markdown → categoria fallback
    section_map = {
        "NON STA FUNZIONANDO": "audit_bug",
        "NON FUNZIONA": "audit_bug",
        "PROBLEMI": "audit_bug",
        "ERRORI": "audit_bug",
        "MIGLIORARE": "audit_improvement",
        "MIGLIORAMENTO": "audit_improvement",
        "AGGIUNGERE": "audit_suggestion",
        "AGGIUNTA": "audit_suggestion",
        "SUGGERIMENTI": "audit_suggestion",
    }

    # Estrai sezioni: # o ## seguito da testo fino alla prossima sezione
    sections = re.split(r'\n#{1,3}\s+', report)
    for section in sections:
        if not section.strip():
            continue
        # Prima riga = titolo sezione
        lines = section.strip().splitlines()
        title = lines[0].upper().strip(" :#.")
        body = "\n".join(lines[1:]).strip()

        category = None
        for kw, cat in section_map.items():
            if kw in title:
                category = cat
                break
        if not category or not body:
            continue

        # Estrai bullet points o frasi significative (min 20 chars)
        bullets = re.findall(r'[-*•]\s+(.+)', body)
        if bullets:
            for b in bullets:
                b = b.strip()
                if len(b) >= 20:
                    findings.append((category, b[:300]))
        else:
            # Nessun bullet → prendi il corpo intero (max 500 chars)
            text = re.sub(r'\s+', ' ', body).strip()
            if len(text) >= 20:
                findings.append((category, text[:500]))

    return findings


# Singleton instance
genesi_auditor = GenesiAuditor()
