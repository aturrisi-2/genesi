"""
Ricerca immagini web per Genesi via DuckDuckGo (gratuito, no API key).
"""
import httpx
import re
from typing import List, Optional
from dataclasses import dataclass

IMAGE_SEARCH_TRIGGERS = [
    "mostrami immagini", "cerca foto", "immagini di",
    "foto di", "mostrami foto", "cerca immagini",
    "visualizza immagini", "show me images", "pictures of"
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
            print(f"IMAGE_SEARCH_OK query={query!r} results={len(results)}")
            return results
        except Exception as e:
            print(f"IMAGE_SEARCH_ERROR query={query!r} error={e}")
            return []

    async def _pixabay_search(self, query: str, max_results: int) -> List[ImageResult]:
        import os
        api_key = os.environ.get("PIXABAY_API_KEY", "")
        if not api_key:
            raise ValueError("PIXABAY_API_KEY non configurata")
        
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

def extract_image_query(message: str) -> Optional[str]:
    msg_lower = message.lower()
    for trigger in IMAGE_SEARCH_TRIGGERS:
        if trigger in msg_lower:
            idx = msg_lower.index(trigger) + len(trigger)
            query = message[idx:].strip().strip('?!.,')
            import re as _re
            query = _re.sub(r"^(di|del|della|degli|delle|dello|d') ", '', query, flags=_re.IGNORECASE).strip()
            if query:
                return query
    return None

_image_search_service = None

def get_image_search_service() -> ImageSearchService:
    global _image_search_service
    if _image_search_service is None:
        _image_search_service = ImageSearchService()
    return _image_search_service
