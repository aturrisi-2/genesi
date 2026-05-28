import urllib.request
import json

data = {
    "message": {
        "chat": {
            "id": 12345,
            "type": "private"
        },
        "from": {
            "id": 12345,
            "first_name": "Luca"
        },
        "text": "ciao"
    }
}

req = urllib.request.Request(
    "http://localhost:8000/api/telegram/webhook",
    data=json.dumps(data).encode(),
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except Exception as e:
    print(f"Error: {e}")
