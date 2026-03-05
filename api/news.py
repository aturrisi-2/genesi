import logging
from typing import Dict, List
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/news", tags=["news"])

TIMEOUT_SECONDS = 8
MAX_ITEMS = 14

SOURCE_FEEDS: Dict[str, List[str]] = {
    "italy": [
        "https://news.google.com/rss?hl=it&gl=IT&ceid=IT:it",
        "https://www.ansa.it/sito/ansait_rss.xml",
    ],
    "world": [
        "https://news.google.com/rss/headlines/section/topic/WORLD?hl=it&gl=IT&ceid=IT:it",
        "https://news.google.com/rss?hl=it&gl=IT&ceid=IT:it",
    ],
    "technology": [
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=it&gl=IT&ceid=IT:it",
        "https://www.ansa.it/sito/notizie/tecnologia/tecnologia_rss.xml",
    ],
}


def _is_safe_http_url(raw_url: str) -> bool:
    try:
        parsed = urlparse(raw_url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def _extract_items_from_xml(xml_text: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    if not xml_text.strip():
        return items

    root = ET.fromstring(xml_text)

    # RSS 2.0: <channel><item>...</item></channel>
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and _is_safe_http_url(link):
            items.append({"title": title, "link": link})

    # Atom fallback: <entry><title>...</title><link href="..."/></entry>
    if not items:
        atom_ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", atom_ns):
            title = (entry.findtext("atom:title", default="", namespaces=atom_ns) or "").strip()
            link_el = entry.find("atom:link", atom_ns)
            link = (link_el.get("href") if link_el is not None else "") or ""
            link = link.strip()
            if title and _is_safe_http_url(link):
                items.append({"title": title, "link": link})

    return items


@router.get("/ticker")
async def get_ticker_news(
    source: str = Query("italy", pattern="^(italy|world|technology)$"),
):
    feeds = SOURCE_FEEDS.get(source, SOURCE_FEEDS["italy"])
    collected: List[Dict[str, str]] = []
    seen_links = set()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
            for feed_url in feeds:
                try:
                    resp = await client.get(feed_url)
                    resp.raise_for_status()
                    feed_items = _extract_items_from_xml(resp.text)
                except Exception as feed_error:
                    logger.warning("NEWS_FEED_ERROR source=%s feed=%s err=%s", source, feed_url, feed_error)
                    continue

                for item in feed_items:
                    link = item["link"]
                    if link in seen_links:
                        continue
                    seen_links.add(link)
                    collected.append(item)
                    if len(collected) >= MAX_ITEMS:
                        break

                if len(collected) >= MAX_ITEMS:
                    break
    except Exception as exc:
        logger.error("NEWS_TICKER_FATAL source=%s err=%s", source, exc)

    return JSONResponse(
        content={
            "ok": True,
            "source": source,
            "items": collected,
        }
    )
