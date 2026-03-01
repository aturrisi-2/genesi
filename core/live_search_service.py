"""
LIVE SEARCH SERVICE - Genesi Core
Ricerca web per domande che richiedono dati aggiornati:
mediche, scientifiche, psicologiche, normative.

Usato SOLO quando il modello LLM non può avere la risposta
aggiornata (ricerche recenti, farmaci, linee guida, statistiche).
Se la ricerca fallisce → fallback silenzioso alla risposta LLM normale.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Keyword che segnalano la necessità di dati live ───────────────────────

# Marcatori di temporalità / aggiornamento
_TEMPORAL = {
    "recente", "recenti", "ultimo", "ultimi", "ultima", "nuov",
    "adesso", "attuale", "attualmente", "2024", "2025", "2026",
    "aggiornato", "aggiornata", "approvato", "approvata",
    "ultimo studio", "nuovi studi",
}

# Ambito medico / farmacologico
_MEDICAL = {
    "farmac", "medicin", "cura", "terapia", "sintom", "malattia",
    "diagnos", "disturbo", "sindrome", "effetti collateral",
    "dosaggio", "interazion", "controindicaz", "vaccin",
    "trattamento", "protocollo clinico", "linee guida",
    "antidepress", "psicofarmac", "psicolog", "psichiatr",
    "ansia", "depressione", "bipolare", "schizofrenia", "tdah",
    "melatonina", "ibuprofene", "paracetamolo", "cortisone",
    "antibiotico", "covid", "influenza", "cancro", "tumore",
    "alzheimer", "parkinson", "colesterol", "diabete",
    "ipertension", "pressione arteriosa",
}

# Ambito scientifico / ricerca
_SCIENTIFIC = {
    "studio scientific", "ricerca scientific", "scoperta",
    "pubblicazione", "trial clinico", "sperimentazione",
    "evidence based", "meta-analisi", "revisione sistematic",
    "studi dimostrano", "studi mostrano", "secondo la ricerca",
    # Pattern generici per "nuovi studi su X", "ricerche recenti su Y"
    "studi su", "studi sull", "studi sul", "studi sui",
    "nuovi studi", "ultimi studi", "ricerche recenti", "ricerche su",
    "cosa dicono gli studi", "ricerca recente",
}

# Ambito normativo / legale / statistico
_REGULATORY = {
    "normativa vigente", "legge vigente", "decreto", "regolamento",
    "statistiche", "dati aggiornati", "percentuale attuale",
    "tasso di", "incidenza",
}


def needs_live_data(message: str) -> bool:
    """
    Ritorna True se la domanda ha alta probabilità di richiedere
    informazioni aggiornate che il modello LLM potrebbe non avere.

    Non viene mai attivato per messaggi brevi o generici.
    """
    if len(message.strip()) < 20:
        return False

    msg = message.lower()

    # Controlla ogni categoria — substring match (es. "farmac" → farmaco, farmaci...)
    def _hits(keyword_set: set) -> bool:
        return any(kw in msg for kw in keyword_set)

    has_temporal = _hits(_TEMPORAL)
    has_medical = _hits(_MEDICAL)
    has_scientific = _hits(_SCIENTIFIC)
    has_regulatory = _hits(_REGULATORY)

    # Trigger: domanda medica/farmacologica specifica
    if has_medical:
        return True

    # Trigger: ricerca scientifica citata esplicitamente
    if has_scientific:
        return True

    # Trigger: normativa o statistiche + temporalità
    if has_regulatory and has_temporal:
        return True

    return False


async def search_for_answer(query: str, max_results: int = 3) -> Optional[dict]:
    """
    Esegue una ricerca DuckDuckGo e ritorna il risultato più rilevante.

    Returns:
        dict con:
          - snippet: testo estratto
          - source_name: nome del sito
          - source_url: URL
          - all_results: lista grezza per il prompt
        oppure None se nessun risultato.
    """
    try:
        import asyncio
        from ddgs import DDGS

        def _sync_search():
            with DDGS() as ddgs:
                return list(ddgs.text(
                    query,
                    max_results=max_results,
                    region="it-it",
                    safesearch="moderate",
                    timelimit="y",   # ultimi 12 mesi
                ))

        results = await asyncio.to_thread(_sync_search)

        if not results:
            logger.info("LIVE_SEARCH_NO_RESULTS query=%s", query[:60])
            return None

        # Prendi il primo risultato come fonte principale
        best = results[0]
        source_url = best.get("href", "")
        source_name = _extract_domain(source_url)

        # Aggrega snippets per il contesto LLM
        context_parts = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "").strip()
            url = r.get("href", "")
            if body:
                context_parts.append(f"[{_extract_domain(url)}] {title}: {body[:350]}")

        logger.info(
            "LIVE_SEARCH_OK query=%s results=%d source=%s",
            query[:60], len(results), source_name,
        )

        return {
            "snippet": best.get("body", "").strip()[:500],
            "source_name": source_name,
            "source_url": source_url,
            "context_block": "\n\n".join(context_parts),
        }

    except Exception as e:
        logger.warning("LIVE_SEARCH_ERROR query=%s error=%s", query[:60], str(e)[:100])
        return None


def _extract_domain(url: str) -> str:
    """Estrae il nome leggibile del dominio dall'URL."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        # Rimuovi www.
        if host.startswith("www."):
            host = host[4:]
        # Rimuovi il TLD per nomi brevi (humanitas.it → Humanitas)
        parts = host.split(".")
        name = parts[0] if parts else host
        return name.capitalize()
    except Exception:
        return url[:40] if url else "fonte"
