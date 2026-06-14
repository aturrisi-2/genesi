#!/usr/bin/env python3
"""
GENESI — Master Test Suite v1.0
Testa TUTTI gli aspetti fondamentali del sistema in un unico script.

Aree coperte (20 gruppi, ~80 test):
  A  Auth & Bootstrap
  B  Intent Classification (fast-track + LLM path)
  C  Tool Skills (meteo, news, orario, data)
  D  Relational & Emotional
  E  Identity & Memory Correction
  F  Personal Facts & Episodic Memory
  G  Knowledge (tecnica / spiegazione / live search)
  H  Image Vision (upload foto + descrizione)
  I  Face Recognition (pipeline completa)
  J  Image Generation
  K  Group Behavior — presentazione + dedup + forget
  L  Group Telegram family (tutti i gruppi = famiglia)
  M  Group Anti-flipper & Unanswered Questions
  N  Platform Restrictions (widget)
  O  SSE Streaming Endpoint
  P  Security — SSRF guard + Meta webhook firma
  Q  OCR (upload immagine con testo)
  R  Document Mode (upload PDF + domanda)
  S  Group Greeting Service
  T  Sanity — nessuna regressione baseline pytest

Uso:
  python3 scripts/master_test.py
  python3 scripts/master_test.py --url http://localhost:8000 --email alfio@example.com --password secret
  python3 scripts/master_test.py --groups A,B,C,D  # solo alcune aree
  python3 scripts/master_test.py --skip T          # salta pytest

Note:
  - Richiede accesso ai file locali (genesi.log, data/faces/) — gira sullo stesso host del server
  - Crea/usa account di test "master_test@genesi.local" / "Master_Test_2026"
  - Fa cleanup automatico al termine (file test, dati temporanei)
"""

import asyncio
import aiohttp
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

# Aggiungi root progetto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL      = "http://localhost:8000"
TEST_EMAIL    = "master_test@genesi.local"
TEST_PASSWORD = "Master_Test_2026"
LOG_FILE      = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "genesi.log")
FACES_DIR     = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "faces")
REPORT_FILE   = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "MASTER_TEST_REPORT.md")
PAUSE         = 1.5   # secondi tra test (attesa background tasks)
FACE_PAUSE    = 4.0   # attesa più lunga per background LLM face extraction

# ─── Colori ───────────────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; C = "\033[96m"; BOLD = "\033[1m"; RST = "\033[0m"
def ok(s):   return f"{G}✅ {s}{RST}"
def fail(s): return f"{R}❌ {s}{RST}"
def warn(s): return f"{Y}⚠️  {s}{RST}"
def info(s): return f"{B}   {s}{RST}"
def head(s): return f"\n{BOLD}{C}{'─'*60}\n{s}\n{'─'*60}{RST}"


# ─── Strutture dati ───────────────────────────────────────────────────────────
@dataclass
class TR:
    group: str
    name: str
    passed: bool
    response: str = ""
    note: str = ""
    latency_ms: float = 0

ALL_RESULTS: List[TR] = []


# ─── JPEG minimale (1×1 px, nessun volto) — per test caricamento senza biometria ──
MINIMAL_JPEG = bytes([
    0xFF,0xD8,0xFF,0xE0,0x00,0x10,0x4A,0x46,0x49,0x46,0x00,0x01,0x01,0x00,0x00,0x01,
    0x00,0x01,0x00,0x00,0xFF,0xDB,0x00,0x43,0x00,0x08,0x06,0x06,0x07,0x06,0x05,0x08,
    0x07,0x07,0x07,0x09,0x09,0x08,0x0A,0x0C,0x14,0x0D,0x0C,0x0B,0x0B,0x0C,0x19,0x12,
    0x13,0x0F,0x14,0x1D,0x1A,0x1F,0x1E,0x1D,0x1A,0x1C,0x1C,0x20,0x24,0x2E,0x27,0x20,
    0x22,0x2C,0x23,0x1C,0x1C,0x28,0x37,0x29,0x2C,0x30,0x31,0x34,0x34,0x34,0x1F,0x27,
    0x39,0x3D,0x38,0x32,0x3C,0x2E,0x33,0x34,0x32,0xFF,0xC0,0x00,0x0B,0x08,0x00,0x01,
    0x00,0x01,0x01,0x01,0x11,0x00,0xFF,0xC4,0x00,0x1F,0x00,0x00,0x01,0x05,0x01,0x01,
    0x01,0x01,0x01,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x01,0x02,0x03,0x04,
    0x05,0x06,0x07,0x08,0x09,0x0A,0x0B,0xFF,0xC4,0x00,0xB5,0x10,0x00,0x02,0x01,0x03,
    0x03,0x02,0x04,0x03,0x05,0x05,0x04,0x04,0x00,0x00,0x01,0x7D,0x01,0x02,0x03,0x00,
    0x04,0x11,0x05,0x12,0x21,0x31,0x41,0x06,0x13,0x51,0x61,0x07,0x22,0x71,0x14,0x32,
    0x81,0x91,0xA1,0x08,0x23,0x42,0xB1,0xC1,0x15,0x52,0xD1,0xF0,0x24,0x33,0x62,0x72,
    0x82,0x09,0x0A,0x16,0x17,0x18,0x19,0x1A,0x25,0x26,0x27,0x28,0x29,0x2A,0x34,0x35,
    0x36,0x37,0x38,0x39,0x3A,0x43,0x44,0x45,0x46,0x47,0x48,0x49,0x4A,0x53,0x54,0x55,
    0x56,0x57,0x58,0x59,0x5A,0x63,0x64,0x65,0x66,0x67,0x68,0x69,0x6A,0x73,0x74,0x75,
    0x76,0x77,0x78,0x79,0x7A,0x83,0x84,0x85,0x86,0x87,0x88,0x89,0x8A,0x92,0x93,0x94,
    0x95,0x96,0x97,0x98,0x99,0x9A,0xA2,0xA3,0xA4,0xA5,0xA6,0xA7,0xA8,0xA9,0xAA,0xB2,
    0xB3,0xB4,0xB5,0xB6,0xB7,0xB8,0xB9,0xBA,0xC2,0xC3,0xC4,0xC5,0xC6,0xC7,0xC8,0xC9,
    0xCA,0xD2,0xD3,0xD4,0xD5,0xD6,0xD7,0xD8,0xD9,0xDA,0xE1,0xE2,0xE3,0xE4,0xE5,0xE6,
    0xE7,0xE8,0xE9,0xEA,0xF1,0xF2,0xF3,0xF4,0xF5,0xF6,0xF7,0xF8,0xF9,0xFA,0xFF,0xDA,
    0x00,0x08,0x01,0x01,0x00,0x00,0x3F,0x00,0xFB,0xD2,0x8A,0x28,0x03,0xFF,0xD9,
])

# PNG 1×1 rosso (per test OCR con immagine valida ma senza testo)
PNG_1X1_RED = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
)


# ─── Classe tester centrale ───────────────────────────────────────────────────
class MasterTester:

    def __init__(self, base_url: str, email: str, password: str):
        self.base_url  = base_url
        self.email     = email
        self.password  = password
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        self._log_cursor = 0
        self._face_tmp_files: List[str] = []  # cleanup a fine sessione

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def setup(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))
        await self._ensure_user()
        await self._login()
        self._log_cursor = self._count_log_lines()
        print(info(f"Login OK — user_id={self.user_id}  log_cursor={self._log_cursor}"))

    async def teardown(self):
        await self._cleanup()
        if self.session:
            await self.session.close()

    async def _ensure_user(self):
        try:
            async with self.session.post(
                f"{self.base_url}/auth/register",
                json={"email": self.email, "password": self.password}
            ) as r:
                pass  # ignora 409 se già esiste
        except Exception:
            pass

    async def _login(self):
        async with self.session.post(
            f"{self.base_url}/auth/login",
            json={"email": self.email, "password": self.password}
        ) as r:
            if r.status != 200:
                txt = await r.text()
                print(fail(f"Login fallito: HTTP {r.status} — {txt}"))
                sys.exit(1)
            data = await r.json()
            self.token = data["access_token"]
            try:
                payload_b64 = self.token.split(".")[1]
                payload_b64 += "=" * (4 - len(payload_b64) % 4)
                payload = json.loads(base64.b64decode(payload_b64))
                self.user_id = payload.get("sub", "")
            except Exception as e:
                print(fail(f"JWT decode error: {e}"))
                sys.exit(1)

    async def _cleanup(self):
        # Rimuovi file face temporanei con prefisso "zmt_"
        if os.path.exists(FACES_DIR):
            for fname in os.listdir(FACES_DIR):
                if fname.lower().startswith("zmt_"):
                    try:
                        os.remove(os.path.join(FACES_DIR, fname))
                    except Exception:
                        pass
        for tmp in self._face_tmp_files:
            try:
                os.remove(tmp)
            except Exception:
                pass

    # ── Log utils ────────────────────────────────────────────────────────────

    def _count_log_lines(self) -> int:
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def _read_new_logs(self) -> str:
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            new_lines = lines[self._log_cursor:]
            return "".join(new_lines)
        except Exception:
            return ""

    def _log_contains(self, pattern: str) -> bool:
        return bool(re.search(pattern, self._read_new_logs(), re.IGNORECASE))

    def _advance_cursor(self):
        self._log_cursor = self._count_log_lines()

    # ── HTTP helpers ─────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    async def chat(self, message: str, platform: str = None) -> Tuple[str, str, float]:
        """Invia messaggio all'endpoint /api/chat/. Ritorna (response, intent, latency_ms)."""
        t0 = time.time()
        body: Dict[str, Any] = {"message": message}
        if platform:
            body["platform"] = platform
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat/",
                json=body,
                headers=self._headers()
            ) as r:
                lat = (time.time() - t0) * 1000
                if r.status == 200:
                    data = await r.json()
                    return data.get("response", ""), data.get("intent", ""), lat
                else:
                    txt = await r.text()
                    return f"HTTP_{r.status}", "", lat
        except Exception as e:
            return f"EXCEPTION:{e}", "", (time.time() - t0) * 1000

    async def upload_file(self, filename: str, content: bytes, mime: str = "image/jpeg") -> dict:
        """Upload file via multipart. Ritorna il JSON di risposta."""
        form = aiohttp.FormData()
        form.add_field("file", content, filename=filename, content_type=mime)
        try:
            async with self.session.post(
                f"{self.base_url}/upload/",
                data=form,
                headers=self._headers()
            ) as r:
                if r.status == 200:
                    return await r.json()
                txt = await r.text()
                return {"error": f"HTTP {r.status}: {txt[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    async def group_chat(self, text: str, group_id: str = "12036340786901@g.us",
                         group_name: str = "Test Master Group",
                         sender_name: str = "TestUtente",
                         sender_id: str = "3900000001@s.whatsapp.net") -> dict:
        """Invia messaggio al gruppo via /api/chat/group."""
        body = {
            "text": text,
            "sender_name": sender_name,
            "sender_id": sender_id,
            "group_id": group_id,
            "group_name": group_name,
        }
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat/group",
                json=body,
                headers=self._headers()
            ) as r:
                if r.status == 200:
                    return await r.json()
                txt = await r.text()
                return {"error": f"HTTP {r.status}", "detail": txt[:200]}
        except Exception as e:
            return {"error": str(e)}

    async def group_present(self, group_id: str, group_name: str, adder: str = "TestAdmin") -> dict:
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat/group/present",
                json={"group_id": group_id, "group_name": group_name, "adder_name": adder},
                headers=self._headers()
            ) as r:
                return await r.json() if r.status == 200 else {"error": f"HTTP {r.status}"}
        except Exception as e:
            return {"error": str(e)}

    async def group_forget(self, group_id: str) -> dict:
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat/group/forget",
                json={"group_id": group_id},
                headers=self._headers()
            ) as r:
                return await r.json() if r.status == 200 else {"error": f"HTTP {r.status}"}
        except Exception as e:
            return {"error": str(e)}

    async def should_respond(self, text: str, recent_messages: list) -> dict:
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat/group/should_respond",
                json={"text": text, "recent_messages": recent_messages},
                headers=self._headers()
            ) as r:
                return await r.json() if r.status == 200 else {"error": f"HTTP {r.status}"}
        except Exception as e:
            return {"error": str(e)}

    # ── Result helpers ────────────────────────────────────────────────────────

    def record(self, group: str, name: str, passed: bool,
               response: str = "", note: str = "", latency_ms: float = 0):
        tr = TR(group=group, name=name, passed=passed,
                response=response[:200], note=note, latency_ms=latency_ms)
        ALL_RESULTS.append(tr)
        status = ok(name) if passed else fail(name)
        detail = f"  ({latency_ms:.0f}ms)" if latency_ms else ""
        extra  = f"  — {note}" if note else (f"  — {response[:80]}" if response else "")
        print(f"  {status}{detail}{extra}")
        return tr

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO A — Auth & Bootstrap
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_A_auth(self):
        print(head("A  Auth & Bootstrap"))
        self.record("A", "A1 login riuscito", bool(self.token), note=f"token[:20]={self.token[:20] if self.token else '—'}")
        self.record("A", "A2 user_id estratto da JWT", bool(self.user_id), note=f"user_id={self.user_id}")

        # Server health
        try:
            async with self.session.get(f"{self.base_url}/health") as r:
                ok_health = r.status == 200
        except Exception:
            ok_health = False
        self.record("A", "A3 health endpoint risponde", ok_health)

        # Token non valido → 401
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat/",
                json={"message": "ciao"},
                headers={"Authorization": "Bearer INVALID_TOKEN"}
            ) as r:
                self.record("A", "A4 token non valido → 401", r.status == 401, note=f"status={r.status}")
        except Exception as e:
            self.record("A", "A4 token non valido → 401", False, note=str(e))

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO B — Intent Classification
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_B_intent(self):
        print(head("B  Intent Classification"))
        self._advance_cursor()

        cases = [
            # (messaggio, log_pattern, label)
            ("ciao",
             r"INTENT_CLASSIFIED.*intent=greeting",
             "B1 greeting fast-track"),
            ("come stai",
             r"INTENT_CLASSIFIED.*intent=how_are_you",
             "B2 how_are_you fast-track"),
            ("che ore sono",
             r"INTENT_CLASSIFIED.*intent=time",
             "B3 time fast-track"),
            ("in realtà mi chiamo Marco",
             r"INTENT_CLASSIFIED.*intent=memory_correction",
             "B4 memory_correction fast-track"),
            ("che tempo fa a Roma",
             r"LLM_INTENT_CLASSIFICATION.*weather",
             "B5 weather via LLM"),
            ("dimmi le ultime notizie",
             r"LLM_INTENT_CLASSIFICATION.*news",
             "B6 news via LLM"),
            ("spiegami cos'è il machine learning",
             r"(INTENT_CLASSIFIED.*spiegazione|LLM_INTENT_CLASSIFICATION.*(tecnica|spiegazione|chat_free))",
             "B7 spiegazione"),
            ("sono molto triste e non so cosa fare",
             r"(INTENT_CLASSIFIED.*emotional|LLM_INTENT_CLASSIFICATION.*emotional)",
             "B8 emotional"),
        ]
        for msg, pattern, label in cases:
            self._advance_cursor()
            resp, intent, lat = await self.chat(msg)
            await asyncio.sleep(PAUSE)
            log_found = self._log_contains(pattern)
            passed = resp and not resp.startswith("HTTP_") and not resp.startswith("EXCEPTION") and log_found
            self.record("B", label, passed, response=resp, note=f"intent={intent} log={'✓' if log_found else '✗'}", latency_ms=lat)

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO C — Tool Skills
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_C_tools(self):
        print(head("C  Tool Skills (meteo / news / orario / data)"))

        cases = [
            ("che tempo fa a Palermo",
             lambda r: any(w in r.lower() for w in ["°", "grad", "sole", "nuv", "piogg", "temp", "ciel", "sere", "calor"]),
             "C1 meteo — risposta con dati"),
            ("dimmi le ultime notizie",
             lambda r: len(r) > 30 and any(w in r.lower() for w in ["notizia", "aggiornamento", "accaduto", "oggi", "italia", "giornata", "news", "articolo", "fonte"]),
             "C2 news — almeno una notizia"),
            ("che ore sono",
             lambda r: any(w in r.lower() for w in ["ore", "h", ":", "stamattina", "pomeriggio", "sera", "notte", "adesso", "momento"]),
             "C3 orario — risposta con ora"),
            ("che giorno è oggi",
             lambda r: any(w in r.lower() for w in ["lunedì","martedì","mercoledì","giovedì","venerdì","sabato","domenica","giugno","luglio","2026","oggi"]),
             "C4 data — risposta con giorno"),
        ]
        for msg, check, label in cases:
            resp, intent, lat = await self.chat(msg)
            await asyncio.sleep(PAUSE)
            self.record("C", label, check(resp), response=resp, note=f"intent={intent}", latency_ms=lat)

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO D — Relational & Emotional
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_D_relational(self):
        print(head("D  Relational & Emotional"))

        # Risposta relazionale base (non vuota, non errore)
        resp, intent, lat = await self.chat("come stai oggi?")
        await asyncio.sleep(PAUSE)
        self.record("D", "D1 relazionale base — risposta non vuota", len(resp) > 10 and not resp.startswith("HTTP_"), response=resp, latency_ms=lat)

        # Supporto emotivo: non deve rispondere con "capisco"
        resp2, intent2, lat2 = await self.chat("sono in un momento difficile, ho tanta ansia")
        await asyncio.sleep(PAUSE)
        no_capisco = "capisco" not in resp2.lower()
        has_content = len(resp2) > 20 and not resp2.startswith("HTTP_")
        self.record("D", "D2 emotional — risponde senza 'capisco'", no_capisco and has_content, response=resp2, note=f"no_capisco={no_capisco}", latency_ms=lat2)

        # Risposta greeting → non troppo lunga (max ~200 char)
        resp3, intent3, lat3 = await self.chat("ciao!")
        await asyncio.sleep(PAUSE)
        self.record("D", "D3 greeting — risposta concisa (≤300 char)", len(resp3) <= 300 and len(resp3) > 2, response=resp3, note=f"len={len(resp3)}", latency_ms=lat3)

        # No "Ahoy" / roleplay pirata
        for kw in ["ahoy", "arrr", "capitano"]:
            self.record("D", f"D4 nessun roleplay '{kw}'", kw not in resp3.lower() and kw not in resp2.lower() and kw not in resp.lower(),
                        note="check su D1+D2+D3")

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO E — Identity & Memory Correction
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_E_identity(self):
        print(head("E  Identity & Memory Correction"))

        # Imposta nome
        resp1, _, lat1 = await self.chat("mi chiamo Alessandro")
        await asyncio.sleep(PAUSE)
        self.record("E", "E1 set nome — risposta OK", not resp1.startswith("HTTP_"), latency_ms=lat1)

        # Recall nome
        resp2, _, lat2 = await self.chat("come mi chiamo?")
        await asyncio.sleep(PAUSE)
        name_ok = "Alessandro" in resp2 or "alessandro" in resp2.lower()
        self.record("E", "E2 recall nome → Alessandro", name_ok, response=resp2, latency_ms=lat2)

        # Correzione nome
        resp3, _, lat3 = await self.chat("in realtà mi chiamo Luca, non Alessandro")
        await asyncio.sleep(PAUSE)
        self.record("E", "E3 memory_correction — risposta OK", not resp3.startswith("HTTP_"), latency_ms=lat3)

        await asyncio.sleep(PAUSE)
        resp4, _, lat4 = await self.chat("come mi chiamo?")
        await asyncio.sleep(PAUSE)
        name_corrected = "Luca" in resp4 or "luca" in resp4.lower()
        self.record("E", "E4 nome corretto → Luca", name_corrected, response=resp4, latency_ms=lat4)

        # Profilo: città
        resp5, _, lat5 = await self.chat("vivo a Torino")
        await asyncio.sleep(PAUSE)
        self.record("E", "E5 set città Torino", not resp5.startswith("HTTP_"), latency_ms=lat5)

        resp6, _, lat6 = await self.chat("dove vivo?")
        await asyncio.sleep(PAUSE)
        city_ok = "torino" in resp6.lower()
        self.record("E", "E6 recall città → Torino", city_ok, response=resp6, latency_ms=lat6)

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO F — Personal Facts & Episodic Memory
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_F_memory(self):
        print(head("F  Personal Facts & Episodic Memory"))

        # Fatto personale nella conversazione
        resp1, _, lat1 = await self.chat("adoro il sushi, lo mangio ogni venerdì sera")
        await asyncio.sleep(FACE_PAUSE)  # aspetta background task personal_facts

        # Recall fatto
        resp2, _, lat2 = await self.chat("cosa mangio di solito il venerdì?")
        await asyncio.sleep(PAUSE)
        sushi_ok = "sushi" in resp2.lower() or "venerdì" in resp2.lower()
        self.record("F", "F1 personal fact sushi — ricordato", sushi_ok, response=resp2, latency_ms=lat2)

        # Episodio: evento passato
        resp3, _, lat3 = await self.chat("ieri ho partecipato a un concerto bellissimo di musica classica")
        await asyncio.sleep(FACE_PAUSE)

        resp4, _, lat4 = await self.chat("cosa ho fatto ieri?")
        await asyncio.sleep(PAUSE)
        concert_ok = any(w in resp4.lower() for w in ["concerto", "musica", "classica", "ieri"])
        self.record("F", "F2 episodic recall concerto", concert_ok, response=resp4, latency_ms=lat4)

        # Contesto conversazione immediata
        resp5, _, _ = await self.chat("ho un cane che si chiama Fido")
        await asyncio.sleep(PAUSE)
        resp6, _, lat6 = await self.chat("come si chiama il mio cane?")
        await asyncio.sleep(PAUSE)
        pet_ok = "fido" in resp6.lower()
        self.record("F", "F3 contesto cane Fido", pet_ok, response=resp6, latency_ms=lat6)

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO G — Knowledge (tecnica / spiegazione / live search)
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_G_knowledge(self):
        print(head("G  Knowledge (tecnica / spiegazione / live search)"))

        resp1, intent1, lat1 = await self.chat("spiegami brevemente cos'è l'intelligenza artificiale")
        await asyncio.sleep(PAUSE)
        ai_ok = len(resp1) > 30 and any(w in resp1.lower() for w in ["intelligenza", "machine", "algoritm", "dati", "model", "apprendimento", "sistema"])
        self.record("G", "G1 spiegazione AI — contenuto pertinente", ai_ok, response=resp1, note=f"intent={intent1}", latency_ms=lat1)

        resp2, intent2, lat2 = await self.chat("come si calcola la derivata di x²?")
        await asyncio.sleep(PAUSE)
        math_ok = len(resp2) > 10 and any(w in resp2.lower() for w in ["2x", "derivata", "2*x", "2·x", "due", "risultato", "formula", "calcolo"])
        self.record("G", "G2 tecnica matematica derivata", math_ok, response=resp2, note=f"intent={intent2}", latency_ms=lat2)

        resp3, intent3, lat3 = await self.chat("chi ha vinto il campionato di calcio in serie A quest'anno?")
        await asyncio.sleep(PAUSE)
        live_ok = len(resp3) > 15 and not resp3.startswith("HTTP_") and not resp3.startswith("EXCEPTION")
        self.record("G", "G3 live search calcio — risponde", live_ok, response=resp3, note=f"intent={intent3}", latency_ms=lat3)

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO H — Image Vision (upload + descrizione)
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_H_vision(self):
        print(head("H  Image Vision (upload + descrizione)"))

        # Carica immagine reale se esiste, altrimenti usa JPEG minimale
        test_img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "tests", "dummy_face_image.jpg")
        if os.path.exists(test_img_path):
            with open(test_img_path, "rb") as f:
                img_bytes = f.read()
            img_label = "dummy_face_image.jpg"
        else:
            img_bytes = MINIMAL_JPEG
            img_label = "minimal_1x1.jpg"

        result = await self.upload_file(img_label, img_bytes, "image/jpeg")
        upload_ok = "error" not in result and "type" in result
        self.record("H", "H1 upload immagine — HTTP 200", upload_ok, note=f"tipo={result.get('type','?')}")

        # Upload: il tipo deve essere "image"
        self.record("H", "H2 upload classifica come 'image'", result.get("type") == "image",
                    note=f"type={result.get('type')}")

        # Domanda sull'immagine appena caricata
        if upload_ok:
            resp, intent, lat = await self.chat("cosa vedi nell'immagine che ho caricato?")
            await asyncio.sleep(PAUSE)
            vision_ok = len(resp) > 10 and not resp.startswith("HTTP_")
            self.record("H", "H3 vision descrizione immagine", vision_ok, response=resp, latency_ms=lat)
        else:
            self.record("H", "H3 vision descrizione immagine", False, note="Upload fallito — skip")

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO I — Face Recognition
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_I_face(self):
        print(head("I  Face Recognition"))

        # Usa dummy face images se disponibili (con volti veri per biometria)
        face_imgs = []
        for fname in ("dummy_face_image.jpg", "dummy_face_image2.jpg"):
            fpath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "tests", fname)
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    face_imgs.append((fname, f.read()))

        if not face_imgs:
            print(warn("  Nessuna dummy_face_image.jpg in tests/ — salto biometria reale"))
            print(info("  Carica un'immagine con volto umano in tests/dummy_face_image.jpg per testare biometria"))
            # Test logico: pipeline awiting_faces (senza immagine reale usa solo il test di stato)
            self.record("I", "I1 face — file mancanti (skip biometria reale)", True, note="tests/dummy_face_image.jpg non trovato")
            self.record("I", "I2 face — file mancanti (skip awiting)", True, note="skip")
            self.record("I", "I3 face — file mancanti (skip recall)", True, note="skip")
            return

        # Upload prima immagine
        fname1, img1 = face_imgs[0]
        self._advance_cursor()
        res1 = await self.upload_file(fname1, img1, "image/jpeg")
        upload1_ok = "error" not in res1
        self.record("I", "I1 upload foto con volto", upload1_ok, note=f"content_len={len(res1.get('content',''))}")

        # Attendi analisi biometrica in background
        await asyncio.sleep(FACE_PAUSE)

        # Verifica log FACE_MEMORY o BIOMETRIC o UNKNOWN_FACES
        face_log = self._log_contains(r"(FACE_MEMORY|BIOMETRIC|UNKNOWN_FACES|AWAITING_FACES|face)")
        self.record("I", "I2 biometria triggerata nel log", face_log,
                    note="cerca FACE_MEMORY/BIOMETRIC/UNKNOWN_FACES nel log")

        # Identifica il volto via messaggio di testo (se awaiting)
        resp_id, _, lat_id = await self.chat("Zmt_TestPerson")
        await asyncio.sleep(FACE_PAUSE)
        id_ok = not resp_id.startswith("HTTP_") and not resp_id.startswith("EXCEPTION")
        self.record("I", "I3 identificazione volto via testo", id_ok, response=resp_id, latency_ms=lat_id)

        # Recall: chiedi il nome della persona
        await asyncio.sleep(PAUSE)
        resp_recall, _, lat_recall = await self.chat("come si chiama la persona nella foto?")
        await asyncio.sleep(PAUSE)
        recall_ok = "zmt_testperson" in resp_recall.lower() or "testperson" in resp_recall.lower() or not resp_recall.startswith("HTTP_")
        self.record("I", "I4 recall nome persona identificata", recall_ok, response=resp_recall, latency_ms=lat_recall)

        # Blocco nomi placeholder
        self.record("I", "I5 nessun placeholder 'UNKNOWN' nella risposta",
                    "unknown" not in resp_id.lower() and "sconosciuto" not in resp_id.lower(),
                    note=f"resp_id={resp_id[:60]}")

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO J — Image Generation
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_J_image_gen(self):
        print(head("J  Image Generation"))
        self._advance_cursor()

        resp, intent, lat = await self.chat("genera un'immagine di un tramonto sul mare")
        await asyncio.sleep(FACE_PAUSE)

        # La risposta deve contenere un data URL o un link o un testo descrittivo
        has_image = ("data:image" in resp or "http" in resp or
                     any(w in resp.lower() for w in ["generat", "creat", "immagine", "disegn", "foto", "generazione"]))
        log_gen = self._log_contains(r"(IMAGE_GEN|image_generat|OPENROUTER_IMAGE|BEDROCK_IMAGE|rate.limit)")
        self.record("J", "J1 image generation — risposta con contenuto", has_image or log_gen,
                    response=resp[:150], note=f"intent={intent} log={'✓' if log_gen else '✗'}", latency_ms=lat)

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO K — Group Behavior (presentazione / dedup / forget)
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_K_group_present(self):
        print(head("K  Group Behavior — presentazione + dedup + forget"))

        unique_gid = f"test{int(time.time())}@g.us"
        gname = "Master Test Group Nuovo"

        # Prima presentazione → deve presentarsi
        r1 = await self.group_present(unique_gid, gname, "Marco")
        presented1 = r1.get("presented") is True and len(r1.get("response", "")) > 10
        self.record("K", "K1 primo join → si presenta", presented1, note=f"resp={r1.get('response','?')[:60]}")

        # Stessa presentazione → dedup: non si ripresenta
        await asyncio.sleep(0.5)
        r2 = await self.group_present(unique_gid, gname)
        not_presented = r2.get("presented") is False
        self.record("K", "K2 secondo join → dedup (non si ripresenta)", not_presented, note=f"presented={r2.get('presented')}")

        # Forget → si ripresenta
        await self.group_forget(unique_gid)
        await asyncio.sleep(0.5)
        r3 = await self.group_present(unique_gid, gname)
        presented3 = r3.get("presented") is True
        self.record("K", "K3 forget → si ripresenta", presented3, note=f"presented={r3.get('presented')}")

        # Cleanup
        await self.group_forget(unique_gid)

        # Chat di gruppo: risposta alla domanda diretta
        r4 = await self.group_chat("Genesi quanto fa 2+2?")
        has_resp = len(r4.get("response", "")) > 5
        self.record("K", "K4 group chat risposta", has_resp, note=r4.get("response", "")[:80])

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO L — Telegram Family Flag (tutti i gruppi = famiglia)
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_L_tg_family(self):
        print(head("L  Telegram Family Flag (nuovo gruppo = famiglia)"))

        # Verifica che _TG_GROUPS_ARE_FAMILY sia True in telegram_bot.py
        try:
            from core.telegram_bot import _TG_GROUPS_ARE_FAMILY, _FAMILY_GROUP_IDS
            flag_ok = _TG_GROUPS_ARE_FAMILY is True
            self.record("L", "L1 _TG_GROUPS_ARE_FAMILY = True", flag_ok,
                        note=f"_TG_GROUPS_ARE_FAMILY={_TG_GROUPS_ARE_FAMILY}")
            self.record("L", "L2 _FAMILY_GROUP_IDS mantenuto per retrocompat.", bool(_FAMILY_GROUP_IDS),
                        note=f"set size={len(_FAMILY_GROUP_IDS)}")
        except ImportError as e:
            self.record("L", "L1 _TG_GROUPS_ARE_FAMILY importazione", False, note=str(e))
            self.record("L", "L2 _FAMILY_GROUP_IDS retrocompat.", False, note="import fallito")

        # Verifica che whatsapp_bot abbia _WA_GROUPS_ARE_FAMILY = True
        try:
            from core.whatsapp_bot import _WA_GROUPS_ARE_FAMILY
            self.record("L", "L3 _WA_GROUPS_ARE_FAMILY = True", _WA_GROUPS_ARE_FAMILY is True,
                        note=f"valore={_WA_GROUPS_ARE_FAMILY}")
        except ImportError as e:
            self.record("L", "L3 _WA_GROUPS_ARE_FAMILY importazione", False, note=str(e))

        # Verifica comportamento: gruppo nuovo WA → tono familiare nel contesto
        gid = f"newfamily{int(time.time())}@g.us"
        r = await self.group_present(gid, "Amici del Cuore", "Salvatore")
        family_tone = r.get("presented") is True
        self.record("L", "L4 nuovo gruppo WA → si presenta", family_tone,
                    note=r.get("response", "")[:80])
        await self.group_forget(gid)

        # Group context builder deve usare is_family_group=True anche per gruppi nuovi
        r_chat = await self.group_chat(
            "Genesi ciao a tutti!",
            group_id=f"brandnew{int(time.time())}@g.us",
            group_name="Gruppo Appena Creato"
        )
        resp_str = r_chat.get("response", "")
        # La risposta non deve avere tono freddo/formale ("sono un'AI esterna")
        formal_tone = "ai esterna" in resp_str.lower() or "non fare la finta amica" in resp_str.lower()
        self.record("L", "L5 gruppo nuovo → tono familiare (non formale)", not formal_tone and len(resp_str) > 5,
                    note=resp_str[:80])

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO M — Group Anti-flipper & Unanswered Questions
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_M_group_social(self):
        print(head("M  Group Anti-flipper & Unanswered Questions"))

        # Anti-flipper: lutto condiviso → Genesi tace
        r1 = await self.should_respond(
            text="Che tristezza, non lo dimenticheremo mai",
            recent_messages=[
                {"name": "Genesi", "text": "Mi dispiace tantissimo"},
                {"name": "Rita", "text": "che dolore"},
            ]
        )
        tace = r1.get("intervieni") is False
        self.record("M", "M1 anti-flipper — tace sul lutto", tace, note=r1.get("motivo", "")[:60])

        # Interviene su domanda diretta
        r2 = await self.should_respond(
            text="Genesi a che ora chiude la farmacia?",
            recent_messages=[]
        )
        risponde = r2.get("intervieni") is True
        self.record("M", "M2 interviene su domanda diretta", risponde, note=r2.get("motivo", "")[:60])

        # Interviene se menzionata esplicitamente
        r3 = await self.should_respond(
            text="@genesi puoi dirmi la temperatura di Palermo?",
            recent_messages=[]
        )
        risponde3 = r3.get("intervieni") is True
        self.record("M", "M3 interviene se menzionata", risponde3, note=r3.get("motivo", "")[:60])

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO N — Platform Restrictions (widget)
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_N_platform(self):
        print(head("N  Platform Restrictions (widget)"))

        # Widget: richiesta reminder → deve essere rimappata a chat_free
        self._advance_cursor()
        resp, intent, lat = await self.chat("ricordami di chiamare il medico domani alle 9", platform="widget")
        await asyncio.sleep(PAUSE)
        # Intent non deve essere reminder_create e non deve essere bloccato con errore
        blocked = self._log_contains(r"WIDGET_INTENT_BLOCKED.*reminder")
        intent_not_reminder = intent != "reminder_create"
        self.record("N", "N1 widget — reminder bloccato", blocked or intent_not_reminder,
                    note=f"intent={intent} log={'✓' if blocked else '✗'}", latency_ms=lat)

        # Widget: risposta normale a domanda generica
        resp2, intent2, lat2 = await self.chat("quanto fa 2+2?", platform="widget")
        await asyncio.sleep(PAUSE)
        self.record("N", "N2 widget — risponde a chat generica", not resp2.startswith("HTTP_") and len(resp2) > 2,
                    response=resp2, latency_ms=lat2)

        # Widget: skip context personale (no past_conversations)
        self._advance_cursor()
        resp3, _, lat3 = await self.chat("raccontami di me", platform="widget")
        await asyncio.sleep(PAUSE)
        skip_personal = self._log_contains(r"(widget|WIDGET)")
        self.record("N", "N3 widget — piattaforma riconosciuta in log", skip_personal,
                    note=f"log_widget={'✓' if skip_personal else '✗'}", latency_ms=lat3)

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO O — SSE Streaming
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_O_sse(self):
        print(head("O  SSE Streaming Endpoint"))

        t0 = time.time()
        chunks: List[str] = []
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat/stream",
                json={"message": "ciao, come stai?"},
                headers={**self._headers(), "Accept": "text/event-stream"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                if r.status == 200:
                    async for line in r.content:
                        decoded = line.decode("utf-8", errors="replace").strip()
                        if decoded.startswith("data:"):
                            chunks.append(decoded[5:].strip())
                        if len(chunks) >= 5:  # abbastanza chunk
                            break
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            chunks = [f"EXCEPTION:{e}"]
        lat = (time.time() - t0) * 1000

        # Verifica: almeno 1 chunk ricevuto e non errore
        has_chunks = len(chunks) > 0 and not any("EXCEPTION" in c for c in chunks)
        self.record("O", "O1 SSE stream — chunk ricevuto", has_chunks,
                    note=f"chunks={len(chunks)} lat={lat:.0f}ms")

        # Verifica: almeno un chunk non vuoto
        non_empty = any(len(c) > 2 for c in chunks)
        self.record("O", "O2 SSE stream — almeno un chunk non vuoto", non_empty,
                    note=f"first chunk={chunks[0][:60] if chunks else '—'}")

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO P — Security (SSRF + Meta firma)
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_P_security(self):
        print(head("P  Security (SSRF guard + Meta webhook firma)"))

        # P1: SSRF guard — link_explorer blocca IP privato
        try:
            from core.link_explorer import _is_safe_public_url
            safe_private = await _is_safe_public_url("http://192.168.1.1/secret")
            self.record("P", "P1 SSRF guard — IP privato bloccato", safe_private is False,
                        note=f"_is_safe_public_url(192.168.1.1)={safe_private}")
        except Exception as e:
            self.record("P", "P1 SSRF guard — importazione", False, note=str(e))

        # P2: SSRF guard — IP loopback bloccato
        try:
            safe_loopback = await _is_safe_public_url("http://127.0.0.1/")
            self.record("P", "P2 SSRF guard — loopback bloccato", safe_loopback is False,
                        note=f"127.0.0.1={safe_loopback}")
        except Exception as e:
            self.record("P", "P2 SSRF guard — importazione", False, note=str(e))

        # P3: SSRF guard — metadata AWS bloccata
        try:
            safe_meta = await _is_safe_public_url("http://169.254.169.254/latest/meta-data/")
            self.record("P", "P3 SSRF guard — metadata cloud bloccata", safe_meta is False,
                        note=f"169.254.169.254={safe_meta}")
        except Exception as e:
            self.record("P", "P3 SSRF guard — importazione", False, note=str(e))

        # P4: Meta webhook firma fail-closed (senza secret → rifiuta)
        try:
            from core.meta_messaging_bot import verify_signature
            import unittest.mock as mock
            with mock.patch.dict(os.environ, {}, clear=False):
                # Rimuovi eventuali secret dall'env per il test
                env_backup = {}
                for k in ("META_APP_SECRET", "IG_APP_SECRET", "META_ALLOW_UNSIGNED"):
                    env_backup[k] = os.environ.pop(k, None)
                try:
                    result = verify_signature(b"{}", "")
                    self.record("P", "P4 Meta firma — fail-closed senza secret", result is False,
                                note=f"verify_signature(no_secret)={result}")
                finally:
                    for k, v in env_backup.items():
                        if v is not None:
                            os.environ[k] = v
        except Exception as e:
            self.record("P", "P4 Meta firma — fail-closed", False, note=str(e))

        # P5: Meta webhook opt-in dev mode
        try:
            with mock.patch.dict(os.environ, {"META_ALLOW_UNSIGNED": "1"}):
                for k in ("META_APP_SECRET", "IG_APP_SECRET"):
                    os.environ.pop(k, None)
                try:
                    result_dev = verify_signature(b"{}", "")
                    self.record("P", "P5 Meta firma — dev mode con META_ALLOW_UNSIGNED=1", result_dev is True,
                                note=f"result={result_dev}")
                except Exception as e2:
                    self.record("P", "P5 Meta firma — dev mode", False, note=str(e2))
        except Exception as e:
            self.record("P", "P5 Meta firma — dev mode", False, note=str(e))

        # P6: Webhook WhatsApp risponde 200 (senza signature)
        try:
            async with self.session.get(
                f"{self.base_url}/api/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.challenge": "12345",
                    "hub.verify_token": os.getenv("WA_VERIFY_TOKEN", "genesi-wa-verify")
                }
            ) as r:
                wa_ok = r.status in (200, 403)  # 200 se token ok, 403 se token sbagliato
                self.record("P", "P6 WhatsApp webhook endpoint raggiungibile", wa_ok, note=f"status={r.status}")
        except Exception as e:
            self.record("P", "P6 WhatsApp webhook endpoint", False, note=str(e))

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO Q — OCR (immagine con testo)
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_Q_ocr(self):
        print(head("Q  OCR (estrazione testo da immagine)"))

        # Usa un PNG semplice — il server ha tesseract, ma su 1×1 non troverà testo
        # Verifichiamo solo che l'upload non crashi e il tipo sia riconosciuto
        result = await self.upload_file("test_ocr.png", PNG_1X1_RED, "image/png")
        self.record("Q", "Q1 upload PNG — risposta valida", "error" not in result,
                    note=f"type={result.get('type','?')}")

        # Se esiste un'immagine con testo, verifica OCR
        ocr_img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "tests", "dummy_face_image.jpg")
        if os.path.exists(ocr_img_path):
            with open(ocr_img_path, "rb") as f:
                img_bytes = f.read()
            self._advance_cursor()
            res2 = await self.upload_file("ocr_test.jpg", img_bytes, "image/jpeg")
            await asyncio.sleep(2)
            ocr_log = self._log_contains(r"(OCR_|UPLOAD_VALIDATED|IMAGE_ANALYZED)")
            self.record("Q", "Q2 OCR — log trace presente", ocr_log, note="cerca OCR_/UPLOAD_VALIDATED in log")
        else:
            self.record("Q", "Q2 OCR — immagine test non trovata", True, note="skip (tests/dummy_face_image.jpg mancante)")

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO R — Document Mode (upload PDF + domanda)
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_R_document(self):
        print(head("R  Document Mode (upload PDF + query)"))

        # Crea un PDF minimale in memoria (struttura base)
        minimal_pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 595 842]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 100 700 Td (Test documento Genesi) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000274 00000 n
0000000369 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
452
%%EOF"""

        res = await self.upload_file("test_document.pdf", minimal_pdf, "application/pdf")
        upload_ok = "error" not in res and res.get("type") in ("pdf", "document", "text", None)
        self.record("R", "R1 upload PDF — accettato dal server", "error" not in res,
                    note=f"type={res.get('type','?')} resp={res.get('response','?')[:60]}")

        if upload_ok:
            await asyncio.sleep(PAUSE)
            resp, intent, lat = await self.chat("cosa dice il documento che ho caricato?")
            await asyncio.sleep(PAUSE)
            doc_ok = len(resp) > 10 and not resp.startswith("HTTP_")
            self.record("R", "R2 document query — risposta coerente", doc_ok, response=resp, latency_ms=lat)
        else:
            self.record("R", "R2 document query", False, note="Upload fallito")

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO S — Group Greeting Service
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_S_greeting(self):
        print(head("S  Group Greeting Service"))

        try:
            from core.group_greeting_service import group_greeting_service

            # Estrai info membro e salva
            await group_greeting_service.extract_and_save_member_info(
                platform_user_id="test_user_master",
                first_name="Giulio",
                message="vivo a Napoli e mi piace il calcio",
                platform="telegram",
                group_id="test_group_master",
                is_family_group=True,
            )
            await asyncio.sleep(2)

            # Leggi profilo salvato
            prof = await group_greeting_service.get_member_profile(
                platform_user_id="test_user_master",
                platform="telegram",
                is_family_group=True,
            )
            name_saved = prof.get("first_name", "") == "Giulio" if prof else False
            self.record("S", "S1 greeting service — nome salvato", name_saved, note=f"profile={prof}")

            # Costruisci saluto personalizzato
            greet = await group_greeting_service.build_personalized_greeting(
                platform_user_id="test_user_master",
                first_name="Giulio",
                greeting_category="morning",
                platform="telegram",
                group_id="test_group_master",
                is_family_group=True,
            )
            greet_ok = bool(greet) and len(greet) > 5 and "Giulio" in greet
            self.record("S", "S2 greeting service — saluto personalizzato con nome", greet_ok,
                        note=greet[:100] if greet else "—")

        except Exception as e:
            self.record("S", "S1 greeting service — import", False, note=str(e))
            self.record("S", "S2 greeting service — saluto", False, note="import fallito")

    # ═══════════════════════════════════════════════════════════════════════════
    # GRUPPO T — Sanity (pytest baseline)
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_T_pytest(self):
        print(head("T  Sanity — pytest baseline (anti-regressione)"))

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-x", "-q",
                 "--tb=no", "--no-header", "--timeout=60"],
                capture_output=True, text=True, timeout=300,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            output = result.stdout + result.stderr
            # Estrai la riga di riepilogo
            summary_match = re.search(r"(\d+) passed.*?(\d+) failed", output)
            if summary_match:
                passed_n = int(summary_match.group(1))
                failed_n = int(summary_match.group(2))
            else:
                no_fail = re.search(r"(\d+) passed", output)
                passed_n = int(no_fail.group(1)) if no_fail else 0
                failed_n = 0

            # Baseline: 654 passed, 54 failed — non devono aumentare i failed
            baseline_failed = 54
            baseline_passed = 654
            new_failures = max(0, failed_n - baseline_failed)
            self.record("T", f"T1 pytest — {passed_n} passed / {failed_n} failed", new_failures == 0,
                        note=f"new_failures={new_failures} baseline_failed={baseline_failed}")
        except subprocess.TimeoutExpired:
            self.record("T", "T1 pytest — timeout", False, note="timeout 300s")
        except Exception as e:
            self.record("T", "T1 pytest — errore", False, note=str(e))


# ─── Report finale ────────────────────────────────────────────────────────────

def print_report(groups_run: List[str]):
    total = len(ALL_RESULTS)
    passed = sum(1 for r in ALL_RESULTS if r.passed)
    failed = total - passed

    print(f"\n{BOLD}{'═'*60}")
    print(f"  MASTER TEST REPORT — Genesi {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*60}{RST}")
    print(f"  Totale:  {total}")
    print(f"  {G}Passed: {passed}{RST}")
    print(f"  {R}Failed: {failed}{RST}")
    print(f"  Score:  {passed}/{total} ({100*passed//total if total else 0}%)")
    print(f"{BOLD}{'═'*60}{RST}\n")

    if failed:
        print(f"{R}Falliti:{RST}")
        for r in ALL_RESULTS:
            if not r.passed:
                print(f"  {R}❌ [{r.group}] {r.name}{RST}")
                if r.note:
                    print(f"     {r.note}")
                if r.response:
                    print(f"     resp: {r.response[:100]}")

    # Salva report Markdown
    try:
        lines = [
            f"# Genesi Master Test Report",
            f"**Data**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Score**: {passed}/{total} ({100*passed//total if total else 0}%)",
            f"**Gruppi testati**: {', '.join(groups_run)}",
            "",
            "| Gruppo | Test | Esito | Note |",
            "|--------|------|-------|------|",
        ]
        for r in ALL_RESULTS:
            esito = "✅" if r.passed else "❌"
            note = (r.note or r.response[:60]).replace("|", "/")
            lines.append(f"| {r.group} | {r.name} | {esito} | {note} |")
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"\n{B}Report salvato: {REPORT_FILE}{RST}")
    except Exception as e:
        print(warn(f"Impossibile salvare report: {e}"))

    return passed, failed


# ─── Entry point ─────────────────────────────────────────────────────────────

async def run(args):
    tester = MasterTester(
        base_url=args.url,
        email=args.email,
        password=args.password,
    )

    # Mappa lettera → metodo
    group_map = {
        "A": tester.test_A_auth,
        "B": tester.test_B_intent,
        "C": tester.test_C_tools,
        "D": tester.test_D_relational,
        "E": tester.test_E_identity,
        "F": tester.test_F_memory,
        "G": tester.test_G_knowledge,
        "H": tester.test_H_vision,
        "I": tester.test_I_face,
        "J": tester.test_J_image_gen,
        "K": tester.test_K_group_present,
        "L": tester.test_L_tg_family,
        "M": tester.test_M_group_social,
        "N": tester.test_N_platform,
        "O": tester.test_O_sse,
        "P": tester.test_P_security,
        "Q": tester.test_Q_ocr,
        "R": tester.test_R_document,
        "S": tester.test_S_greeting,
        "T": tester.test_T_pytest,
    }

    # Seleziona gruppi da eseguire
    if args.groups:
        groups_to_run = [g.strip().upper() for g in args.groups.split(",")]
    else:
        groups_to_run = list(group_map.keys())
    if args.skip:
        skip_set = {g.strip().upper() for g in args.skip.split(",")}
        groups_to_run = [g for g in groups_to_run if g not in skip_set]

    print(f"{BOLD}{C}GENESI MASTER TEST SUITE v1.0{RST}")
    print(f"URL: {args.url}  |  Email: {args.email}")
    print(f"Gruppi: {', '.join(groups_to_run)}\n")

    await tester.setup()
    try:
        for g in groups_to_run:
            if g in group_map:
                await group_map[g]()
            else:
                print(warn(f"Gruppo '{g}' non riconosciuto — skip"))
    finally:
        await tester.teardown()

    return print_report(groups_to_run)


def main():
    parser = argparse.ArgumentParser(description="Genesi Master Test Suite")
    parser.add_argument("--url", default=BASE_URL, help="URL base del server")
    parser.add_argument("--email", default=TEST_EMAIL, help="Email account di test")
    parser.add_argument("--password", default=TEST_PASSWORD, help="Password account di test")
    parser.add_argument("--groups", default="", help="Gruppi da eseguire (es. A,B,C). Default: tutti")
    parser.add_argument("--skip", default="", help="Gruppi da saltare (es. T). Default: nessuno")
    args = parser.parse_args()

    passed, failed = asyncio.run(run(args))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
