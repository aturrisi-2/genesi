#!/usr/bin/env python3
"""
GENESI MEDIA FEATURES TEST SUITE
Testa: upload immagini/documenti, contesto foto, priorità file recente,
       confronto multi-file, fotomontaggio intent, cleanup.

Uso:  python3 scripts/test_media_features.py
      python3 scripts/test_media_features.py alfio.turrisi@gmail.com ZOEennio0810
"""
import asyncio
import aiohttp
import json
import time
import re
import io
import os
import sys
import struct
import zlib
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

BASE_URL = "http://localhost:8000"
TEST_EMAIL = sys.argv[1] if len(sys.argv) > 1 else "alfio.turrisi@gmail.com"
TEST_PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "ZOEennio0810"

# ─── Colori ANSI ──────────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; RST = "\033[0m"; BOLD = "\033[1m"


# ─── Generazione immagini PNG sintetiche ──────────────────────────────────────
def _make_png(width: int, height: int, r: int, g: int, b: int, label: str = "") -> bytes:
    """Crea un PNG colorato minimale senza dipendenze esterne."""
    def _chunk(name: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + name + data
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return c + struct.pack(">I", crc)

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    # IDAT — righe pixel RGB
    raw_rows = b""
    for row in range(height):
        raw_rows += b"\x00"  # filter none
        for col in range(width):
            # pattern semplice: colore base con variazione per rendere le immagini distinguibili
            pr = min(255, r + (row * 2) % 30)
            pg = min(255, g + (col * 2) % 30)
            pb = min(255, b)
            raw_rows += bytes([pr, pg, pb])

    compressed = zlib.compress(raw_rows)
    idat = _chunk(b"IDAT", compressed)

    # tEXt chunk con label (leggibile da OCR se grande abbastanza)
    iend = _chunk(b"IEND", b"")

    sig = b"\x89PNG\r\n\x1a\n"
    return sig + ihdr + idat + iend


def make_red_image() -> bytes:
    """Immagine rossa 200x200 — 'immagine rossa con sfondo rosso'."""
    return _make_png(200, 200, 220, 50, 50)


def make_blue_image() -> bytes:
    """Immagine blu 200x200 — 'immagine blu con sfondo blu'."""
    return _make_png(200, 200, 50, 80, 220)


def make_green_image() -> bytes:
    """Immagine verde 200x200."""
    return _make_png(200, 200, 50, 200, 80)


def make_text_file(content: str) -> bytes:
    return content.encode("utf-8")


# ─── Dataclass risultato ──────────────────────────────────────────────────────
@dataclass
class TR:
    name: str
    passed: bool
    response: str = ""
    notes: str = ""
    latency_ms: float = 0


results: List[TR] = []


# ─── Tester ───────────────────────────────────────────────────────────────────
class MediaTester:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.log_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "genesi.log"
        )

    async def setup(self):
        connector = aiohttp.TCPConnector(limit=5)
        timeout = aiohttp.ClientTimeout(total=120)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        await self._login()

    async def teardown(self):
        if self.session:
            await self.session.close()

    async def _login(self):
        async with self.session.post(
            f"{BASE_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        ) as r:
            if r.status != 200:
                raise RuntimeError(f"Login failed {r.status}: {await r.text()}")
            data = await r.json()
            self.token = data["access_token"]
            print(f"{G}✅ Login OK{RST}")

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"}

    async def _get_logs(self, seconds: int = 30) -> str:
        result_lines = []
        cutoff = datetime.utcnow().timestamp() - seconds
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        ts_str = line[1:20]
                        line_dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                        if line_dt.timestamp() >= cutoff:
                            result_lines.append(line.rstrip())
                    except Exception:
                        pass
        except Exception:
            pass
        return "\n".join(result_lines)

    async def _log_contains(self, pattern: str, seconds: int = 30) -> bool:
        logs = await self._get_logs(seconds)
        return bool(re.search(pattern, logs, re.IGNORECASE))

    async def upload(self, filename: str, data: bytes, content_type: str = "image/png") -> dict:
        """Esegue upload e ritorna il JSON di risposta."""
        form = aiohttp.FormData()
        form.add_field("file", io.BytesIO(data), filename=filename, content_type=content_type)
        async with self.session.post(
            f"{BASE_URL}/api/upload/",
            data=form,
            headers=self._auth()
        ) as r:
            if r.status != 200:
                raise RuntimeError(f"Upload {r.status}: {await r.text()}")
            return await r.json()

    async def chat(self, message: str) -> dict:
        """Invia messaggio e ritorna JSON risposta."""
        async with self.session.post(
            f"{BASE_URL}/api/chat/",
            json={"message": message},
            headers=self._auth()
        ) as r:
            text = await r.text()
            if r.status != 200:
                raise RuntimeError(f"Chat {r.status}: {text}")
            return json.loads(text)

    def _record(self, name: str, passed: bool, response: str = "", notes: str = "",
                latency: float = 0):
        tr = TR(name=name, passed=passed, response=response[:300], notes=notes,
                latency_ms=latency)
        results.append(tr)
        icon = f"{G}✅{RST}" if passed else f"{R}❌{RST}"
        print(f"  {icon} {name}")
        if not passed:
            print(f"     {Y}→ {notes}{RST}")
            if response:
                print(f"     Risposta: {response[:200]}")

    # ══════════════════════════════════════════════════════════════════════════
    # GRUPPO 1 — Upload base immagine
    # ══════════════════════════════════════════════════════════════════════════
    async def test_image_upload_basic(self):
        print(f"\n{BOLD}{B}GRUPPO 1 — Upload immagine base{RST}")

        t0 = time.time()
        try:
            result = await self.upload("test_rosso.png", make_red_image())
            lat = (time.time() - t0) * 1000

            # 1.1 Risposta breve senza descrizione automatica
            response_text = result.get("response", "")
            short_ok = "dimmi cosa vuoi fare" in response_text.lower() or "caricata" in response_text.lower()
            no_desc = len(response_text) < 200  # non deve essere una descrizione lunga
            self._record(
                "1.1 Risposta breve (no descrizione auto)",
                short_ok and no_desc,
                response_text,
                f"len={len(response_text)} short_ok={short_ok}",
                lat
            )

            # 1.2 doc_id presente
            self._record("1.2 doc_id restituito", bool(result.get("doc_id")),
                        str(result.get("doc_id")))

            # 1.3 tipo corretto
            self._record("1.3 type=image", result.get("type") == "image",
                        str(result.get("type")))

            # 1.4 image_data_url presente (serve per editing)
            has_url = bool(result.get("image_data_url")) or \
                      bool((result.get("meta") or {}).get("image_data_url"))
            self._record("1.4 image_data_url disponibile", has_url,
                        "data_url: " + str(bool(result.get("image_data_url"))))

            # 1.5 active_documents aggiornati
            active = result.get("active_documents", [])
            self._record("1.5 active_documents popolati", len(active) >= 1,
                        str(active))

            # 1.6 Log upload
            await asyncio.sleep(1)
            log_ok = await self._log_contains("DOCUMENT_SAVED|UPLOAD_VALIDATED", 15)
            self._record("1.6 Log DOCUMENT_SAVED presente", log_ok)

        except Exception as e:
            self._record("1.x Upload immagine", False, notes=str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # GRUPPO 2 — Contesto immagine in chat
    # ══════════════════════════════════════════════════════════════════════════
    async def test_image_context_in_chat(self):
        print(f"\n{BOLD}{B}GRUPPO 2 — Contesto immagine in chat{RST}")

        try:
            # Carica immagine rossa
            await self.upload("test_rosso.png", make_red_image())
            await asyncio.sleep(2)

            t0 = time.time()
            reply = await self.chat("cosa vedi nella foto?")
            lat = (time.time() - t0) * 1000
            resp_text = reply.get("response", reply.get("text", ""))

            # 2.1 Risposta non generica
            not_generic = not any(k in resp_text.lower() for k in [
                "non ho accesso", "non posso vedere", "non ho ricevuto",
                "nessun file", "nessuna immagine"
            ])
            self._record("2.1 Genesi accede al contenuto immagine", not_generic,
                        resp_text, "risposta generica rilevata" if not not_generic else "", lat)

            # 2.2 Risposta non vuota
            self._record("2.2 Risposta non vuota", len(resp_text) > 20, resp_text)

            # 2.3 Log DOCUMENT_CONTEXT_INJECTED
            await asyncio.sleep(1)
            log_ok = await self._log_contains("DOCUMENT_CONTEXT_INJECTED", 20)
            self._record("2.3 Log DOCUMENT_CONTEXT_INJECTED", log_ok)

        except Exception as e:
            self._record("2.x Contesto immagine", False, notes=str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # GRUPPO 3 — Priorità file più recente
    # ══════════════════════════════════════════════════════════════════════════
    async def test_recent_file_priority(self):
        print(f"\n{BOLD}{B}GRUPPO 3 — Priorità file più recente{RST}")

        try:
            # Carica prima immagine rossa, poi verde
            r1 = await self.upload("immagine_rossa.png", make_red_image())
            await asyncio.sleep(1)
            r2 = await self.upload("immagine_verde.png", make_green_image())
            await asyncio.sleep(2)

            # 3.1 Entrambe in active_documents
            active_ids = [d["doc_id"] for d in r2.get("active_documents", [])]
            both_present = len(active_ids) >= 2
            self._record("3.1 Entrambe le immagini in active_documents",
                        both_present, str(active_ids))

            # 3.2 La più recente è ultima nella lista (append order)
            if both_present:
                last_doc = r2.get("active_documents", [])[-1]
                is_verde = "verde" in last_doc.get("filename", "").lower()
                self._record("3.2 Immagine più recente in ultima posizione",
                            is_verde or last_doc.get("doc_id") == r2.get("doc_id"),
                            str(last_doc))
            else:
                self._record("3.2 Immagine più recente in ultima posizione",
                            False, "active_documents insufficienti")

            # 3.3 Genesi risponde sulla più recente (verde) quando non specificato
            reply = await self.chat("cosa c'è nella foto?")
            resp_text = reply.get("response", reply.get("text", ""))
            # La risposta deve essere coerente (non rifiuto)
            not_generic = not any(k in resp_text.lower() for k in [
                "non ho accesso", "non posso vedere", "non ho ricevuto"
            ])
            self._record("3.3 Risposta coerente per file più recente",
                        not_generic and len(resp_text) > 20, resp_text)

        except Exception as e:
            self._record("3.x Priorità file recente", False, notes=str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # GRUPPO 4 — Confronto multi-immagine
    # ══════════════════════════════════════════════════════════════════════════
    async def test_compare_images(self):
        print(f"\n{BOLD}{B}GRUPPO 4 — Confronto multi-immagine{RST}")

        try:
            await self.upload("img_rossa.png", make_red_image())
            await asyncio.sleep(1)
            await self.upload("img_blu.png", make_blue_image())
            await asyncio.sleep(2)

            t0 = time.time()
            reply = await self.chat("confronta le due immagini che ho caricato")
            lat = (time.time() - t0) * 1000
            resp_text = reply.get("response", reply.get("text", ""))

            # 4.1 Risposta non rifiuta il confronto
            not_refused = not any(k in resp_text.lower() for k in [
                "non ho accesso", "non posso", "non ho ricevuto"
            ])
            self._record("4.1 Confronto non rifiutato", not_refused, resp_text,
                        "", lat)

            # 4.2 Risposta abbastanza lunga (dovrebbe descrivere entrambe)
            rich = len(resp_text) > 80
            self._record("4.2 Risposta ricca per confronto", rich, resp_text[:200])

            # 4.3 Log per entrambi i doc iniettati
            await asyncio.sleep(1)
            log_ok = await self._log_contains("DOCUMENT_CONTEXT_INJECTED", 20)
            self._record("4.3 Log DOCUMENT_CONTEXT_INJECTED presente", log_ok)

        except Exception as e:
            self._record("4.x Confronto immagini", False, notes=str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # GRUPPO 5 — Upload documento testo + domanda
    # ══════════════════════════════════════════════════════════════════════════
    async def test_text_document(self):
        print(f"\n{BOLD}{B}GRUPPO 5 — Documento testo{RST}")

        doc_content = (
            "RICETTA SEGRETA TIRAMISÙ DELLA NONNA\n\n"
            "Ingredienti:\n"
            "- 500g mascarpone\n"
            "- 4 uova\n"
            "- 200g savoiardi\n"
            "- Caffè amaro q.b.\n"
            "- 100g zucchero\n"
            "- Cacao amaro per decorare\n\n"
            "Procedimento: montare i tuorli con lo zucchero, aggiungere il mascarpone, "
            "incorporare gli albumi montati a neve. Inzuppare i savoiardi nel caffè, "
            "alternare con la crema, spolverare di cacao. Refrigerare 4 ore."
        )

        try:
            result = await self.upload("ricetta_tiramisu.txt", make_text_file(doc_content),
                                      "text/plain")

            # 5.1 Tipo corretto
            self._record("5.1 type=text", result.get("type") == "text", str(result.get("type")))

            # 5.2 Risposta breve senza descrizione completa
            resp = result.get("response", "")
            self._record("5.2 Risposta breve doc testo", len(resp) < 300 and "cosa vuoi" in resp.lower(),
                        resp)

            await asyncio.sleep(2)

            # 5.3 Chiedi ingredienti
            reply = await self.chat("quali ingredienti ci sono nella ricetta del tiramisù?")
            resp_text = reply.get("response", reply.get("text", ""))
            has_ingredient = any(k in resp_text.lower() for k in [
                "mascarpone", "savoiardi", "uova", "caffè", "zucchero"
            ])
            self._record("5.3 Genesi risponde con ingredienti dal documento",
                        has_ingredient, resp_text[:200])

            # 5.4 Chiedi procedimento
            reply2 = await self.chat("come si prepara?")
            resp2 = reply2.get("response", reply2.get("text", ""))
            has_steps = any(k in resp2.lower() for k in [
                "montare", "mascarpone", "savoiardi", "caffè", "cacao", "refriger"
            ])
            self._record("5.4 Genesi risponde con procedimento dal documento",
                        has_steps, resp2[:200])

        except Exception as e:
            self._record("5.x Documento testo", False, notes=str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # GRUPPO 6 — Intent fotomontaggio → image_generation
    # ══════════════════════════════════════════════════════════════════════════
    async def test_photomontage_intent(self):
        print(f"\n{BOLD}{B}GRUPPO 6 — Routing intent fotomontaggio{RST}")

        # Prima caricare un'immagine
        try:
            await self.upload("base_foto.png", make_red_image())
            await asyncio.sleep(2)
        except Exception as e:
            self._record("6.0 Setup upload", False, notes=str(e))
            return

        cases = [
            ("crea un fotomontaggio con questa immagine", "image_generation"),
            ("modifica la foto e aggiungi la neve", "image_generation"),
            ("genera un'immagine di un tramonto sul mare", "image_generation"),
            ("ritocca la foto", "image_generation"),
        ]

        for msg, expected_intent in cases:
            try:
                t0 = time.time()
                reply = await self.chat(msg)
                lat = (time.time() - t0) * 1000
                actual_intent = reply.get("intent", "")
                resp_text = reply.get("response", reply.get("text", ""))

                # Verifica: intent corretto O log IMAGE_GENERATION
                await asyncio.sleep(1)
                log_ok = await self._log_contains(
                    r"ROUTING_DECISION.*route=image_generation|IMAGE_GENERATION", 20
                )
                intent_ok = actual_intent == expected_intent or log_ok

                # La risposta non deve essere un rifiuto
                not_refused = "non sono in grado" not in resp_text.lower() and \
                              "non posso modificare" not in resp_text.lower()

                self._record(
                    f"6.x [{msg[:40]}]",
                    intent_ok and not_refused,
                    resp_text[:150],
                    f"intent={actual_intent} log={log_ok} not_refused={not_refused}",
                    lat
                )
                await asyncio.sleep(3)  # evita flood
            except Exception as e:
                self._record(f"6.x [{msg[:40]}]", False, notes=str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # GRUPPO 7 — Persistenza active_documents tra richieste
    # ══════════════════════════════════════════════════════════════════════════
    async def test_persistence(self):
        print(f"\n{BOLD}{B}GRUPPO 7 — Persistenza documenti{RST}")

        try:
            # Upload
            r = await self.upload("persist_test.png", make_blue_image())
            doc_id = r.get("doc_id")
            await asyncio.sleep(2)

            # Prima domanda
            reply1 = await self.chat("cosa c'è nella foto?")
            resp1 = reply1.get("response", reply1.get("text", ""))
            ok1 = len(resp1) > 20 and "non ho accesso" not in resp1.lower()
            self._record("7.1 Prima domanda accede all'immagine", ok1, resp1[:150])

            await asyncio.sleep(2)

            # Seconda domanda (stesso contesto, doc deve restare attivo)
            reply2 = await self.chat("dimmi qualcosa di più sull'immagine che ho caricato")
            resp2 = reply2.get("response", reply2.get("text", ""))
            ok2 = len(resp2) > 20 and "non ho accesso" not in resp2.lower()
            self._record("7.2 Seconda domanda (persistenza contesto)", ok2, resp2[:150])

        except Exception as e:
            self._record("7.x Persistenza", False, notes=str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # GRUPPO 8 — Upload multiplo (max 10, più vecchi rimossi)
    # ══════════════════════════════════════════════════════════════════════════
    async def test_max_active_documents(self):
        print(f"\n{BOLD}{B}GRUPPO 8 — Limite documenti attivi (max 10){RST}")

        try:
            last_result = None
            for i in range(4):  # Non carichiamo 11 — basta verificare che N>1 funziona
                img = make_red_image() if i % 2 == 0 else make_blue_image()
                last_result = await self.upload(f"bulk_{i}.png", img)
                await asyncio.sleep(0.5)

            active = last_result.get("active_documents", [])
            # Devono essere presenti (non svuotati)
            self._record("8.1 Documenti multipli in active_documents",
                        len(active) >= 2, str(len(active)) + " docs")

            # Max 10
            self._record("8.2 Non supera max 10",
                        len(active) <= 10, str(len(active)))

        except Exception as e:
            self._record("8.x Max documenti", False, notes=str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # GRUPPO 9 — No analisi automatica (Genesi aspetta input)
    # ══════════════════════════════════════════════════════════════════════════
    async def test_no_auto_analysis(self):
        print(f"\n{BOLD}{B}GRUPPO 9 — No analisi automatica dopo upload{RST}")

        try:
            result = await self.upload("no_auto.png", make_green_image())
            resp = result.get("response", "")

            # La risposta non deve contenere descrizione dettagliata
            no_auto_desc = not any(k in resp.lower() for k in [
                "l'immagine mostra", "si vede", "nella foto", "colore", "sfondo",
                "chiaramente", "visibile", "ocr", "descrizione"
            ])
            self._record("9.1 Nessuna descrizione automatica nella risposta upload",
                        no_auto_desc, resp)

            # Deve contenere invito all'azione
            has_cta = any(k in resp.lower() for k in [
                "cosa vuoi", "dimmi", "fammi sapere"
            ])
            self._record("9.2 Invito all'azione presente",
                        has_cta, resp)

        except Exception as e:
            self._record("9.x No auto analysis", False, notes=str(e))


# ─── Runner principale ────────────────────────────────────────────────────────
async def run_all():
    print(f"\n{BOLD}{'═'*60}{RST}")
    print(f"{BOLD}  GENESI MEDIA FEATURES TEST SUITE{RST}")
    print(f"  Utente: {TEST_EMAIL}")
    print(f"  Server: {BASE_URL}")
    print(f"{BOLD}{'═'*60}{RST}")

    tester = MediaTester()
    try:
        await tester.setup()
    except Exception as e:
        print(f"{R}❌ Setup fallito: {e}{RST}")
        return

    try:
        await tester.test_no_auto_analysis()
        await tester.test_image_upload_basic()
        await tester.test_image_context_in_chat()
        await tester.test_recent_file_priority()
        await tester.test_compare_images()
        await tester.test_text_document()
        await tester.test_photomontage_intent()
        await tester.test_persistence()
        await tester.test_max_active_documents()
    finally:
        await tester.teardown()

    # ─── Riepilogo finale ────────────────────────────────────────────────────
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    score_pct = int(100 * passed / total) if total else 0

    print(f"\n{BOLD}{'═'*60}{RST}")
    print(f"{BOLD}  RISULTATI FINALI{RST}")
    print(f"{'═'*60}")

    for r in results:
        icon = f"{G}✅{RST}" if r.passed else f"{R}❌{RST}"
        lat = f" [{r.latency_ms:.0f}ms]" if r.latency_ms > 0 else ""
        print(f"  {icon} {r.name}{lat}")
        if not r.passed and r.notes:
            print(f"     {Y}→ {r.notes}{RST}")

    print(f"\n{'═'*60}")
    color = G if score_pct >= 80 else (Y if score_pct >= 60 else R)
    print(f"{BOLD}  Score: {color}{passed}/{total} ({score_pct}%){RST}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    asyncio.run(run_all())
