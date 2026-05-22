import asyncio
import logging
import re
from html.parser import HTMLParser
import httpx

logger = logging.getLogger(__name__)

# Regex per trovare URL nei messaggi
URL_REGEX = re.compile(
    r'(https?://[^\s<>"]+)',
    re.IGNORECASE
)

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.text_parts = []
        self.current_tag = ""
        # Tag HTML rumorosi da ignorare completamente per il contenuto testuale
        self.ignore_tags = {
            "script", "style", "nav", "header", "footer", "head",
            "svg", "noscript", "aside", "form", "iframe", "button"
        }
        self.ignore_depth = 0

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag.lower()
        if self.current_tag in self.ignore_tags:
            self.ignore_depth += 1

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in self.ignore_tags:
            self.ignore_depth = max(0, self.ignore_depth - 1)
        if self.current_tag == tag_lower:
            self.current_tag = ""

    def handle_data(self, data):
        if self.ignore_depth > 0:
            return
        
        text = data.strip()
        if not text:
            return
            
        if self.current_tag == "title":
            self.title = text
        else:
            self.text_parts.append(text)

    def get_text(self) -> str:
        content = " ".join(self.text_parts)
        # Sostituisce spazi e tab multipli con uno spazio singolo
        content = re.sub(r'[ \t]+', ' ', content)
        # Sostituisce newlines multiple con un'unica newline
        content = re.sub(r'\n+', '\n', content)
        return content.strip()


async def explore_link(url: str) -> str:
    """Scarica e analizza un URL estraendo titolo e testo pulito."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("LINK_EXPLORER_HTTP_ERROR status=%d url=%s", resp.status_code, url)
                return f"[Link: {url} | Errore: HTTP {resp.status_code}]"
            
            content_type = resp.headers.get("content-type", "").lower()
            if "html" not in content_type:
                # Se è testo semplice o JSON
                text_content = resp.text[:800].strip()
                return f"[Link: {url}\nContenuto: {text_content}]"
            
            parser = HTMLTextExtractor()
            parser.feed(resp.text)
            title = parser.title or "Nessun titolo"
            body = parser.get_text()
            
            # Limita il corpo a 800 caratteri per evitare token bloat
            if len(body) > 800:
                body = body[:800] + "..."
                
            logger.info("LINK_EXPLORE_OK url=%s title=%s len=%d", url, title, len(body))
            return f"[Link: {url} | Titolo: {title}\nContenuto: {body}]"
    except Exception as e:
        logger.warning("LINK_EXPLORE_EXCEPTION url=%s err=%s", url, e)
        return f"[Link: {url} | Errore: non raggiungibile ({type(e).__name__})]"


async def explore_links_in_text(text: str) -> str:
    """Trova tutti i link nel testo, li esplora e appende le informazioni utili."""
    if not text:
        return text

    urls = list(dict.fromkeys(URL_REGEX.findall(text)))  # Rimuove duplicati mantenendo l'ordine
    if not urls:
        return text

    logger.info("LINK_EXPLORER_FOUND_URLS count=%d urls=%s", len(urls), urls)
    
    # Esplora fino a un massimo di 3 link in parallelo per non rallentare troppo la risposta
    tasks = [explore_link(url) for url in urls[:3]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    summaries = []
    for r in results:
        if isinstance(r, Exception):
            continue
        summaries.append(r)
        
    if not summaries:
        return text
        
    summary_block = "\n\n[Contenuto dei Link esplorati nel messaggio:\n" + "\n\n".join(summaries) + "]"
    return text + summary_block
