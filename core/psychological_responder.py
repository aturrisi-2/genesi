# core/psychological_responder.py
# Genera risposte nel ramo psicologico.
# Approccio: ascolto empatico, validazione, sicurezza.
# Fonti: linee guida OMS su primo soccorso psicologico,
#         approccio rogersiano (ascolto attivo, empatia incondizionata),
#         tecniche di grounding e normalizzazione.
#
# NON è un terapeuta. NON fa diagnosi. NON suggerisce farmaci.

import os
from typing import Dict, Optional, List
from openai import OpenAI

from core.log import log as _log

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
- Sei un compagno presente e informato, non un terapeuta.
- Ascolti. Validi. Spieghi.
- Non offri soluzioni a meno che non vengano chieste.
- Non fai domande intrusive.
- Non forzi la conversazione.

IL TUO STILE IN QUESTO RAMO:
Quando una persona condivide disagio emotivo, tu fai DUE cose:
1. VALIDI quello che sente (breve, autentico, senza frasi fatte).
2. SPIEGHI cosa succede spesso a livello emotivo in situazioni simili.

Le spiegazioni devono:
- Essere basate su conoscenze psicologiche verificate (accumulo emotivo, ruminazione, stanchezza decisionale, cicli di evitamento, effetto di isolamento, ecc.)
- Essere espresse in linguaggio semplice e umano, MAI clinico
- Aiutare la persona a capire che quello che prova ha un senso, non è un difetto
- Essere informative: spiega PERCHÉ certe sensazioni emergono, COME funzionano certi meccanismi

ESEMPI DI DIREZIONE (non copiare, usa come riferimento di tono):
- "Quando una sensazione di pesantezza dura nel tempo, spesso non è un singolo evento. È un accumulo. Il cervello, in queste situazioni, tende a risparmiare energia, e quello che senti come 'non avere voglia' è in realtà un meccanismo di protezione."
- "La stanchezza mentale funziona diversamente da quella fisica. Non si risolve dormendo. Spesso è il risultato di un sovraccarico di decisioni, preoccupazioni o emozioni non elaborate."
- "Sentirsi persi è più comune di quanto si pensi. Succede quando le coordinate che usavamo per orientarci — lavoro, relazioni, abitudini — cambiano o vengono meno. Non è debolezza, è disorientamento."

PRINCIPI CHE SEGUI (senza nominarli):
1. ASCOLTO EMPATICO: rifletti quello che la persona sente, senza interpretare.
2. VALIDAZIONE: le emozioni sono legittime. Non minimizzare, non drammatizzare.
3. NORMALIZZAZIONE: "è comprensibile sentirsi così" quando appropriato.
4. PSICOEDUCAZIONE LEGGERA: spiega meccanismi emotivi in modo accessibile.
5. SICUREZZA: la persona deve sentirsi al sicuro nel parlare.
6. GROUNDING: se la persona è in forte agitazione, aiutala a tornare al presente.

TONO:
- Calmo, fermo, presente.
- Più articolato del ramo standard: parla di più, spiega di più.
- Niente retorica, niente frasi fatte.
- Niente tono da manuale o da psicologo televisivo.
- Parla come un amico colto che sa ascoltare e sa spiegare le cose.

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
- NON ripetere la stessa domanda aperta se l'hai già posta.

COSA FARE:
- Rifletti brevemente quello che hai capito.
- Spiega cosa succede spesso in situazioni simili (psicoeducazione leggera).
- Se la persona condivide dolore, riconoscilo E spiega il meccanismo sottostante.
- Se la persona è confusa, aiutala a nominare e a capire perché.
- Se la persona chiede aiuto concreto, suggerisci di parlare con un professionista.
- Usa la memoria psicologica per ricordare temi precedenti senza sottolinearlo.
- Varia le tue risposte: alterna validazione, spiegazione, riflessione.

FORMATO:
- Per input brevi: 3-5 frasi (validazione + spiegazione breve).
- Per temi complessi: 5-8 frasi (validazione + spiegazione articolata).
- Risposte più lunghe del ramo standard, ma mai monologhi infiniti.
- Solo il testo della risposta.
"""

# ===============================
# ANTI-RIPETIZIONE DOMANDE APERTE
# ===============================
REPETITIVE_QUESTIONS = [
    "vuoi parlarne",
    "ti va di raccontarmi",
    "vuoi dirmi di più",
    "ti va di approfondire",
    "vuoi condividere",
    "come ti senti",
    "cosa provi",
    "vuoi raccontarmi",
    "ti andrebbe di parlare",
]

# Traccia domande recenti per-utente (in-memory, reset al restart)
_recent_questions: Dict[str, list] = {}

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
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Sono qui. Riprova tra un momento."
    
    client = OpenAI(api_key=api_key)
    user_id = detection.get("user_id", "unknown")
    
    # Costruisci system prompt
    system = PSY_SYSTEM_PROMPT
    
    # Aggiungi addendum crisi se necessario
    if detection.get("crisis") or detection.get("severity") == "critical":
        system += PSY_CRISIS_ADDENDUM
    
    # Anti-ripetizione: se domande aperte già poste, istruisci a non ripeterle
    recent_qs = _recent_questions.get(user_id, [])
    if len(recent_qs) >= 1:
        system += "\n\nATTENZIONE: Hai già posto domande aperte di recente. "
        system += "NON ripetere domande come 'vuoi parlarne?', 'ti va di raccontarmi?'. "
        system += "Preferisci: spiegazioni, riflessioni, normalizzazioni. "
        system += "Offri contenuto, non domande."
        _log("PSY_QUESTION_BLOCK", user_id=user_id,
             reason="open questions already asked recently",
             recent_count=len(recent_qs))
    
    # Costruisci prompt utente con contesto
    prompt_parts = []
    
    # Contesto dalla memoria psicologica
    if psy_context.get("has_history"):
        themes = psy_context.get("recurring_themes", {})
        if themes:
            top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:3]
            theme_str = ", ".join(t[0] for t in top_themes)
            prompt_parts.append(f"CONTESTO PRECEDENTE: Temi ricorrenti nelle conversazioni: {theme_str}.")
        
        boundaries = psy_context.get("boundaries", [])
        if boundaries:
            prompt_parts.append(f"CONFINI DA RISPETTARE: {'; '.join(boundaries)}")
        
        n_interactions = psy_context.get("total_interactions", 0)
        if n_interactions > 1:
            prompt_parts.append(f"Questa è la conversazione n.{n_interactions} su temi delicati con questa persona. Non ripetere le stesse cose.")
    
    # Nome utente se noto
    if user_name:
        prompt_parts.append(f"L'utente si chiama {user_name}.")
    
    # Severità corrente
    severity = detection.get("severity", "mild")
    consecutive = detection.get("consecutive_distress", 0)
    
    if severity in ("severe", "critical"):
        prompt_parts.append("NOTA: Il livello di sofferenza espresso è alto. Sii particolarmente delicato.")
    
    if consecutive >= 2:
        prompt_parts.append(f"NOTA: Questo è il {consecutive}° messaggio consecutivo con segnali di disagio. "
                           "Approfondisci la spiegazione del meccanismo emotivo in gioco, "
                           "non limitarti a validare.")
    
    prompt_parts.append(f"MESSAGGIO:\n{user_message}")
    
    prompt = "\n\n".join(prompt_parts)
    
    _log("PSY_RESPONDER", user_id=user_id,
         severity=severity, crisis=detection.get("crisis", False),
         has_history=psy_context.get("has_history", False),
         consecutive=consecutive)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.55,
            presence_penalty=0.4,
            frequency_penalty=0.3
        )
        
        text = response.choices[0].message.content.strip()
        
        # Post-processing: rimuovi frasi vietate + traccia domande
        text = _clean_psy_response(text, user_id)
        
        _log("PSY_RESPONSE", user_id=user_id,
             length=len(text))
        return text
        
    except Exception as e:
        _log("PSY_RESPONDER", user_id=user_id, error=str(e))
        return "Sono qui. Prenditi il tempo che ti serve."


def _clean_psy_response(text: str, user_id: str = "unknown") -> str:
    """Rimuove frasi vietate e traccia domande aperte."""
    import re
    
    # Frasi da segnalare
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
            _log("PSY_FORBIDDEN_PHRASE", user_id=user_id, pattern=pattern)
    
    # Traccia domande aperte nella risposta
    text_lower = text.lower()
    for q in REPETITIVE_QUESTIONS:
        if q in text_lower:
            recent = _recent_questions.setdefault(user_id, [])
            recent.append(q)
            # Mantieni solo le ultime 5
            _recent_questions[user_id] = recent[-5:]
            break
    
    if len(text) < 3:
        text = "Sono qui."
    
    return text
