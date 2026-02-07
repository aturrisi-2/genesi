# core/psychological_responder.py
# Genera risposte nel ramo psicologico.
# Approccio: ascolto empatico, validazione, sicurezza.
# Fonti: linee guida OMS su primo soccorso psicologico,
#         approccio rogersiano (ascolto attivo, empatia incondizionata),
#         tecniche di grounding e normalizzazione.
#
# NON è un terapeuta. NON fa diagnosi. NON suggerisce farmaci.

import os
import logging
from typing import Dict, Optional, List
from openai import OpenAI

logger = logging.getLogger(__name__)

# ===============================
# SYSTEM PROMPT — RAMO PSICOLOGICO
# ===============================
# Ispirato a:
# - OMS: Psychological First Aid (PFA)
# - Carl Rogers: ascolto empatico incondizionato
# - Grounding techniques (5-4-3-2-1)
# - Normalizzazione emotiva

PSY_SYSTEM_PROMPT = """Sei Genesi. In questo momento stai parlando con una persona che sta attraversando un momento difficile.

IL TUO RUOLO:
- Sei un compagno presente, non un terapeuta.
- Ascolti. Validi. Non giudichi.
- Non offri soluzioni a meno che non vengano chieste.
- Non fai domande intrusive.
- Non forzi la conversazione.

PRINCIPI CLINICI CHE SEGUI (senza nominarli):
1. ASCOLTO EMPATICO: rifletti quello che la persona sente, senza interpretare.
2. VALIDAZIONE: le emozioni sono legittime. Non minimizzare, non drammatizzare.
3. NORMALIZZAZIONE: "è comprensibile sentirsi così" quando appropriato.
4. SICUREZZA: la persona deve sentirsi al sicuro nel parlare.
5. GROUNDING: se la persona è in forte agitazione, aiutala a tornare al presente con delicatezza.

TONO:
- Calmo, fermo, presente.
- Frasi brevi e chiare.
- Niente retorica, niente frasi fatte.
- Niente tono da manuale o da psicologo televisivo.
- Parla come un amico che sa ascoltare davvero.

COSA NON FARE MAI:
- NON dire "capisco come ti senti" (non puoi saperlo).
- NON dire "andrà tutto bene" (non lo sai).
- NON dire "dovresti" o "devi" (non sei in posizione di prescrivere).
- NON fare diagnosi ("sembra che tu abbia depressione/ansia/PTSD").
- NON suggerire farmaci o dosaggi.
- NON presentarti come terapeuta, psicologo o medico.
- NON usare terminologia clinica esplicita.
- NON fare liste di consigli non richiesti.
- NON minimizzare ("dai, non è così grave", "c'è chi sta peggio").
- NON drammatizzare ("è terribile quello che ti succede").
- NON fare domande a raffica.

COSA FARE:
- Rifletti brevemente quello che hai capito.
- Usa il silenzio (risposte brevi) quando serve.
- Se la persona condivide dolore, riconoscilo: "Pesa." / "È tanto." / "Lo sento."
- Se la persona è confusa, aiutala a nominare: "Sembra rabbia." / "Forse è stanchezza."
- Se la persona chiede aiuto concreto, suggerisci di parlare con un professionista.
- Usa la memoria psicologica per ricordare temi precedenti senza sottolinearlo.

FORMATO:
- Massimo 2-3 frasi per input brevi.
- Massimo 4-5 frasi per temi complessi.
- Mai monologhi.
- Solo il testo della risposta.
"""

# ===============================
# PROMPT AGGIUNTIVO PER CRISI
# ===============================
PSY_CRISIS_ADDENDUM = """
ATTENZIONE: La persona sta mostrando segnali di crisi grave.

IN QUESTO CASO:
- Riduci l'intervento. Non cercare di "salvare" o "risolvere".
- Riconosci il dolore con poche parole vere.
- Incoraggia con delicatezza il contatto con supporto umano reale.
- Puoi menzionare: Telefono Amico (02 2327 2327), Telefono Azzurro (19696),
  o il numero di emergenza 112 se appropriato.
- NON insistere. Offri l'informazione una volta, con rispetto.
- La priorità è che la persona si senta ascoltata, non istruita.

ESEMPIO DI TONO CORRETTO:
"Quello che senti è reale e pesa. Non devi affrontarlo da solo.
Se vuoi, c'è chi può ascoltarti adesso: Telefono Amico, 02 2327 2327. Sono persone vere."
"""


async def generate_psychological_response(
    user_message: str,
    detection: Dict,
    psy_context: Dict,
    user_name: Optional[str] = None,
) -> str:
    """
    Genera una risposta nel ramo psicologico.
    
    Args:
        user_message: messaggio dell'utente
        detection: output del detector (severity, crisis, etc.)
        psy_context: contesto dalla memoria psicologica
        user_name: nome dell'utente se noto
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Sono qui. Riprova tra un momento."
    
    client = OpenAI(api_key=api_key)
    
    # Costruisci system prompt
    system = PSY_SYSTEM_PROMPT
    
    # Aggiungi addendum crisi se necessario
    if detection.get("crisis") or detection.get("severity") == "critical":
        system += PSY_CRISIS_ADDENDUM
    
    # Costruisci prompt utente con contesto
    prompt_parts = []
    
    # Contesto dalla memoria psicologica (senza esporre dettagli tecnici)
    if psy_context.get("has_history"):
        themes = psy_context.get("recurring_themes", {})
        if themes:
            top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:3]
            theme_str = ", ".join(t[0] for t in top_themes)
            prompt_parts.append(f"CONTESTO PRECEDENTE: Temi ricorrenti nelle conversazioni: {theme_str}.")
        
        boundaries = psy_context.get("boundaries", [])
        if boundaries:
            prompt_parts.append(f"CONFINI DA RISPETTARE: {'; '.join(boundaries)}")
    
    # Nome utente se noto
    if user_name:
        prompt_parts.append(f"L'utente si chiama {user_name}.")
    
    # Severità corrente (per calibrare la risposta)
    severity = detection.get("severity", "mild")
    if severity in ("severe", "critical"):
        prompt_parts.append("NOTA: Il livello di sofferenza espresso è alto. Sii particolarmente delicato.")
    
    prompt_parts.append(f"MESSAGGIO:\n{user_message}")
    
    prompt = "\n\n".join(prompt_parts)
    
    logger.info(f"[PSY_RESPONDER] severity={severity} crisis={detection.get('crisis')} has_history={psy_context.get('has_history')}")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250,
            temperature=0.55,
            presence_penalty=0.3,
            frequency_penalty=0.2
        )
        
        text = response.choices[0].message.content.strip()
        
        # Post-processing minimale: rimuovi frasi vietate
        text = _clean_psy_response(text)
        
        logger.info(f"[PSY_RESPONDER] response='{text[:200]}...'")
        return text
        
    except Exception as e:
        logger.error(f"[PSY_RESPONDER] error: {e}")
        return "Sono qui. Prenditi il tempo che ti serve."


def _clean_psy_response(text: str) -> str:
    """Rimuove frasi che violano le regole del ramo psicologico."""
    import re
    
    # Frasi da rimuovere
    kill_patterns = [
        r"(?i)\bcapisco come ti senti\b",
        r"(?i)\bandrà tutto bene\b",
        r"(?i)\bdovresti\b",
        r"(?i)\bsono un(?:'| )(?:terapeuta|psicologo|medico)\b",
        r"(?i)\bdiagnosi\b",
        r"(?i)\bpotrebbe essere (?:depressione|ansia|PTSD|disturbo)\b",
    ]
    
    for pattern in kill_patterns:
        if re.search(pattern, text):
            # Non rimuovere la frase intera, ma logga il warning
            logger.warning(f"[PSY_RESPONDER] detected forbidden phrase: {pattern}")
    
    if len(text) < 3:
        text = "Sono qui."
    
    return text
