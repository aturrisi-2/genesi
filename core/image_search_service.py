"""
Ricerca immagini web per Genesi via DuckDuckGo (gratuito, no API key).
"""
import asyncio
import httpx
import logging
from typing import List, Optional
from dataclasses import dataclass
from ddgs import DDGS

logger = logging.getLogger(__name__)

IMAGE_SEARCH_TRIGGERS = [
    "mostrami immagini", "cerca foto", "immagini di",
    "foto di", "mostrami foto", "cerca immagini",
    "visualizza immagini", "show me images", "pictures of",
    "cercami immagini", "trova immagini", "cerca su web immagini"
]

@dataclass
class ImageResult:
    url: str
    title: str
    source: str
    thumbnail: str = ""
    width: int = 0
    height: int = 0

class ImageSearchService:
    PIXABAY_API_URL = "https://pixabay.com/api/"
    TIMEOUT = 10
    MAX_RESULTS = 4

    async def search(self, query: str, max_results: int = 4) -> List[ImageResult]:
        try:
            results = await self._pixabay_search(query, max_results)
            if results:
                logger.info("IMAGE_SEARCH_OK backend=pixabay query=%r results=%d", query, len(results))
                return results

            # Fallback: no API key / empty Pixabay response
            results = await self._duckduckgo_search(query, max_results)
            logger.info("IMAGE_SEARCH_OK backend=duckduckgo query=%r results=%d", query, len(results))
            return results
        except Exception as e:
            logger.warning("IMAGE_SEARCH_ERROR query=%r error=%s", query, e)
            return []

    async def _pixabay_search(self, query: str, max_results: int) -> List[ImageResult]:
        import os
        api_key = os.environ.get("PIXABAY_API_KEY", "")
        if not api_key:
            return []
        
        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            params = {
                "key": api_key,
                "q": query,
                "lang": "it",
                "image_type": "photo",
                "per_page": max_results,
                "safesearch": "true"
            }
            resp = await client.get(self.PIXABAY_API_URL, params=params)
            data = resp.json()
            
            results = []
            for item in data.get("hits", [])[:max_results]:
                results.append(ImageResult(
                    url=item["largeImageURL"],
                    title=item.get("tags", ""),
                    source="pixabay.com",
                    thumbnail=item["previewURL"],
                    width=item.get("imageWidth", 0),
                    height=item.get("imageHeight", 0)
                ))
            return results

    async def _duckduckgo_search(self, query: str, max_results: int) -> List[ImageResult]:
        def _do_search() -> List[dict]:
            with DDGS() as ddgs:
                return list(ddgs.images(
                    query,
                    max_results=max_results,
                    region="wt-wt",
                    safesearch="moderate"
                ))

        raw_results = await asyncio.to_thread(_do_search)
        results: List[ImageResult] = []
        for item in raw_results[:max_results]:
            image_url = item.get("image") or item.get("url") or item.get("thumbnail")
            if not image_url:
                continue
            results.append(ImageResult(
                url=image_url,
                title=item.get("title") or query,
                source=item.get("source") or "duckduckgo",
                thumbnail=item.get("thumbnail") or image_url,
                width=int(item.get("width", 0) or 0),
                height=int(item.get("height", 0) or 0),
            ))
        return results

def extract_image_query(message: str) -> Optional[str]:
    msg_lower = message.lower()
    for trigger in IMAGE_SEARCH_TRIGGERS:
        if trigger in msg_lower:
            idx = msg_lower.index(trigger) + len(trigger)
            query = message[idx:].strip().strip('?!.,')
            import re as _re
            query = _re.sub(r"^(di|del|della|degli|delle|dello|d'|su|sul|sulla) ", '', query, flags=_re.IGNORECASE).strip()
            if query:
                return query
    return None

_image_search_service = None

def get_image_search_service() -> ImageSearchService:
    global _image_search_service
    if _image_search_service is None:
        _image_search_service = ImageSearchService()
    return _image_search_service
