import requests
import random
import time

BASE_URL = "http://127.0.0.1:8000"

EMAIL = "idappleturrisi@gmail.com"
PASSWORD = "Genesi123!"

MESSAGES = [
    "Ciao",
    "Come stai?",
    "Ho avuto una giornata difficile.",
    "Secondo te dovrei cambiare lavoro?",
    "Il mio cane si chiama Loki.",
    "Che ne pensi del mio carattere?",
    "Mi sento un po' stanco ultimamente.",
    "Ti ricordi come si chiama il mio cane?",
    "Oggi piove qui.",
    "Sto pensando di trasferirmi.",
    "Cosa abbiamo detto prima?",
]

def login():
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "email": EMAIL,
        "password": PASSWORD
    })
    if r.status_code != 200:
        print("Login fallito")
        return None
    return r.json()["access_token"]

def send_message(token, message):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{BASE_URL}/api/chat",
        json={"message": message},
        headers=headers
    )
    if r.status_code == 200:
        return r.json()["response"]
    return f"Errore {r.status_code}"

def run_simulation(turns=50):
    token = login()
    if not token:
        return

    print("Simulazione avviata...\n")

    for i in range(turns):
        msg = random.choice(MESSAGES)
        print(f"[USER] {msg}")
        response = send_message(token, msg)
        print(f"[GENESI] {response}\n")
        time.sleep(random.uniform(0.8, 2.0))

    print("Simulazione completata.")

if __name__ == "__main__":
    run_simulation(100)
