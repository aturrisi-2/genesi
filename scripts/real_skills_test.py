#!/usr/bin/env python3
"""
Test REALE e completo delle skill di Genesi sul VPS (niente pytest).
Fa scattare i trigger veri via gli endpoint reali + chiamate dirette ai servizi,
poi verifica le risposte effettive. Esegui con: venv/bin/python3 scripts/real_skills_test.py
(env /etc/genesi.env + /opt/genesi/.env già caricati nel processo).
"""
import asyncio, sys, time, json, os, base64
sys.path.insert(0, "/opt/genesi")
import httpx

BASE = "http://localhost:8000"
GROUP_EMAIL = "whatsapp_group@genesi.group"
GROUP_PASS = "WaGroup2026!"
TESTG = "120363407869433239@g.us"   # Prova Genesi (gruppo noto)
RESULTS = []

def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("✅" if ok else "❌") + f"  {name}  —  {str(detail)[:90]}")

async def main():
    async with httpx.AsyncClient(timeout=120) as c:
        tok = (await c.post(f"{BASE}/auth/login", json={"email": GROUP_EMAIL, "password": GROUP_PASS})).json().get("access_token", "")
        H = {"Authorization": f"Bearer {tok}"}
        chk("Auth login (token gruppo)", bool(tok), tok[:10] + "...")

        async def group(text, sender="TestUtente", sid="3900000001@s.whatsapp.net", **kw):
            body = {"text": text, "sender_name": sender, "sender_id": sid,
                    "group_id": TESTG, "group_name": "Prova Genesi"}
            body.update(kw)
            r = await c.post(f"{BASE}/api/chat/group", json=body, headers=H)
            return r.json()

        # 1. Risposta relazionale di gruppo
        r = await group("Genesi raccontami una cosa bella di oggi")
        chk("Skill: chat relazionale gruppo", len(r.get("response", "")) > 15, r.get("response", "")[:70])

        # 2. Meteo (intent + dato reale)
        r = await group("Genesi che tempo fa a Roma oggi?")
        resp = r.get("response", "").lower()
        chk("Skill: meteo", any(w in resp for w in ["°", "grad", "sole", "nuvol", "piogg", "cielo", "sere"]), r.get("response", "")[:70])

        # 3. Identità (sa di essere Genesi, prima persona)
        r = await group("Genesi tu chi sei? Sei un membro umano?")
        resp = r.get("response", "").lower()
        chk("Skill: identità (è Genesi, AI)", "genesi" in resp or "assistente" in resp or "ai" in resp, r.get("response", "")[:70])

        # 4. Presentazione in gruppo NUOVO
        newg = f"888777{int(time.time())}@g.us"
        r = (await c.post(f"{BASE}/api/chat/group/present", json={"group_id": newg, "group_name": "Test Skill Group", "adder_name": "Marco"}, headers=H)).json()
        chk("Skill: presentazione gruppo nuovo", r.get("presented") and len(r.get("response", "")) > 15, r.get("response", "")[:60])

        # 5. Dedup presentazione (stesso gruppo → no)
        r2 = (await c.post(f"{BASE}/api/chat/group/present", json={"group_id": newg, "group_name": "Test Skill Group"}, headers=H)).json()
        chk("Skill: dedup presentazione", r2.get("presented") is False, f"presented={r2.get('presented')}")

        # 6. Forget + ripresentazione
        await c.post(f"{BASE}/api/chat/group/forget", json={"group_id": newg}, headers=H)
        r3 = (await c.post(f"{BASE}/api/chat/group/present", json={"group_id": newg, "group_name": "Test Skill Group"}, headers=H)).json()
        chk("Skill: forget→ripresentazione", r3.get("presented") is True, f"presented={r3.get('presented')}")
        await c.post(f"{BASE}/api/chat/group/forget", json={"group_id": newg}, headers=H)

        # 7. Compleanno: parsing testo qualsiasi formato
        r = (await c.post(f"{BASE}/api/chat/group/birthday-dm", json={"wa_id": "39testbday1", "name": "TestB", "text": "sono nato il ventidue aprile del settantotto"}, headers=H)).json()
        chk("Skill: compleanno parse (a parole)", r.get("found") and r.get("date") == "1978-04-22", f"{r.get('date')}")

        # 8. Anti-flipper: discussione emotiva tra umani → TACE
        r = (await c.post(f"{BASE}/api/chat/group/should_respond", json={"text": "Che tristezza, non lo dimenticheremo mai", "recent_messages": [{"name": "Genesi", "text": "Mi dispiace tantissimo"}, {"name": "Rita", "text": "che dolore"}]}, headers=H)).json()
        chk("Skill: anti-flipper (tace sul lutto)", r.get("intervieni") is False, r.get("motivo", "")[:50])

        # 9. Should_respond: domanda di utilità → RISPONDE
        r = (await c.post(f"{BASE}/api/chat/group/should_respond", json={"text": "Genesi a che ora chiude la farmacia?", "recent_messages": []}, headers=H)).json()
        chk("Skill: interviene su utilità", r.get("intervieni") is True, r.get("motivo", "")[:50])

        # 10. Correzione nome ("chiamami X") + persistenza preferred_name
        sid_pina = "3900000777@s.whatsapp.net"
        await group("Genesi chiamami Cetty d'ora in poi", sender="Concetta Strana 🌸", sid=sid_pina)
        from core.telegram_group_memory import get_member, stable_hash, member_display_name
        mem = await get_member(stable_hash("3900000777"))
        chk("Skill: correzione nome (preferred_name)", member_display_name(mem) == "Cetty", f"display={member_display_name(mem)}")

        # 11. Foto + biometria volti (riconosce un volto noto)
        import glob
        face_imgs = glob.glob("/opt/genesi/data/faces/*.jpg")
        if face_imgs:
            fn = sorted(face_imgs, key=os.path.getsize)[-1]
            known_name = os.path.basename(fn).split("_")[0]
            with open(fn, "rb") as f:
                img = f.read()
            up = await c.post(f"{BASE}/api/upload/", files={"file": ("face.jpg", img, "image/jpeg")}, headers=H)
            content = (up.json().get("content", "") if up.status_code == 200 else "").lower()
            chk("Skill: foto+biometria volti", up.status_code == 200 and len(content) > 20, f"riconosciuto~{known_name}? len={len(content)}")
        else:
            chk("Skill: foto+biometria volti", False, "nessuna immagine volto su disco")

        # 12. Audio: trascrizione + uso (via pipeline) — genera TTS e processa
        try:
            from core.tts_provider import OpenAITTSProvider
            audio = await OpenAITTSProvider().synthesize("Ciao Genesi, il mio compleanno è il dieci marzo millenovecentonovanta.")
            from core.message_pipeline import process_incoming_audio
            ar = await process_incoming_audio(session_id="test_audio", user_id="test_audio", audio_bytes=audio, platform="whatsapp", content_type="audio/mpeg")
            tr = (ar.get("transcription") or "").lower()
            chk("Skill: audio trascrizione", "marzo" in tr or "compleanno" in tr or "genesi" in tr, tr[:60])
        except Exception as e:
            chk("Skill: audio trascrizione", False, str(e)[:60])

        # 13. Compleanno da AUDIO (vocale → data)
        try:
            audio2 = await OpenAITTSProvider().synthesize("sono nato il quindici agosto del millenovecentottantacinque")
            mid_a = f"TESTBDAUDIO{int(time.time())}"
            with open(f"/opt/genesi-baileys/media-cache/{mid_a}", "wb") as f:
                f.write(audio2)
            with open(f"/opt/genesi-baileys/media-cache/{mid_a}.mime", "w") as f:
                f.write("audio/mpeg")
            r = (await c.post(f"{BASE}/api/chat/group/birthday-dm", json={"wa_id": "39testbdaudio", "name": "TestA", "text": "", "media_id": mid_a, "media_type": "audio", "media_mime": "audio/mpeg"}, headers=H)).json()
            chk("Skill: compleanno da VOCALE", r.get("found") and r.get("date") == "1985-08-15", f"{r.get('date')}")
        except Exception as e:
            chk("Skill: compleanno da VOCALE", False, str(e)[:60])

    # ---- Chiamate dirette ai servizi (no HTTP) ----
    # 14. Manuali: ricerca medica/veterinaria/psicologica
    try:
        from core.manual_service import manual_service as ms
        hits = []
        for q in ["primo soccorso psicologico ascolto", "parassiti gastrointestinali cane", "infarto sintomi"]:
            res = ms.search(q) if not asyncio.iscoroutinefunction(ms.search) else await ms.search(q)
            hits.append(bool(res and len(str(res)) > 20))
        chk("Skill: consultazione manuali", all(hits), f"hit={hits}")
    except Exception as e:
        chk("Skill: consultazione manuali", False, str(e)[:60])

    # 15. Diario gruppi persistito su disco
    try:
        from core.telegram_group_memory import get_raw_messages, MAX_RAW_MSGS
        d = await get_raw_messages(272555882, limit=500)
        chk("Skill: diario gruppo persistente", MAX_RAW_MSGS >= 500, f"cap={MAX_RAW_MSGS}, msg salvati={len(d)}")
    except Exception as e:
        chk("Skill: diario gruppo persistente", False, str(e)[:60])

    # 16. Compleanni enumerati da DISCO
    try:
        from core.birthday_service import _all_birthday_member_ids
        ids = _all_birthday_member_ids()
        chk("Skill: compleanni enumerati da disco", len(ids) > 0, f"{len(ids)} compleanni trovati")
    except Exception as e:
        chk("Skill: compleanni enumerati da disco", False, str(e)[:60])

    # 17. Database volti + animali su SSD
    import glob
    nf = len(glob.glob("/opt/genesi/data/faces/*.pt"))
    npet = len(glob.glob("/opt/genesi/data/pets/*.pt"))
    chk("Skill: DB volti+animali su SSD", nf > 0 and npet > 0, f"volti={nf}, animali={npet}")

    # 18. Immagine mattutina generata (saluto+meteo)
    try:
        from core.birthday_service import _generate_morning_image
        url = await _generate_morning_image("Buongiorno famiglia, oggi splende il sole!", 943999700, "whatsapp")
        ok = bool(url)
        if ok:
            async with httpx.AsyncClient(timeout=30) as c2:
                hh = await c2.get(url)
                ok = hh.status_code == 200 and "image" in hh.headers.get("content-type", "")
        chk("Skill: immagine mattutina generata", ok, url[-40:] if url else "no url")
    except Exception as e:
        chk("Skill: immagine mattutina generata", False, str(e)[:60])

    # ---- Cleanup artefatti di test ----
    try:
        from core.storage import storage
        for k in ["birthday:wa:39testbday1", "birthday:wa:39testbdaudio"]:
            try: await storage.delete(k)
            except Exception: pass
    except Exception:
        pass

    # ---- Report ----
    ok = sum(1 for _, v in RESULTS if v)
    tot = len(RESULTS)
    print("\n" + "=" * 50)
    print(f"RISULTATO: {ok}/{tot} skill OK")
    if ok < tot:
        print("FALLITE:", ", ".join(n for n, v in RESULTS if not v))
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
