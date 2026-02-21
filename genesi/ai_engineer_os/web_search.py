"""
Web Search Tool per AI Engineer OS.
Usa DuckDuckGo — nessuna API key richiesta.
I risultati vengono iniettati nel contesto LLM, invisibili all'utente.
"""

from ddgs import DDGS
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def should_search(message: str) -> bool:
    """
    Decide se il messaggio richiede una ricerca web.
    Trigger su: versioni, librerie, changelog, esempi reali, "latest", "ultimo".
    """
    # Filtra messaggi bash/terminale copiati per errore
    if message.startswith("(venv)"):
        return False
    if "$/opt/" in message:
        return False
    if len(message) > 300:
        return False
    
    keywords = [
        # Italiano
        'ultima versione', 'versione stabile', 'changelog', 'novità',
        'aggiornamento', 'documentazione', 'esempio', 'tutorial',
        'come si usa', 'come funziona', 'installare', 'configurare',
        'errore', 'bug', 'issue', 'github', 'repo', 'libreria',
        'framework', 'package', 'modulo', 'deprecato', 'migrazione',
        # Inglese
        'latest', 'version', 'how to', 'example', 'docs',
        'install', 'setup', 'release', 'update', 'import',
        # Coding & Debugging
        'fix', 'error', 'traceback', 'exception', 'debug', 'undefined', 
        'null', 'import error', 'syntax', 'typeerror', 'attributeerror',
        'cannot', 'failed', 'not working', 'broken'
    ]
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in keywords)


def build_search_query(message: str) -> str:
    """Costruisce una query ottimizzata per ricerche tecniche."""
    # Aggiungi contesto tecnico se non presente
    tech_terms = ['python', 'fastapi', 'javascript', 'typescript', 'react',
                  'docker', 'git', 'linux', 'sql', 'api', 'rest', 'async']
    has_tech = any(t in message.lower() for t in tech_terms)
    
    query = message.strip()
    if not has_tech:
        query = f"programming {query}"
    
    # Limita lunghezza query
    return query[:150]


async def search_web(query: str, max_results: int = 4) -> Optional[str]:
    """
    Esegue ricerca DuckDuckGo e restituisce testo formattato
    da iniettare nel contesto LLM.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                query,
                max_results=max_results,
                region='wt-wt',
                safesearch='off',
                timelimit='y'  # ultimi 12 mesi
            ))
        
        if not results:
            return None
        
        # Formatta per il contesto LLM
        context_lines = [
            "=== RICERCA WEB (contesto tecnico aggiornato) ===",
            f"Query: {query}",
            ""
        ]
        
        for i, r in enumerate(results, 1):
            title = r.get('title', 'N/A')
            body = r.get('body', '').strip()
            href = r.get('href', '')
            if body:
                context_lines.append(f"[{i}] {title}")
                context_lines.append(f"    {body[:300]}")
                context_lines.append(f"    Fonte: {href}")
                context_lines.append("")
        
        context_lines.append("=== FINE RICERCA WEB ===")
        
        logger.info(f"WEB_SEARCH_OK query='{query}' results={len(results)}")
        return '\n'.join(context_lines)
    
    except Exception as e:
        logger.warning(f"WEB_SEARCH_ERROR query='{query}' error={e}")
        return None

def search_github(query: str) -> Optional[str]:
    """
    Cerca su GitHub via Search API senza auth.
    I risultati vengono integrati dopo quelli di web search.
    """
    import urllib.parse
    import requests
    try:
        q = urllib.parse.quote(query)
        url = f"https://api.github.com/search/repositories?q={q}&sort=stars&per_page=3"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Genesi-AI-Engineer-OS"
        }
        resp = requests.get(url, headers=headers, timeout=5.0)
        if resp.status_code != 200:
            return None
            
        items = resp.json().get("items", [])
        if not items:
            return None
            
        risultati = []
        for item in items:
            name = item.get("full_name", "")
            description = item.get("description", "")
            repo_url = item.get("html_url", "")
            stars = item.get("stargazers_count", 0)
            risultati.append(f"- [{name}]({repo_url}) ⭐{stars}: {description}")
            
        logger.info(f"GITHUB_SEARCH_OK results={len(items)}")
        return "GitHub repos trovati:\n" + "\n".join(risultati)
    except Exception as e:
        logger.warning(f"GITHUB_SEARCH_ERROR query='{query}' error={e}")
        return None
