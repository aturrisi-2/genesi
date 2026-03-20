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

# Richieste esplicite di ricerca web
_EXPLICIT_SEARCH = {
    "cerca sul web", "cerca online", "cerca su internet", "cerca in rete",
    "cerca su google", "cerca su bing", "cerca su duckduckgo",
    "fai una ricerca", "fai una ricerca su", "fai una ricerca online",
    "cerca per me", "trovami informazioni", "trovami notizie",
    "cerca informazioni su", "cerca notizie su",
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
    if len(message.strip()) < 10:
        return False

    msg = message.lower()

    def _hits(keyword_set: set) -> bool:
        return any(kw in msg for kw in keyword_set)

    # Richiesta esplicita di ricerca web: sempre live
    if _hits(_EXPLICIT_SEARCH):
        return True

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


def _build_search_query(query: str) -> tuple[str, str]:
    """
    Ritorna (search_query, tbs) dove tbs è il filtro temporale Serper/DDG.
    Inietta data/anno nella query per forzare risultati del 2026.
    """
    from datetime import datetime as _dt
    now = _dt.now()
    year = now.year
    # Data completa tipo "20 marzo 2026" per massima precisione
    months_it = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
                 "luglio","agosto","settembre","ottobre","novembre","dicembre"]
    date_str = f"{now.day} {months_it[now.month - 1]} {year}"

    q_lower = query.lower()
    immediate_kw = [
        "questo weekend", "questo fine settimana", "fine settimana",
        "oggi", "adesso", "ora", "stanotte", "stasera", "stamattina",
        "questa settimana", "settimana corrente",
    ]
    month_kw = ["questo mese", "mese corrente", "quest'anno", "questa stagione"]

    if any(k in q_lower for k in immediate_kw):
        # Data completa + timelimit last week → forza 2026
        return f"{query} {date_str}", "qdr:w"
    elif any(k in q_lower for k in month_kw):
        return f"{query} {year}", "qdr:m"
    else:
        # Sempre aggiunge l'anno per evitare risultati del 2025
        if str(year) not in query:
            return f"{query} {year}", "qdr:y"
        return query, "qdr:y"


async def _search_serper(query: str, max_results: int = 5) -> Optional[list[dict]]:
    """
    Ricerca via Serper.dev (Google backend).
    Ritorna lista di {"title", "link", "snippet"} o None se fallisce.
    """
    import os, aiohttp
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        return None

    search_query, tbs = _build_search_query(query)
    payload = {
        "q": search_query,
        "gl": "it",
        "hl": "it",
        "num": max_results,
        "tbs": tbs,
    }
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://google.serper.dev/search",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    logger.warning("SERPER_HTTP_ERROR status=%d", resp.status)
                    return None
                data = await resp.json()

        # Estrai risultati organici
        results = []
        # answerBox ha la risposta diretta (es. meteo, calcoli)
        ab = data.get("answerBox", {})
        if ab.get("answer") or ab.get("snippet"):
            results.append({
                "title": ab.get("title", "Google Answer"),
                "link": ab.get("link", ""),
                "snippet": ab.get("answer") or ab.get("snippet", ""),
            })
        for r in data.get("organic", []):
            results.append({
                "title": r.get("title", ""),
                "link": r.get("link", ""),
                "snippet": r.get("snippet", ""),
            })
            if len(results) >= max_results:
                break
        return results if results else None

    except Exception as e:
        logger.warning("SERPER_ERROR query=%s error=%s", query[:60], str(e)[:80])
        return None


async def _search_ddg(query: str, max_results: int = 3) -> Optional[list[dict]]:
    """
    Fallback DuckDuckGo.
    """
    import asyncio
    search_query, tbs = _build_search_query(query)
    # DDG usa "w"/"m"/"y" invece di "qdr:w"
    ddg_timelimit = tbs.replace("qdr:", "") if ":" in tbs else tbs

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        def _sync():
            with DDGS() as ddgs:
                return list(ddgs.text(
                    search_query,
                    max_results=max_results,
                    region="it-it",
                    safesearch="moderate",
                    timelimit=ddg_timelimit,
                ))

        raw = await asyncio.to_thread(_sync)
        if not raw:
            return None
        return [
            {"title": r.get("title", ""), "link": r.get("href", ""), "snippet": r.get("body", "")}
            for r in raw
        ]
    except Exception as e:
        logger.warning("DDG_SEARCH_ERROR query=%s error=%s", query[:60], str(e)[:80])
        return None


async def search_for_answer(query: str, max_results: int = 5) -> Optional[dict]:
    """
    Cerca online: prova Serper (Google) prima, poi fallback DuckDuckGo.

    Returns:
        dict con:
          - snippet: testo estratto dal risultato principale
          - source_name: nome del sito
          - source_url: URL
          - context_block: tutti i risultati aggregati per il prompt LLM
        oppure None se nessun risultato.
    """
    # Prova Serper prima
    results = await _search_serper(query, max_results=max_results)
    provider = "serper"

    # Fallback DDG se Serper non configurato o fallisce
    if not results:
        results = await _search_ddg(query, max_results=min(max_results, 3))
        provider = "ddg"

    if not results:
        logger.info("LIVE_SEARCH_NO_RESULTS query=%s", query[:60])
        return None

    best = results[0]
    source_url = best.get("link", "")
    source_name = _extract_domain(source_url)

    context_parts = []
    for r in results:
        title = r.get("title", "")
        snippet = r.get("snippet", "").strip()
        url = r.get("link", "")
        if snippet:
            context_parts.append(f"[{_extract_domain(url)}] {title}: {snippet[:350]}")

    logger.info(
        "LIVE_SEARCH_OK provider=%s query=%s results=%d source=%s",
        provider, query[:60], len(results), source_name,
    )

    return {
        "snippet": best.get("snippet", "").strip()[:500],
        "source_name": source_name,
        "source_url": source_url,
        "context_block": "\n\n".join(context_parts),
    }


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
