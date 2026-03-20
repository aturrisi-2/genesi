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
    "oggi", "ieri", "stanotte", "stamattina", "stamattina",
    "questa settimana", "questo mese", "quest'anno",
    "ultimamente", "di recente", "in questi giorni",
    "nelle ultime ore", "nelle ultime settimane",
    "questo weekend", "questo fine settimana", "fine settimana",
    "questa domenica", "sabato prossimo", "domenica prossima",
    "questo week", "nel weekend",
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

# Ambito eventi correnti — politica, economia, sport, conflitti, tech
_CURRENT_EVENTS = {
    # Politica / governo
    "elezioni", "governo", "premier", "presidente", "parlamento",
    "ministro", "partito politico", "voto", "referendum",
    "sondaggio politico", "legge approvata", "riforma",
    # Economia / finanza
    "borsa", "spread", "inflazione", "pil", "recessione",
    "prezzo del petrolio", "prezzo della benzina", "costo dell",
    "tasso di interesse", "bce", "banca centrale",
    "bitcoin", "crypto", "azioni di", "mercati",
    # Conflitti / crisi internazionali
    "guerra", "conflitto armato", "crisi diplomatica",
    "attacco missilistico", "bombardament", "cessate il fuoco",
    "sanctions", "sanzioni",
    # Sport — risultati, classifiche ed eventi live
    "risultato di ieri", "risultato di oggi", "chi ha vinto",
    "classifica attuale", "classifica di serie", "champions league",
    "partita di ieri", "partita di oggi", "prossima partita",
    "trasferimento di mercato", "calciomercato",
    "formula 1", "formula uno", "gran premio", "gara di formula",
    "dove corrono", "dove si corre", "dove giocano", "dove si gioca",
    "dove si svolge la gara", "dove si disputa", "calendario f1",
    "piloti di formula", "circuito di", "gara di domenica",
    # Tecnologia / prodotti nuovi
    "nuovo modello di", "nuova versione di", "ultimo aggiornamento di",
    "ha appena lanciato", "ha presentato", "annunciato da",
    # Disastri / cronaca
    "terremoto", "alluvione", "incendio a", "tragedia",
    "incidente a", "attentato",
}


def needs_live_data(message: str) -> bool:
    """
    Ritorna True se la domanda ha alta probabilità di richiedere
    informazioni aggiornate che il modello LLM potrebbe non avere.
    """
    if len(message.strip()) < 15:
        return False

    msg = message.lower()

    def _hits(keyword_set: set) -> bool:
        return any(kw in msg for kw in keyword_set)

    has_temporal      = _hits(_TEMPORAL)
    has_medical       = _hits(_MEDICAL)
    has_scientific    = _hits(_SCIENTIFIC)
    has_regulatory    = _hits(_REGULATORY)
    has_current_events = _hits(_CURRENT_EVENTS)

    # Medico/farmacologico: sempre live
    if has_medical:
        return True

    # Ricerca scientifica citata esplicitamente: sempre live
    if has_scientific:
        return True

    # Normativa/statistiche + temporalità: live
    if has_regulatory and has_temporal:
        return True

    # Evento corrente + temporalità: live (es. "chi ha vinto le elezioni ieri?")
    if has_current_events and has_temporal:
        return True

    # Solo topic corrente anche senza temporal marker (notizie per natura volatili)
    if has_current_events and len(message.strip()) > 25:
        return True

    # Temporalità forte + messaggio specifico (es. "cosa è successo oggi in Italia?")
    if has_temporal and len(message.strip()) > 40:
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

        # Supporta sia ddgs (>=7) che duckduckgo_search (<7)
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

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
