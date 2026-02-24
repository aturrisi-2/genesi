
import os
import sys
import datetime
import pytest
from pathlib import Path

# Aggiungi la root del progetto al path
root_path = Path(__file__).parent.parent
sys.path.append(str(root_path))

from core.icloud_service import icloud_service
from calendar_manager import calendar_manager

@pytest.mark.asyncio
async def test_icloud_connection():
    """Testa se riusciamo a connetterci a iCloud."""
    print("\n[TEST] Verifica connessione iCloud...")
    assert icloud_service.username is not None, "Username iCloud non configurato"
    assert icloud_service.password is not None, "Password iCloud non configurata"
    
    success = icloud_service._connect()
    assert success is True, "Connessione CalDAV fallita"
    print("✅ Connessione riuscita")

@pytest.mark.asyncio
async def test_icloud_fetch():
    """Testa il recupero degli impegni."""
    print("\n[TEST] Recupero impegni iCloud...")
    items = icloud_service.get_vtodo(days=1, force_sync=True)
    print(f"✅ Recuperati {len(items)} impegni")
    assert isinstance(items, list)

@pytest.mark.asyncio
async def test_icloud_create_reminder():
    """Testa la creazione di un promemoria reale."""
    test_title = f"Test Genesi {datetime.datetime.now().strftime('%H:%M:%S')}"
    test_dt = datetime.datetime.now() + datetime.timedelta(hours=2)
    
    print(f"\n[TEST] Creazione promemoria: {test_title}...")
    success = icloud_service.create_reminder(test_title, test_dt)
    
    assert success is True, "Creazione promemoria fallita"
    print("✅ Promemoria creato con successo")
    
    # Verifica che sia apparso nella cache/lista
    items = icloud_service.get_vtodo(days=7)
    found = any(test_title in i['summary'] for i in items)
    assert found is True, "Il promemoria creato non appare nella lista"
    print("✅ Verifica presenza nella lista superata")

if __name__ == "__main__":
    # Esecuzione manuale se necessario
    import asyncio
    async def run_all():
        try:
            await test_icloud_connection()
            await test_icloud_fetch()
            await test_icloud_create_reminder()
            print("\n🌟 TUTTI I TEST PASSATI!")
        except Exception as e:
            print(f"\n❌ TEST FALLITO: {e}")
            sys.exit(1)
    
    asyncio.run(run_all())
