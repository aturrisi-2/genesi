import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set console output encoding to utf-8 if on Windows
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

from core.telegram_bot import (
    get_default_reply_markup,
    get_domain_name,
    extract_webapp_urls,
    build_webapp_inline_keyboard,
    clean_markdown_links
)

def test_default_reply_markup():
    print("Testing get_default_reply_markup...")
    markup = get_default_reply_markup("private")
    assert markup is not None
    assert "keyboard" in markup
    assert markup["resize_keyboard"] is True
    assert markup["is_persistent"] is True
    assert len(markup["keyboard"]) == 2
    assert markup["keyboard"][0][0]["text"] == "🌦️ Meteo"
    assert markup["keyboard"][0][1]["text"] == "📅 Impegni"
    assert markup["keyboard"][1][0]["text"] == "🎂 Compleanni"
    assert markup["keyboard"][1][1]["text"] == "❓ Aiuto"
    
    assert get_default_reply_markup("group") is None
    print("[OK] get_default_reply_markup")

def test_get_domain_name():
    print("Testing get_domain_name...")
    assert get_domain_name("https://www.ilmeteo.it/roma") == "ilmeteo.it"
    assert get_domain_name("https://google.com") == "google.com"
    # Long domain truncation
    long_url = "https://verylongdomainnameforthiswebpage.com/path"
    assert get_domain_name(long_url) == "verylongdomainnam..."
    print("[OK] get_domain_name")

def test_extract_webapp_urls():
    print("Testing extract_webapp_urls...")
    text_with_links = (
        "Ciao! Ti consiglio di guardare il meteo su https://www.ilmeteo.it/roma, "
        "oppure visita il sito https://wikipedia.org. Ecco un'immagine: https://example.com/photo.jpg"
    )
    urls = extract_webapp_urls(text_with_links)
    print("Extracted URLs:", urls)
    
    assert "https://www.ilmeteo.it/roma" in urls
    assert "https://wikipedia.org" in urls
    assert "https://example.com/photo.jpg" not in urls  # Ignored image URL
    
    # Strip punctuation and parentheses
    text_ends_with_link = "Visita (https://google.com)."
    urls2 = extract_webapp_urls(text_ends_with_link)
    assert urls2 == ["https://google.com"]

    # HTTP to HTTPS translation
    text_http = "Sito: http://it.wikipedia.org/wiki/Papa"
    urls3 = extract_webapp_urls(text_http)
    assert urls3 == ["https://it.wikipedia.org/wiki/Papa"]

    # support www. links
    text_www = "Visita www.google.com o anche il sito www.wikipedia.org/wiki/Papa."
    urls4 = extract_webapp_urls(text_www)
    assert "https://www.google.com" in urls4
    assert "https://www.wikipedia.org/wiki/Papa" in urls4

    # support markdown links extraction
    text_md = "Vedi [Wikipedia del Papa](https://it.wikipedia.org/wiki/Papa_Francesco) o anche [Google](www.google.com)."
    urls5 = extract_webapp_urls(text_md)
    assert "https://it.wikipedia.org/wiki/Papa_Francesco" in urls5
    assert "https://www.google.com" in urls5 or "https://google.com" in urls5

    print("[OK] extract_webapp_urls")

def test_clean_markdown_links():
    print("Testing clean_markdown_links...")
    text = "Ecco la pagina di [Wikipedia su Papa Francesco](https://it.wikipedia.org/wiki/Papa_Francesco) per te, o vedi [Google](www.google.com)."
    cleaned = clean_markdown_links(text)
    print("Cleaned text:", cleaned)
    assert cleaned == "Ecco la pagina di Wikipedia su Papa Francesco per te, o vedi Google."
    print("[OK] clean_markdown_links")

def test_build_webapp_inline_keyboard():
    print("Testing build_webapp_inline_keyboard...")
    urls = ["https://google.com", "https://wikipedia.org"]
    markup = build_webapp_inline_keyboard(urls)
    assert "inline_keyboard" in markup
    assert len(markup["inline_keyboard"]) == 2
    assert markup["inline_keyboard"][0][0]["text"] == "🌐 Apri google.com"
    assert markup["inline_keyboard"][0][0]["web_app"]["url"] == "https://google.com"
    assert markup["inline_keyboard"][1][0]["text"] == "🌐 Apri wikipedia.org"
    assert markup["inline_keyboard"][1][0]["web_app"]["url"] == "https://wikipedia.org"
    print("[OK] build_webapp_inline_keyboard")

if __name__ == "__main__":
    try:
        test_default_reply_markup()
        test_get_domain_name()
        test_extract_webapp_urls()
        test_clean_markdown_links()
        test_build_webapp_inline_keyboard()
        print("\nALL TESTS PASSED SUCCESSFULLY!")
    except AssertionError as e:
        print("\nTEST FAILED:", e)
        sys.exit(1)
    except Exception as e:
        print("\nERROR RUNNING TESTS:", e)
        sys.exit(1)
