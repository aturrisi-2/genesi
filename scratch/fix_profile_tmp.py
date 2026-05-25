import json
from pathlib import Path

profile_path = Path("/opt/genesi/memory/profile/fd037393-3e28-49f1-a125-e7b50c469871.json")
data = {
  "user_id": "fd037393-3e28-49f1-a125-e7b50c469871",
  "email": "alfio.turrisi@gmail.com",
  "name": "Alfio",
  "city": "Roma",
  "timezone": "Europe/Rome",
  "profession": "Sviluppatore",
  "spouse": "Rita",
  "children": [
    {"name": "Zoe"},
    {"name": "Ennio"}
  ],
  "pets": [
    {"type": "cat", "name": "Mignolo"},
    {"type": "cat", "name": "Prof"},
    {"type": "dog", "name": "Rio"}
  ],
  "interests": [],
  "preferences": [],
  "traits": []
}

with open(profile_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("SUCCESS: fd037393-3e28-49f1-a125-e7b50c469871.json written cleanly!")
