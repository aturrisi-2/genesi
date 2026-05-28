import httpx
import sys

def main():
    token = "EAANpF9ZA0xfUBRNrSf7Ax24UohbDMpbyqz7DDDrv5kVx08pTCidKsGiSVkDsWkHMcZA6r2kjo9Y3vzdizZA8WruslQHYCfKUfO0VHN1ZCHo7FkksfA762EbjoAU4S6nrv9UJ9FjY4rabD3UrtmL7IU0j3Ty95vEbLBrMD8oEhuWw0BTsMrhR0ywsO1d1UgZDZD"
    phone_id = "1094888310365993"
    to_num = "393920681099"
    
    url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_num,
        "type": "text",
        "text": {
            "body": "Test da Antigravity! La connessione e il token sono validi?"
        }
    }
    
    print(f"Invio richiesta POST a {url}...")
    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=10)
        print(f"Status Code: {r.status_code}")
        print(f"Response Headers: {dict(r.headers)}")
        print(f"Response Body: {r.text}")
    except Exception as e:
        print(f"Errore durante l'invio: {e}")

if __name__ == "__main__":
    main()
