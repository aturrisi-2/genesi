import asyncio
import sys
import os

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.chat import GroupChatRequest, GroupParticipant, group_chat_endpoint
from core.telegram_group_memory import build_group_context
from auth.models import AuthUser

async def test_disambiguation_and_counting():
    print("\n--- Test 1: Riconoscimento e Disambiguazione Partecipanti ---")
    
    # Mockiamo i partecipanti inviati dal Baileys bridge
    # Due umani con lo stesso nome "Alfio" ma diversi ID/JID, e Genesi stessa
    participants = [
        {"id": "393311234567@s.whatsapp.net", "name": "Alfio", "is_me": False},
        {"id": "393478901234@s.whatsapp.net", "name": "Alfio", "is_me": False},
        {"id": "393313650671@s.whatsapp.net", "name": "Genesi", "is_me": True}
    ]
    
    # Chiamiamo build_group_context
    chat_id = 999999
    from_id = 111111
    first_name = "Alfio"
    
    print("Costruisco contesto con partecipanti duplicati...")
    ctx = await build_group_context(
        chat_id=chat_id,
        from_id=from_id,
        first_name=first_name,
        participants=participants
    )
    
    print("Contesto generato (anteprima):")
    # Usa backslashreplace per evitare eccezioni di stampa su Windows
    print(ctx[:500].encode('ascii', 'backslashreplace').decode('ascii') + "\n...")
    
    # Validiamo i conteggi e le disambiguazioni
    assert "In totale ci sono 3 membri: tu (e gli altri umani) e io (Genesi, l'assistente AI)." in ctx, \
        "Errore: il conteggio totale dei membri non è corretto!"
    assert "Alfio (tel: ...4567)" in ctx, "Errore: Alfio 1 non è stato disambiguato correttamente!"
    assert "Alfio (tel: ...1234)" in ctx, "Errore: Alfio 2 non è stato disambiguato correttamente!"
    print("[OK] Test 1 Superato con Successo!")

async def test_group_link_explorer():
    print("\n--- Test 2: Integrazione Link Explorer in Group Chat ---")
    
    # Mock utente autenticato coerente con SQLAlchemy AuthUser
    mock_user = AuthUser(
        id="owner_user_123",
        email="whatsapp_group@genesi.group",
        password_hash="hashed_password",
        is_verified=True
    )
    
    # Mock payload della richiesta di gruppo con un URL reale (stabile)
    request_data = GroupChatRequest(
        text="Date un'occhiata a questa pagina: https://httpbin.org/html",
        sender_name="Alfio",
        sender_id="393311234567@s.whatsapp.net",
        group_id="120363200000000000@g.us",
        group_name="Test Link Group",
        participants=[
            GroupParticipant(id="393311234567@s.whatsapp.net", name="Alfio", is_me=False),
            GroupParticipant(id="393313650671@s.whatsapp.net", name="Genesi", is_me=True)
        ]
    )
    
    print("Inoltro richiesta all'endpoint group_chat_endpoint...")
    # Bypassa Depends(require_auth) chiamando direttamente l'endpoint asincrono
    response = await group_chat_endpoint(request_data, user=mock_user)
    
    print("Risposta ricevuta da Genesi:")
    # Usa backslashreplace per evitare eccezioni di stampa su Windows
    print(response.response.encode('ascii', 'backslashreplace').decode('ascii'))
    
    assert response.status == "ok", "L'endpoint ha restituito uno stato non ok!"
    assert len(response.response) > 0, "La risposta di Genesi è vuota!"
    print("[OK] Test 2 Superato con Successo!")

async def main():
    print("=== INIZIO INTEGRATION TEST: GRUPPO WHATSAPP ===")
    try:
        await test_disambiguation_and_counting()
        await test_group_link_explorer()
        print("\n=== TUTTI I TEST DI INTEGRAZIONE LOCALI SUPERATI CON SUCCESSO! ===")
    except Exception as e:
        print(f"\n[FAIL] TEST FALLITO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
