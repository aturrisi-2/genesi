#!/usr/bin/env python3
"""
GENESI — Face/Pet Recognition Test Suite
Testa il pipeline completo di riconoscimento visivo (piattaforma-indipendente):
  - Identificazione umana da testo dopo foto con sconosciuti
  - Identificazione animale domestico
  - Lista ordinata con più soggetti
  - Risposta parziale (1 nome su 3)
  - Blocco nomi placeholder (UNKNOWN, sconosciuto, ecc.)
  - Nessuna falsa identificazione senza stato awaiting
  - Regressione: chat normale non disturbata

Uso:
  python3 scripts/test_face_recognition.py
  python3 scripts/test_face_recognition.py alfio.turrisi@gmail.com ZOEennio0810

NOTE:
  - Usa nomi con prefisso "Ztfr_" (ZTest_FaceRecognition) → rimossi in cleanup
  - Approccio delta-file: confronta data/faces/ prima e dopo ogni test
  - Non dipende da dati preesistenti: solo nuovi file creati durante il test
  - Richiede accesso ai file in memory/ e data/faces/ (stesso VPS del server)
  - Fa chiamate LLM reali (gpt-4o-mini) per l'estrazione nomi
"""
import asyncio
import aiohttp
import base64
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL      = "http://localhost:8000"
TEST_EMAIL    = sys.argv[1] if len(sys.argv) > 1 else "face_test@genesi.local"
TEST_PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "Face_Test_2026"

LOG_FILE  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "genesi.log")
FACES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "faces")

# Prefisso test — tutti i file che iniziano con "ztfr_" vengono rimossi al cleanup
T_PREFIX  = "Ztfr_"
T_HUMAN_1 = f"{T_PREFIX}Marco"
T_HUMAN_2 = f"{T_PREFIX}Laura"
T_HUMAN_3 = f"{T_PREFIX}Rita"
T_PET_1   = f"{T_PREFIX}Milo"

PAUSE = 3.0  # secondi tra test (attesa background tasks LLM)

# ─── Colori ────────────────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; RST = "\033[0m"; BOLD = "\033[1m"

def ok(s):   return f"{G}✅ {s}{RST}"
def fail(s): return f"{R}❌ {s}{RST}"
def info(s): return f"{B}   {s}{RST}"


# ─── JPEG minimale 1x1 px (biometrico: 0 volti, ma file valido) ───────────────
def _make_minimal_jpeg() -> bytes:
    return bytes([
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


@dataclass
class TR:
    group: str
    name: str
    passed: bool
    response: str = ""
    note: str = ""
    latency_ms: float = 0

results: List[TR] = []


class FaceRecognitionTester:

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        self._log_cursor = 0

    # ── Setup / teardown ──────────────────────────────────────────────────────
    async def setup(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90))
        await self._ensure_user()
        await self._login()
        self._log_cursor = self._count_log_lines()
        print(info(f"Login OK. user_id={self.user_id}  log cursor={self._log_cursor}"))

    async def teardown(self):
        await self._cleanup_test_data()
        if self.session:
            await self.session.close()

    async def _ensure_user(self):
        if TEST_EMAIL.endswith("@genesi.local"):
            try:
                async with self.session.post(
                    f"{BASE_URL}/auth/register",
                    json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
                ) as r:
                    pass
            except Exception:
                pass

    async def _login(self):
        async with self.session.post(
            f"{BASE_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        ) as r:
            if r.status != 200:
                print(fail(f"Login fallito: HTTP {r.status}"))
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

    async def _cleanup_test_data(self):
        if not os.path.exists(FACES_DIR):
            return
        removed = []
        for fname in os.listdir(FACES_DIR):
            if fname.lower().startswith("ztfr_"):
                try:
                    os.remove(os.path.join(FACES_DIR, fname))
                    removed.append(fname)
                except Exception:
                    pass
        if removed:
            print(info(f"Cleanup: rimossi {len(removed)} file test da data/faces/"))

    # ── Chat ──────────────────────────────────────────────────────────────────
    async def chat(self, message: str) -> Tuple[str, float]:
        t0 = time.time()
        try:
            async with self.session.post(
                f"{BASE_URL}/api/chat/",
                json={"message": message},
                headers={"Authorization": f"Bearer {self.token}"}
            ) as r:
                latency = (time.time() - t0) * 1000
                if r.status == 200:
                    data = await r.json()
                    return data.get("response", ""), latency
                else:
                    body = await r.text()
                    return f"[HTTP {r.status}] {body[:120]}", latency
        except Exception as e:
            return f"[ERRORE] {e}", (time.time() - t0) * 1000

    # ── Log ───────────────────────────────────────────────────────────────────
    def _count_log_lines(self) -> int:
        if not os.path.exists(LOG_FILE):
            return 0
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)

    def _read_new_logs(self) -> str:
        if not os.path.exists(LOG_FILE):
            return ""
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        new = lines[self._log_cursor:]
        self._log_cursor = len(lines)
        return "".join(new)

    def _log_has(self, pattern: str, logs: str) -> bool:
        return bool(re.search(pattern, logs, re.IGNORECASE))

    # ── Delta-file: confronta file in data/faces/ prima e dopo ───────────────
    def _snapshot_faces(self) -> Set[str]:
        if not os.path.exists(FACES_DIR):
            return set()
        return set(f for f in os.listdir(FACES_DIR) if f.endswith(".json"))

    def _new_faces_since(self, before: Set[str]) -> Set[str]:
        return self._snapshot_faces() - before

    # ── Awaiting state seeding ────────────────────────────────────────────────
    async def _seed_awaiting(self, description: str, unknown_count: int = 1,
                             tmp_img: str = "/tmp/ztfr_face.jpg"):
        with open(tmp_img, "wb") as f:
            f.write(_make_minimal_jpeg())
        from core.storage import storage
        session_key = f"short_term_chat:awaiting_faces_{self.user_id}"
        await storage.save(session_key, {
            "img_path": tmp_img,
            "description": description,
            "unknown_count": unknown_count,
            "identified": [],
            "ts": int(time.time()),
        })
        await asyncio.sleep(0.2)

    async def _clear_awaiting(self):
        from core.storage import storage
        session_key = f"short_term_chat:awaiting_faces_{self.user_id}"
        await storage.delete(session_key)

    # ── Runner ────────────────────────────────────────────────────────────────
    async def run(
        self,
        group: str,
        name: str,
        *,
        seed_desc: str = "",
        seed_count: int = 1,
        message: str,
        expect_new_face: str = "",        # nome (clean lowercase) di un file atteso come NUOVO
        expect_no_new_face: str = "",     # nome che NON deve comparire tra i nuovi file
        log_must: str = "",
        log_must_not: str = "",
        note: str = "",
        pre_seed: bool = True,
    ) -> TR:
        if pre_seed and seed_desc:
            await self._seed_awaiting(seed_desc, unknown_count=seed_count)

        before = self._snapshot_faces()
        self._read_new_logs()

        response, latency = await self.chat(message)
        await asyncio.sleep(PAUSE)
        logs = self._read_new_logs()

        after = self._snapshot_faces()
        new_files = self._new_faces_since(before)

        checks = []
        notes_parts = []

        if expect_new_face:
            exp_key = expect_new_face.strip().lower().replace(" ", "_") + ".json"
            found = exp_key in new_files
            checks.append(found)
            if not found:
                notes_parts.append(f"file non creato: {exp_key} (nuovi: {new_files})")

        if expect_no_new_face:
            exp_key = expect_no_new_face.strip().lower().replace(" ", "_") + ".json"
            absent = exp_key not in new_files
            checks.append(absent)
            if not absent:
                notes_parts.append(f"file creato per errore: {exp_key}")

        if log_must:
            found_log = self._log_has(log_must, logs)
            checks.append(found_log)
            if not found_log:
                notes_parts.append(f"log mancante: {log_must}")

        if log_must_not:
            absent_log = not self._log_has(log_must_not, logs)
            checks.append(absent_log)
            if not absent_log:
                notes_parts.append(f"log inatteso: {log_must_not}")

        # Nessun check specifico → passa se HTTP 200
        if not checks:
            checks.append(not response.startswith("[HTTP") and not response.startswith("[ERRORE]"))

        passed = all(checks)
        full_note = (note + " | " if note else "") + "; ".join(notes_parts)

        result = TR(
            group=group, name=name, passed=passed,
            response=response[:200], note=full_note.strip(" |"), latency_ms=latency
        )
        results.append(result)

        icon = ok(name) if passed else fail(name)
        print(f"  {icon}  [{latency:.0f}ms]")
        if not passed:
            print(info(f"    resp: {response[:120]}"))
            print(info(f"    note: {full_note}"))
        return result


# ─── Suite ─────────────────────────────────────────────────────────────────────
async def run_suite():
    t = FaceRecognitionTester()
    await t.setup()

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{BOLD}{B}GRUPPO 1 — Identificazione umana da testo{RST}")
    # ══════════════════════════════════════════════════════════════════════════

    desc_1human = (
        f"Nella foto c'è 1 persona. [UNKNOWN_FACES_DETECTED] [TOTAL_HUMANS:1] "
        f"[INDEX:0] uomo capelli scuri camicia blu al centro "
        f"[GENDER_VISUAL_HINTS: index=0 gender=M]"
    )

    await t.run(
        "G1", "F1.1 — Identificazione singola",
        seed_desc=desc_1human,
        message=f"si chiama {T_HUMAN_1}",
        expect_new_face=T_HUMAN_1,
        log_must=r"FACE_MEMORY_SAVED.*ztfr",
        note="awaiting 1 face → name → FACE_MEMORY_SAVED + file creato"
    )

    await t.run(
        "G1", "F1.2 — Nome placeholder bloccato",
        seed_desc=desc_1human,
        message="è una persona sconosciuta",
        expect_no_new_face="persona",
        note="'persona' in _INVALID_NAMES → nessun salvataggio"
    )

    await t.run(
        "G1", "F1.3 — Nessun false positive senza awaiting",
        pre_seed=False,
        message=f"mi chiamo {T_HUMAN_1}",
        expect_no_new_face=T_HUMAN_1,
        log_must_not=r"FACE_MEMORY_SAVED.*ztfr_marco",
        note="senza awaiting state: nessun salvataggio dal testo libero"
    )

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{BOLD}{B}GRUPPO 2 — Identificazione animale (pet){RST}")
    # ══════════════════════════════════════════════════════════════════════════

    desc_1pet = (
        f"Nella foto c'è 1 animale. [UNKNOWN_PETS_DETECTED] [TOTAL_PETS:1] "
        f"[INDEX:0] gatto pelage arancione taglia media"
    )

    await t.run(
        "G2", "F2.1 — Identificazione animale",
        seed_desc=desc_1pet,
        message=f"è il mio gatto {T_PET_1}",
        log_must=r"PET_SAVED.*ztfr",
        note="awaiting 1 pet → name → PET_SAVED"
    )

    await t.run(
        "G2", "F2.2 — Pet: nome generico bloccato",
        seed_desc=desc_1pet,
        message="è un gatto",
        note="'gatto' in _INVALID_NAMES → nessun PET_SAVED"
    )

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{BOLD}{B}GRUPPO 3 — Lista ordinata e risposta parziale{RST}")
    # ══════════════════════════════════════════════════════════════════════════

    desc_3humans = (
        f"Nella foto ci sono 3 persone. [UNKNOWN_FACES_DETECTED] [TOTAL_HUMANS:3] "
        f"[INDEX:0] donna capelli biondi a sinistra [GENDER_VISUAL_HINTS: index=0 gender=F] "
        f"[INDEX:1] uomo capelli scuri al centro [GENDER_VISUAL_HINTS: index=1 gender=M] "
        f"[INDEX:2] donna capelli rossi a destra [GENDER_VISUAL_HINTS: index=2 gender=F]"
    )

    await t.run(
        "G3", "F3.1 — Lista ordinata 3 nomi → tutti salvati",
        seed_desc=desc_3humans, seed_count=3,
        message=f"da sinistra {T_HUMAN_2}, {T_HUMAN_1} e {T_HUMAN_3}",
        expect_new_face=T_HUMAN_1,
        log_must=r"EXTRACT_FACES_DONE.*saved=3",
        note="3 nomi in ordine → saved=3 + remaining=0"
    )

    await t.run(
        "G3", "F3.2 — Risposta parziale 1/3 → remaining=2",
        seed_desc=desc_3humans, seed_count=3,
        message=f"la prima a sinistra è {T_HUMAN_2}",
        expect_new_face=T_HUMAN_2,
        log_must=r"AWAITING_FACES_UPDATED.*remaining=2",
        note="1 nome su 3 → awaiting aggiornato con remaining=2"
    )

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{BOLD}{B}GRUPPO 4 — Correzioni{RST}")
    # ══════════════════════════════════════════════════════════════════════════

    desc_correction = (
        f"Nella foto c'è 1 persona. [UNKNOWN_FACES_DETECTED] [TOTAL_HUMANS:1] "
        f"[INDEX:0] uomo giacca verde [GENDER_VISUAL_HINTS: index=0 gender=M]"
    )

    await t.run(
        "G4", "F4.1 — Prima identificazione",
        seed_desc=desc_correction,
        message=f"si chiama {T_HUMAN_1}",
        expect_new_face=T_HUMAN_1,
        note="setup: salva il primo nome"
    )
    await t.run(
        "G4", "F4.2 — Correzione: nuovo nome salvato",
        seed_desc=desc_correction,
        message=f"aspetta, in realtà si chiama {T_HUMAN_3}",
        expect_new_face=T_HUMAN_3,
        log_must=r"FACE_MEMORY_SAVED.*ztfr",
        note="correzione → file per il nome corretto creato"
    )

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{BOLD}{B}GRUPPO 5 — Regressioni chat normale{RST}")
    # ══════════════════════════════════════════════════════════════════════════

    await t._clear_awaiting()

    await t.run(
        "G5", "F5.1 — Chat normale (greeting): nessun side-effect",
        pre_seed=False,
        message="ciao come stai",
        expect_no_new_face=T_HUMAN_1,
        log_must_not=r"FACE_MEMORY_SAVED|PET_SAVED|AWAITING_FACES_SET",
        note="chat normale non tocca il face pipeline"
    )

    await t.run(
        "G5", "F5.2 — Nome proprio nel testo senza awaiting: nessun false positive",
        pre_seed=False,
        message=f"ho un amico che si chiama {T_HUMAN_1}",
        expect_no_new_face=T_HUMAN_1,
        log_must_not=r"FACE_MEMORY_SAVED.*ztfr_marco",
        note="menzione nome senza awaiting → nessun salvataggio"
    )

    await t.run(
        "G5", "F5.3 — Risposta HTTP 200 (smoke test)",
        pre_seed=False,
        message="che tempo fa a Roma",
        note="check base: server risponde normalmente"
    )

    await t.teardown()

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"{BOLD}RISULTATI FACE RECOGNITION TEST{RST}")
    print(f"{'='*60}")

    passed_count = sum(1 for r in results if r.passed)
    total = len(results)
    current_group = ""
    for r in results:
        if r.group != current_group:
            print(f"\n  {B}{r.group}{RST}")
            current_group = r.group
        icon = f"{G}✅{RST}" if r.passed else f"{R}❌{RST}"
        print(f"    {icon} {r.name}  ({r.latency_ms:.0f}ms)")
        if r.note and not r.passed:
            print(f"       {Y}{r.note}{RST}")

    print(f"\n{'─'*60}")
    color = G if passed_count == total else (Y if passed_count >= total * 0.7 else R)
    print(f"{BOLD}{color}Score: {passed_count}/{total}{RST}")

    if passed_count < total:
        print(f"\n{R}Test falliti:{RST}")
        for r in results:
            if not r.passed:
                print(f"  • {r.name}: {r.note[:100]}")
    print("")
    return passed_count == total


if __name__ == "__main__":
    ok_all = asyncio.run(run_suite())
    sys.exit(0 if ok_all else 1)
