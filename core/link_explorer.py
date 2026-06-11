import asyncio
import logging
import re
import httpx
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

# Regex per trovare URL nei messaggi
URL_REGEX = re.compile(
    r'(https?://[^\s<>"]+)',
    re.IGNORECASE
)

def extract_youtube_id(url: str) -> str:
    m = re.search(r'(?:v=|youtu\.be/|shorts/)([^&?]+)', url)
    if m:
        return m.group(1)
    return None

async def summarize_long_text(text: str, url: str) -> str:
    """Riassume il testo se è troppo lungo per evitare di consumare troppi token nel contesto."""
    if len(text) <= 1500:
        return text
    
    prompt = (
        "Sei un assistente che riassume il contenuto testuale estratto da un URL o video in modo conciso ma completo (max 150 parole). "
        "Estrai i punti salienti, chiari e utili per una discussione. Mantieni il tono informativo neutro."
    )
    user_msg = f"URL: {url}\n\nTESTO DA RIASSUMERE:\n{text[:15000]}"
    
    try:
        from core.llm_service import llm_service
        summary = await llm_service._call_model(
            "openai/gpt-4o-mini",
            prompt,
            user_msg,
            user_id="link-summarizer",
            route="memory"
        )
        if summary:
            return f"[RIASSUNTO AUTOGENERATO (testo originale troppo lungo)]\n{summary.strip()}"
    except Exception as e:
        logger.warning("LINK_SUMMARIZER_ERROR url=%s err=%s", url, e)
    
    # Fallback
    return text[:1500] + "\n...[testo troncato per lunghezza]"

async def explore_youtube(url: str, video_id: str) -> str:
    """Scarica la trascrizione di un video YouTube."""
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        try:
            transcript = transcript_list.find_transcript(['it', 'en'])
        except Exception:
            # Fallback a qualsiasi lingua generata
            transcript = transcript_list.find_generated_transcript(['it', 'en'])
            
        transcript_data = transcript.fetch()
        text_parts = []
        for t in transcript_data:
            if isinstance(t, dict):
                text_parts.append(t.get('text', ''))
            elif hasattr(t, 'text'):
                text_parts.append(getattr(t, 'text'))
                
        text = " ".join(text_parts)
        # Pulizia
        text = re.sub(r'\[.*?\]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        final_text = await summarize_long_text(text, url)
        
        return f"[Link YouTube: {url}]\nTrascrizione Parlato:\n{final_text}"
    except Exception as e:
        logger.warning("LINK_YOUTUBE_ERROR url=%s id=%s err=%s", url, video_id, e)
        return None

async def explore_jina(url: str) -> str:
    """Scarica il contenuto markdown della pagina tramite l'API gratuita Jina Reader."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    jina_url = f"https://r.jina.ai/{url}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(jina_url, headers=headers)
            if resp.status_code == 200:
                text = resp.text.strip()
                final_text = await summarize_long_text(text, url)
                return f"[Link Esterno: {url}]\nContenuto della pagina:\n{final_text}"
            else:
                return f"[Link: {url} | Errore: HTTP {resp.status_code}]"
    except Exception as e:
        logger.warning("LINK_JINA_ERROR url=%s err=%s", url, e)
        return f"[Link: {url} | Errore: non raggiungibile ({type(e).__name__})]"

async def explore_link(url: str) -> str:
    """Esplora un singolo link. Prova prima l'estrattore specifico (YouTube), poi fallback generico (Jina)."""
    yt_id = extract_youtube_id(url)
    if yt_id:
        yt_text = await explore_youtube(url, yt_id)
        if yt_text:
            return yt_text

    return await explore_jina(url)

async def explore_links_in_text(text: str) -> str:
    """Trova tutti i link nel testo, li esplora (riassumendoli se necessario) e appende le info."""
    if not text:
        return text

    urls = list(dict.fromkeys(URL_REGEX.findall(text)))
    if not urls:
        return text

    logger.info("LINK_EXPLORER_FOUND count=%d urls=%s", len(urls), urls)
    
    tasks = [explore_link(url) for url in urls[:3]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    summaries = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("LINK_EXPLORER_EXCEPTION err=%s", r)
            continue
        if r:
            summaries.append(r)
            
    if not summaries:
        return text
        
    summary_block = "\n\n[INFORMAZIONI ESTRATTE DAI LINK PRESENTI NEL MESSAGGIO:\n" + "\n\n".join(summaries) + "]"
    return text + summary_block
