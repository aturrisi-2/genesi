import asyncio
import logging
import re
import os
import json
import socket
import ipaddress
import httpx
from urllib.parse import urlparse, urljoin
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)


async def _is_safe_public_url(url: str) -> bool:
    """Anti-SSRF: True solo se l'host risolve esclusivamente a IP pubblici.

    Blocca loopback, reti private, link-local (incl. 169.254.169.254 metadata
    cloud), multicast, reserved e unspecified. Fail-closed su qualsiasi errore.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(parsed.hostname, None)
        if not infos:
            return False
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
                return False
        return True
    except Exception as e:
        logger.warning("SSRF_GUARD_REJECT url=%s err=%s", url, e)
        return False

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

def is_msd_category(url: str) -> bool:
    """Rileva se un URL fa riferimento a una categoria di MSD Manuals."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    # Host-check ESATTO (no substring): evita bypass tipo msdmanuals.com.attacker.com
    if not (host == "msdmanuals.com" or host.endswith(".msdmanuals.com")):
        return False
    path_parts = [p for p in parsed.path.split('/') if p]
    # Una pagina di categoria di MSD ha solitamente 2 o 3 componenti di percorso:
    # /it/professionale/disturbi-dell-apparato-cardiovascolare (3)
    # /professional/cardiovascular-disorders (2)
    return len(path_parts) in (2, 3)

async def _fetch_article_for_manual(art_url: str, art_title: str, sem: asyncio.Semaphore) -> list:
    """Scarica il testo dell'articolo (tramite Jina o fallback HTTP) e lo divide in paragrafi."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    content = ""
    async with sem:
        try:
            jina_url = f"https://r.jina.ai/{art_url}"
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(jina_url, headers=headers)
                if resp.status_code == 200:
                    content = resp.text.strip()
        except Exception as e:
            logger.warning("Jina fetch failed for %s, trying direct HTTP: %s", art_url, e)

        if not content and await _is_safe_public_url(art_url):
            try:
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
                    resp = await client.get(art_url, headers=headers)
                    if resp.status_code == 200:
                        html = resp.text
                        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
                        clean_paras = []
                        for p in paragraphs:
                            clean_p = re.sub(r'<[^>]+>', '', p).strip()
                            clean_p = " ".join(clean_p.split())
                            if clean_p and len(clean_p) > 20:
                                clean_paras.append(clean_p)
                        content = "\n\n".join(clean_paras)
            except Exception as e:
                logger.error("Direct fallback fetch failed for %s: %s", art_url, e)

    if not content:
        return [{"title": art_title, "text": f"[Contenuto non disponibile per {art_url}]", "url": art_url}]

    raw_paragraphs = content.split('\n\n')
    chunks = []
    current_section = ""
    for para in raw_paragraphs:
        para = para.strip()
        if not para:
            continue
        if para.startswith('#'):
            current_section = para.lstrip('#').strip()
            continue
        para = re.sub(r'!\[.*?\]\(.*?\)', '', para)
        if len(para) < 20:
            continue
        title = f"{art_title} ({current_section})" if current_section else art_title
        chunks.append({
            "title": title,
            "text": para,
            "url": art_url
        })
    return chunks

async def crawl_and_save_msd_category_bg(url: str, category_slug: str):
    """Crawl asincrono in background per scaricare l'intera categoria medica."""
    try:
        logger.info("MSD_CRAWLER_START url=%s slug=%s", url, category_slug)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        if not await _is_safe_public_url(url):
            logger.error("MSD_CRAWLER_UNSAFE_URL url=%s", url)
            return
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.error("MSD_CRAWLER_INDEX_ERROR status=%d", resp.status_code)
                return
            html = resp.text

        parsed_url = urlparse(url)
        base_path = parsed_url.path.rstrip('/')
        path_parts = [p for p in base_path.split('/') if p]
        C = len(path_parts)

        link_pattern = re.compile(
            r'<a\s+[^>]*href=["\'](' + re.escape(base_path) + r'/[^"\']+)["\'][^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE
        )
        matches = link_pattern.findall(html)

        def clean_html(text):
            text = re.sub(r'<[^>]+>', '', text)
            return " ".join(text.split()).strip()

        articles_dict = {}
        for href, text in matches:
            link_path = href.split('#')[0]
            clean_txt = clean_html(text)
            if not clean_txt:
                continue
            parts = [p for p in link_path.split('/') if p]
            if len(parts) == C + 2:
                if link_path not in articles_dict:
                    articles_dict[link_path] = clean_txt

        all_articles = [(urljoin(url, path), title) for path, title in articles_dict.items()]
        logger.info("MSD_CRAWLER_FOUND_ARTICLES count=%d", len(all_articles))
        if not all_articles:
            return

        sem = asyncio.Semaphore(5)
        tasks = [_fetch_article_for_manual(art_url, art_title, sem) for art_url, art_title in all_articles]
        results = await asyncio.gather(*tasks)

        all_chunks = []
        for chunk_list in results:
            all_chunks.extend(chunk_list)

        manual_data = {
            "title": f"Manuale MSD - {category_slug.replace('-', ' ').title()}",
            "source_url": url,
            "sections": all_chunks
        }

        manuals_dir = "memory/manuals"
        os.makedirs(manuals_dir, exist_ok=True)
        filepath = os.path.join(manuals_dir, f"{category_slug}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(manual_data, f, ensure_ascii=False, indent=2)

        logger.info("MSD_CRAWLER_SUCCESS filepath=%s chunks=%d", filepath, len(all_chunks))
    except Exception as e:
        logger.error("MSD_CRAWLER_FATAL_ERROR error=%s", e, exc_info=True)

async def explore_link(url: str) -> str:
    """Esplora un singolo link. Prova prima l'estrattore specifico (MSD category, YouTube), poi fallback generico (Jina)."""
    if is_msd_category(url):
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]
        category_slug = path_parts[-1] if path_parts else "msd_manual"
        filepath = os.path.join("memory/manuals", f"{category_slug}.json")
        if os.path.exists(filepath):
            return f"[Link Categoria MSD: {url}]\n📚 Questa categoria medica è già presente e indicizzata nei miei manuali di sistema locali sul VPS."
        
        # Avvia il crawl asincrono in background
        asyncio.create_task(crawl_and_save_msd_category_bg(url, category_slug))
        return (
            f"[Link Categoria MSD: {url}]\n"
            f"📥 Ho rilevato un manuale medico di MSD Manuals. Ho avviato il download automatico e "
            f"l'indicizzazione di tutti gli articoli in background sul VPS. Saranno memorizzati localmente e "
            f"disponibili per la mia consultazione autonoma a breve."
        )

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
