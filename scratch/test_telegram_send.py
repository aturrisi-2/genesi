import sys
import os
import asyncio

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from core.telegram_bot import send_message, build_webapp_inline_keyboard

async def main():
    chat_id = 494065944  # Alfio's Telegram user ID
    text = "Questo è un messaggio di test con un bottone inline per Google."
    urls = ["https://google.com"]
    reply_markup = build_webapp_inline_keyboard(urls)
    
    print("Invio del messaggio...")
    await send_message(chat_id, text, reply_markup=reply_markup)
    print("Completato.")

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        try:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        except Exception:
            pass
    asyncio.run(main())
