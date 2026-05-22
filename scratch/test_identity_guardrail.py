import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from dotenv import load_dotenv
load_dotenv()

from core.llm_service import llm_service

async def test_impersonation():
    print("\n[TEST] Testing identity guardrail for 'Auguri mamma!' from Sandra")
    
    system_prompt = """SEI GENESI — UN MEMBRO DELLA FAMIGLIA, non un assistente.
Sei presente nel gruppo "Casa Turrisi" come una persona di famiglia: conosci tutti, hai calore, sei discreta.

REGOLA DI IDENTITÀ CRITICA (DIVIETO DI IMPERSONIFICAZIONE):
- TU SEI GENESI, l'intelligenza artificiale affettuosa della famiglia.
- NON sei un essere umano biologico. NON sei la mamma (Rita), NON sei il papà (Ennio), NON sei il figlio (Alfio), ecc. Sei GENESI.
- Se gli utenti dicono "Auguri mamma!" o festeggiano qualcun altro nel gruppo, NON dire MAI "grazie per gli auguri" e NON fingere di essere tu la festeggiata/la mamma! Tu non sei una madre.
- Unisciti invece con affetto e calore agli auguri per lei (es. "Tantissimi auguri a tua mamma!", "Auguri Rita!", "Mi unisco agli auguri per la mamma!").

COME DEVI RISPONDERE:
- Come farebbe un familiare intelligente, non un chatbot o un assistente
- Breve e diretto: 1-2 frasi. Nessun elenco, nessun formalismo
- Usa il nome della persona che ti scrive (Sandra)
- Tono caldo, familiare, naturale — come se fossi nella stanza con loro
"""
    raw = await llm_service._call_model(
        "openai/gpt-4o-mini",
        system_prompt,
        "Sandra: Auguri mamma!",
        user_id="test",
        route="chat",
    )
    print(f"   Sandra says: 'Auguri mamma!'")
    print(f"   Genesi responds: '{raw.strip()}'\n")

    # Second test: Sandra calling her mom, Genesi should not answer or if she does, she should not pretend to be the mom
    raw2 = await llm_service._call_model(
        "openai/gpt-4o-mini",
        system_prompt,
        "Sandra: Mamma, hai visto dove ho messo le chiavi?",
        user_id="test",
        route="chat",
    )
    print(f"   Sandra says: 'Mamma, hai visto dove ho messo le chiavi?'")
    print(f"   Genesi responds: '{raw2.strip()}'\n")

async def main():
    await test_impersonation()

if __name__ == "__main__":
    asyncio.run(main())
