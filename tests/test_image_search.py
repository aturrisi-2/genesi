import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.image_search_service import ImageSearchService, ImageResult, extract_image_query, IMAGE_SEARCH_TRIGGERS

def test_triggers_exist():
    assert "mostrami immagini" in IMAGE_SEARCH_TRIGGERS
    assert "cerca foto" in IMAGE_SEARCH_TRIGGERS
    assert "immagini di" in IMAGE_SEARCH_TRIGGERS

def test_extract_query():
    assert extract_image_query("mostrami immagini di gatti") == "gatti"
    assert extract_image_query("cerca foto di Roma") == "Roma"
    assert extract_image_query("ciao come stai") is None

def test_image_result():
    r = ImageResult(url="https://example.com/img.jpg", title="Test", source="example.com")
    assert r.url.startswith("https://")

def test_service_config():
    svc = ImageSearchService()
    assert svc.MAX_RESULTS == 4
    assert svc.TIMEOUT == 10

if __name__ == "__main__":
    test_triggers_exist()
    test_extract_query()
    test_image_result()
    test_service_config()
    print("✅ All image search tests passed")
