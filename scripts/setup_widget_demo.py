#!/usr/bin/env python3
"""
GENESI WIDGET — Script di installazione guidata
================================================
Esegui questo script davanti al cliente per mostrare come si installa
il widget Genesi su qualsiasi sito intranet.

Lo script fa automaticamente:
  1. Verifica che il server Genesi sia raggiungibile
  2. Crea un account dedicato per il cliente
  3. Crea la API key aziendale
  4. Configura nome, colore e messaggio di benvenuto personalizzati
  5. Mostra lo snippet da incollare nel CMS (1 riga)
  6. Apre il sito intranet di test con il widget già attivo
  7. Verifica in live che il widget risponde

Uso:
  python scripts/setup_widget_demo.py
  python scripts/setup_widget_demo.py --url https://genesi.lucadigitale.eu
  python scripts/setup_widget_demo.py --url https://genesi.lucadigitale.eu --company "C-Place" --color "#0055a4"
"""

import asyncio
import aiohttp
import argparse
import sys
import os
import time
import json
import webbrowser

# Forza UTF-8 su Windows (evita UnicodeEncodeError con cp1252)
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── Config di default (modificabili da riga di comando) ──────────────────────
DEFAULT_URL      = "https://genesi.lucadigitale.eu"
DEFAULT_COMPANY  = "C-Place"
DEFAULT_COLOR    = "#0055a4"      # blu aziendale C-Place
DEFAULT_WELCOME  = "Ciao! Sono l'assistente di C-Place. Come posso aiutarti?"
DEFAULT_POSITION = "bottom-right"

# Admin credentials (solo per generare la chiave — il cliente non le vede)
ADMIN_EMAIL    = os.getenv("GENESI_ADMIN_EMAIL",    "alfio.turrisi@gmail.com")
ADMIN_PASSWORD = os.getenv("GENESI_ADMIN_PASSWORD", "ZOEennio0810")
# Token admin widget (per reset sito demo)
WIDGET_ADMIN_TOKEN = os.getenv("WIDGET_ADMIN_TOKEN", "1f0d01ce48a9f7e2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8")

# ─── Colori terminale ─────────────────────────────────────────────────────────
GREEN  = "\033[92m"
BLUE   = "\033[94m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def step(n, s):  print(f"\n{BOLD}{BLUE}[{n}]{RESET} {BOLD}{s}{RESET}")
def ok(s):       print(f"    {GREEN}OK  {s}{RESET}")
def err(s):      print(f"    {RED}ERR {s}{RESET}")
def info(s):     print(f"    {DIM}{s}{RESET}")
def snippet(s):  print(f"\n{CYAN}{s}{RESET}\n")
def sep():       print(f"\n{DIM}{'-'*60}{RESET}")


# ─── Installer ────────────────────────────────────────────────────────────────

class WidgetInstaller:

    def __init__(self, base_url: str, company: str, color: str, welcome: str, position: str, key_override: str = None, admin_token: str = None):
        self.base_url      = base_url.rstrip("/")
        self.company       = company
        self.color         = color
        self.welcome       = welcome
        self.position      = position
        self.key_override  = key_override   # se impostato, salta creazione account/key
        self.api_key       = self._make_key(company, key_override)
        self.admin_token   = admin_token or WIDGET_ADMIN_TOKEN
        self.token         = None
        self.session       = None

    def _make_key(self, company: str, key_override: str = None) -> str:
        """Genera una API key pulita dal nome azienda, oppure usa override."""
        if key_override:
            return key_override
        import re
        key = re.sub(r"[^a-zA-Z0-9]", "_", company.lower()).strip("_")
        return f"{key}_widget_2026"

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    async def _post(self, path: str, body: dict, auth: bool = False) -> tuple[int, dict]:
        h = {"Content-Type": "application/json"}
        if auth and self.token:
            h["Authorization"] = f"Bearer {self.token}"
        async with self.session.post(
            f"{self.base_url}{path}", json=body, headers=h,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            try:    data = await r.json()
            except: data = {"_raw": await r.text()}
            return r.status, data

    async def _patch(self, path: str, body: dict) -> tuple[int, dict]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        async with self.session.patch(
            f"{self.base_url}{path}", json=body, headers=h,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            try:    data = await r.json()
            except: data = {"_raw": await r.text()}
            return r.status, data

    async def _get(self, path: str, extra_headers: dict = None) -> tuple[int, dict]:
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra_headers:
            h.update(extra_headers)
        async with self.session.get(
            f"{self.base_url}{path}", headers=h,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            try:    data = await r.json()
            except: data = {"_raw": await r.text()}
            return r.status, data

    # ── Step 0: Reset sito demo ───────────────────────────────────────────────

    async def step0_reset_demo(self) -> bool:
        step(0, "Reset sito intranet di demo (stato pulito, senza widget)")
        try:
            async with self.session.post(
                f"{self.base_url}/api/widget/admin/demo/reset",
                headers={"X-Admin-Token": self.admin_token},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    n = len(data.get("restored", []))
                    ok(f"{n} file HTML ripristinati allo stato pulito")
                    return True
                else:
                    body = await r.text()
                    err(f"Reset fallito (HTTP {r.status}): {body[:80]}")
                    info("Continuando comunque — il sito potrebbe già essere pulito")
                    return True  # non blocca la demo
        except Exception as e:
            err(f"Errore reset: {e}")
            info("Continuando comunque")
            return True  # non blocca la demo

    # ── Step 1: Ping ──────────────────────────────────────────────────────────

    async def step1_ping(self) -> bool:
        step(1, "Connessione al server Genesi")
        info(f"URL: {self.base_url}")
        try:
            async with self.session.get(
                f"{self.base_url}/health",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status in (200, 404):  # 404 = server up ma /health non esiste
                    ok(f"Server raggiungibile (HTTP {r.status})")
                    return True
        except Exception as e:
            pass
        # Fallback: prova /api/widget/ping con chiave esistente
        try:
            async with self.session.get(
                f"{self.base_url}/api/widget/ping",
                headers={"X-Widget-Key": "demo_cplace_2026"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                ok(f"Server raggiungibile")
                return True
        except Exception as e:
            err(f"Server non raggiungibile: {e}")
            return False

    # ── Step 2: Login admin ────────────────────────────────────────────────────

    async def step2_login(self) -> bool:
        step(2, "Autenticazione admin")
        info(f"Account: {ADMIN_EMAIL}")
        status, data = await self._post("/auth/login", {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
        })
        if status == 200 and "access_token" in data:
            self.token = data["access_token"]
            ok("Login riuscito")
            return True
        else:
            err(f"Login fallito (HTTP {status}): {data}")
            return False

    # ── Step 3: Crea account widget ────────────────────────────────────────────

    async def step3_create_account(self) -> bool:
        step(3, f"Creazione account dedicato per {self.company}")
        widget_email    = f"widget_{self.api_key}@genesi.local"
        widget_password = f"Widget_{self.api_key}_2026!"
        info(f"Email: {widget_email}")

        status, data = await self._post("/auth/register", {
            "email": widget_email,
            "password": widget_password,
        })
        if status in (200, 201):
            ok(f"Account creato: {widget_email}")
        elif status == 409:
            ok(f"Account già esistente (riuso)")
        else:
            err(f"Registrazione fallita (HTTP {status}): {data}")
            return False

        # Salva le credenziali per il passo successivo
        self._widget_email    = widget_email
        self._widget_password = widget_password
        return True

    # ── Step 4: Crea API key ────────────────────────────────────────────────────

    async def step4_create_key(self) -> bool:
        step(4, f"Creazione API key aziendale")
        info(f"Chiave: {self.api_key}")

        status, data = await self._post(
            "/api/widget/admin/keys",
            {
                "key":      self.api_key,
                "email":    self._widget_email,
                "password": self._widget_password,
                "label":    self.company,
                "rate_limited": False,
            },
            auth=True,
        )
        if status == 201:
            ok(f"API key creata: {self.api_key}")
        elif status == 409:
            ok(f"API key già esistente (riuso)")
        else:
            err(f"Creazione key fallita (HTTP {status}): {data}")
            return False
        return True

    # ── Step 5: Configura visuale ──────────────────────────────────────────────

    async def step5_configure(self) -> bool:
        step(5, f"Configurazione interfaccia widget per {self.company}")
        info(f"Nome assistente : {self.company} Assistant")
        info(f"Colore brand    : {self.color}")
        info(f"Messaggio avvio : {self.welcome}")
        info(f"Posizione       : {self.position}")

        status, data = await self._patch(
            f"/api/widget/admin/config/{self.api_key}",
            {
                "name":        f"{self.company} Assistant",
                "color":       self.color,
                "welcome":     self.welcome,
                "position":    self.position,
                "placeholder": f"Chiedi qualcosa a {self.company}...",
            },
        )
        if status == 200:
            ok("Configurazione salvata sul server")
            return True
        else:
            err(f"Configurazione fallita (HTTP {status}): {data}")
            return False

    # ── Step 6: Mostra snippet ─────────────────────────────────────────────────

    def step6_show_snippet(self):
        step(6, "Snippet da incollare nel CMS")
        print(f"""
  {DIM}Questa è l'unica cosa che il cliente deve aggiungere al sito —{RESET}
  {DIM}una riga di codice, solitamente prima di </body>:{RESET}
""")
        tag = (
            f'<script\n'
            f'  src="{self.base_url}/widget.js"\n'
            f'  data-api-key="{self.api_key}"\n'
            f'  data-user-name="{{{{nome_utente_loggato}}}}"\n'
            f'  data-user-role="{{{{ruolo_utente}}}}">\n'
            f'</script>'
        )
        snippet(tag)
        info("• colore, nome e messaggio di benvenuto vengono dal server (step 5)")
        info("• nessun altro parametro necessario")
        info("• {{nome_utente_loggato}} va sostituito dal CMS con il nome reale")

    # ── Step 7: Apri demo intranet ─────────────────────────────────────────────

    async def step7_open_demo(self) -> bool:
        step(7, "Apertura sito intranet di test")
        demo_url = f"{self.base_url}/intranet-test"
        info(f"URL: {demo_url}")

        # Verifica che la pagina esista
        try:
            async with self.session.get(
                demo_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    ok("Sito intranet di test raggiungibile")
                else:
                    err(f"Pagina non trovata (HTTP {r.status})")
                    return False
        except Exception as e:
            err(f"Errore: {e}")
            return False

        # Apri nel browser
        try:
            webbrowser.open(demo_url)
            ok(f"Browser aperto → {demo_url}")
        except Exception:
            info(f"Apri manualmente: {demo_url}")
        return True

    # ── Step 8: Verifica live ──────────────────────────────────────────────────

    async def step8_verify(self) -> bool:
        step(8, "Verifica live — invio messaggio di prova")
        info("Invio: 'Ciao, chi sei?'")

        try:
            async with self.session.post(
                f"{self.base_url}/api/widget/chat",
                json={
                    "message":   "Ciao, chi sei?",
                    "user_name": "Demo Utente",
                    "user_role": "Test",
                },
                headers={"X-Widget-Key": self.api_key},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    reply = data.get("response", "")[:120]
                    ok(f"Risposta ricevuta:")
                    print(f"\n    {CYAN}\"{reply}\"{RESET}\n")
                    return True
                else:
                    body = await r.text()
                    err(f"HTTP {r.status}: {body[:100]}")
                    return False
        except Exception as e:
            err(f"Errore: {e}")
            return False

    # ── Riepilogo finale ───────────────────────────────────────────────────────

    def summary(self, steps_ok: list[bool]):
        sep()
        passed = sum(steps_ok)
        total  = len(steps_ok)
        color  = GREEN if passed == total else YELLOW
        label  = "COMPLETATA" if passed == total else "PARZIALE"

        print(f"\n{BOLD}  INSTALLAZIONE {label}{RESET}")
        print(f"  {color}{passed}/{total} step completati{RESET}\n")

        if passed == total:
            print(f"  {GREEN}{BOLD}Il widget e' attivo e configurato per {self.company}.{RESET}")
            print(f"  {GREEN}  Sito demo: {self.base_url}/intranet-test{RESET}")
            print(f"  {GREEN}  API key:   {self.api_key}{RESET}")
        else:
            print(f"  {YELLOW}Alcuni step non sono andati a buon fine.{RESET}")
            print(f"  {YELLOW}Verifica la connessione e le credenziali admin.{RESET}")
        sep()

    # ── Main ──────────────────────────────────────────────────────────────────

    async def run(self):
        print(f"\n{BOLD}{'='*60}")
        print(f"  GENESI WIDGET -- Installazione per {self.company}")
        print(f"{'='*60}{RESET}")
        print(f"  Server  : {self.base_url}")
        print(f"  Azienda : {self.company}")
        print(f"  Colore  : {self.color}")
        sep()

        self.session = aiohttp.ClientSession()
        steps_ok = []

        try:
            steps_ok.append(await self.step0_reset_demo())
            steps_ok.append(await self.step1_ping())
            if not steps_ok[-1]:
                print(f"\n{RED}Server non raggiungibile. Verifica URL e riprova.{RESET}\n")
                return

            steps_ok.append(await self.step2_login())
            if not steps_ok[-1]:
                print(f"\n{RED}Login fallito. Verifica GENESI_ADMIN_EMAIL e GENESI_ADMIN_PASSWORD.{RESET}\n")
                return

            if self.key_override:
                # Chiave esistente: salta creazione account/key
                info(f"  Modalità chiave esistente — skip step 3-4 (account/key già pronti)")
                steps_ok.append(True)  # step 3
                steps_ok.append(True)  # step 4
            else:
                steps_ok.append(await self.step3_create_account())
                steps_ok.append(await self.step4_create_key())
            steps_ok.append(await self.step5_configure())

            self.step6_show_snippet()
            steps_ok.append(True)

            steps_ok.append(await self.step7_open_demo())
            steps_ok.append(await self.step8_verify())

        finally:
            await self.session.close()

        self.summary(steps_ok)


# ─── Entry point ──────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Genesi Widget — Setup guidato")
    parser.add_argument("--url",      default=DEFAULT_URL,      help=f"URL server (default: {DEFAULT_URL})")
    parser.add_argument("--company",  default=DEFAULT_COMPANY,  help=f"Nome azienda (default: {DEFAULT_COMPANY})")
    parser.add_argument("--color",    default=DEFAULT_COLOR,    help=f"Colore brand hex (default: {DEFAULT_COLOR})")
    parser.add_argument("--welcome",  default=DEFAULT_WELCOME,  help="Messaggio di benvenuto")
    parser.add_argument("--position", default=DEFAULT_POSITION, choices=["bottom-right", "bottom-left"],
                        help="Posizione widget")
    parser.add_argument("--key", default=None,
                        help="Usa chiave esistente (salta creazione account/key)")
    parser.add_argument("--admin-token", default=None,
                        help="Token admin widget per reset demo (default: env WIDGET_ADMIN_TOKEN)")
    args = parser.parse_args()

    installer = WidgetInstaller(
        base_url=args.url,
        company=args.company,
        color=args.color,
        welcome=args.welcome,
        position=args.position,
        key_override=args.key,
        admin_token=args.admin_token,
    )
    await installer.run()


if __name__ == "__main__":
    asyncio.run(main())
