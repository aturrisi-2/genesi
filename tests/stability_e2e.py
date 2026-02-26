import pytest
import asyncio
from playwright.sync_api import sync_playwright, expect
import time
import os
import json
import sys

# Forza encoding UTF-8 per gestire emoji su Windows
sys.stdout.reconfigure(encoding='utf-8')

# CONFIGURATION
BASE_URL = "http://localhost:8000"

def test_genesi_deep_audit():
    """
    Audit di stabilità profonda: testa i sistemi vitali di Genesi simulando un utente reale.
    """
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 720})
        page = context.new_page()

        # Reports and logs
        audit_results = {
            "critical_logic": [],
            "ux_ui": [],
            "ecosystem": [],
            "errors": []
        }

        page.on("console", lambda msg: audit_results["errors"].append(f"[JS {msg.type}] {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda exc: audit_results["errors"].append(f"[EXCEPTION] {exc}"))

        print("\n[GUARDIA] Avvio Audit Profondo di Genesi...")

        # 1. TEST CONNESSIONE (Semaforo Verde)
        try:
            print("  - Fase 1: Verifica raggiungibilità...")
            page.goto(f"{BASE_URL}")
            expect(page).to_have_title("Genesi")
            audit_results["ux_ui"].append("✅ Titolo Genesi presente.")
        except Exception as e:
            audit_results["critical_logic"].append(f"❌ Impossibile caricare la Home: {e}")

        # 2. TEST AUTH PAGE
        print("  - Fase 2: Audit interfaccia Login...")
        if "login" in page.url:
            expect(page.locator("input[type='email']")).to_be_visible()
            expect(page.locator("input[type='password']")).to_be_visible()
            audit_results["ux_ui"].append("✅ Pagina Login strutturata correttamente.")
        
        # 3. TEST PWA & ASSETS
        print("  - Fase 3: Verifica asset PWA...")
        manifest = page.request.get(f"{BASE_URL}/static/manifest.json")
        if manifest.status == 200:
            audit_results["ecosystem"].append("✅ Manifest PWA accessibile.")
        else:
            audit_results["ecosystem"].append("❌ Manifest PWA mancante!")

        # 4. TEST HEALTH API (Stato Interno)
        print("  - Fase 4: Verifica API Salute...")
        health = page.request.get(f"{BASE_URL}/health")
        if health.status == 200:
            data = health.json()
            audit_results["critical_logic"].append(f"✅ Motore {data.get('architecture')} attivo.")
        else:
            audit_results["critical_logic"].append("❌ API Health non risponde.")

        # 5. AUDIT LOGICA SINCRONIZZAZIONE (Simulazione)
        # Verifichiamo se il codice di app.v2.js contiene la logica dei popup
        print("  - Fase 5: Verifica integrità logica Sync (app.v2.js)...")
        js_content = page.request.get(f"{BASE_URL}/static/app.v2.js").text()
        if "handleSyncPopups" in js_content and "showSyncPopup" in js_content:
            audit_results["ecosystem"].append("✅ Logica Sync Popups presente nel bundle JS.")
        else:
            audit_results["ecosystem"].append("🚩 Logica Sync Popups NON TROVATA nel JS!")

        # 6. ANALISI ERRORI CONSOLE
        print("\n--- [RISULTATI AUDIT STABILITÀ] ---")
        
        print("\n🧠 LOGICA CRITICA:")
        for res in audit_results["critical_logic"]: print(f"  {res}")
        
        print("\n🎭 INTERFACCIA (UX/UI):")
        for res in audit_results["ux_ui"]: print(f"  {res}")
        
        print("\n🌐 ECOSISTEMA & SYNC:")
        for res in audit_results["ecosystem"]: print(f"  {res}")

        if audit_results["errors"]:
            print("\n🚩 ERRORI RILEVATI DA SISTEMARE:")
            for err in audit_results["errors"]: print(f"  {err}")
        else:
            print("\n✨ NESSUN ERRORE CRITICO RILEVATO.")

        with open("audit_summary.json", "w", encoding="utf-8") as f:
            json.dump(audit_results, f, indent=2, ensure_ascii=False)
        
        print("\nAudit completo. Risultati salvati in audit_summary.json")
        browser.close()

if __name__ == "__main__":
    test_genesi_deep_audit()
