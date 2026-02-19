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
    DDG_URL = "https://duckduckgo.com/"
    DDG_IMAGES_URL = "https://duckduckgo.com/i.js"
    TIMEOUT = 10
    MAX_RESULTS = 4

    async def search(self, query: str, max_results: int = 4) -> List[ImageResult]:
        try:
            results = await self._ddg_search(query, max_results)
            print(f"IMAGE_SEARCH_OK query={query!r} results={len(results)}")
            return results
        except Exception as e:
            print(f"IMAGE_SEARCH_ERROR query={query!r} error={e}")
            return []

    async def _ddg_search(self, query: str, max_results: int) -> List[ImageResult]:
        async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(self.DDG_URL, params={"q": query})
            vqd_match = re.search(r'vqd=([\d-]+)', resp.text)
            if not vqd_match:
                raise ValueError("vqd token non trovato")
            vqd = vqd_match.group(1)

            headers = {"Referer": "https://duckduckgo.com/", "Accept": "application/json"}
            params = {"l": "it-it", "o": "json", "q": query, "vqd": vqd, "f": ",,,", "p": "1"}
            resp = await client.get(self.DDG_IMAGES_URL, params=params, headers=headers)
            data = resp.json()

            results = []
            for item in data.get("results", [])[:max_results]:
                if item.get("image"):
                    results.append(ImageResult(
                        url=item["image"],
                        title=item.get("title", ""),
                        source=item.get("source", ""),
                        thumbnail=item.get("thumbnail", ""),
                        width=item.get("width", 0),
                        height=item.get("height", 0)
                    ))
            return results

def extract_image_query(message: str) -> Optional[str]:
    msg_lower = message.lower()
    for trigger in IMAGE_SEARCH_TRIGGERS:
        if trigger in msg_lower:
            idx = msg_lower.index(trigger) + len(trigger)
            query = message[idx:].strip().strip('?!.,')
            if query:
                return query
    return None

_image_search_service = None

def get_image_search_service() -> ImageSearchService:
    global _image_search_service
    if _image_search_service is None:
        _image_search_service = ImageSearchService()
    return _image_search_service
