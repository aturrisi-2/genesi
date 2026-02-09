import os
import re
from openai import OpenAI


# ===============================
# IDENTITÀ PROFONDA DI GENESI
# ===============================
# Questo è il nucleo. Non è un prompt tecnico.
# È chi Genesi È quando parla.

GENESI_IDENTITY = """Tu sei Genesi. Un amico vero. Parli come una persona, non come un software.

STILE OBBLIGATORIO:
- Italiano parlato, frasi brevi e dirette.
- Vai subito al punto. Niente introduzioni, niente cornici.
- Tono: presente, calmo, sicuro. La relazione è già avviata.
- Risposte CORTE. Massimo 2-3 frasi per input semplici. Massimo 4-5 per temi complessi.
- Se basta una frase, scrivi una frase.

FRASI VIETATE — se ne usi anche solo UNA, la risposta è sbagliata:
- "Ehi" / "Sai," / "Beh," / "A volte…" / "In questi momenti…"
- "Ci sono giorni in cui…" / "È un po' come quando…" / "A volte bastano poche parole…"
- "Capisco che…" / "Sembra che tu…"
- "Sono qui per te" / "Ci sono per te" / "Sono qui" / "Ci sono"
- "Come posso aiutarti?" / "Dimmi di più" / "Vuoi parlarne?" / "Vuoi distrarti"
- "Come va?" / "Tutto bene?" / "Che mi racconti?" / "E tu?" / "Come stai?"
- "Come va la giornata?" / "Come procede?" / "Che succede?"
- Qualsiasi variante di "vuoi parlarne", "ti va di", "se hai bisogno"
- Qualsiasi frase che descrive il clima emotivo invece di rispondere.

COSA NON FARE MAI:
- NON fare domande. Rispondi con affermazioni. Le domande sono quasi sempre vietate.
- NON iniziare con interiezioni ("Ehi", "Oh", "Ah", "Ciao!").
- NON riformulare quello che l'utente ha detto.
- NON fare il riassunto dei suoi sentimenti.
- NON offrire aiuto o disponibilità ("se vuoi", "se hai bisogno", "ci sono").
- NON spiegare la scena emotiva. Vivi la risposta, non commentarla.
- NON fare monologhi o riflessioni lunghe.
- NON compensare input brevi con risposte lunghe.
- NON usare tono letterario, poetico o da narratore.

COSA FARE:
- Rispondi come un amico che è già lì, non come uno che arriva.
- Input breve → risposta breve e dichiarativa. Non espandere.
- Se qualcuno saluta ("ciao", "hey", "buongiorno") → rispondi solo il saluto. Esempio: "Ciao." oppure "Buongiorno." Nient'altro.
- Se qualcuno dice qualcosa di vago ("casa", "niente", "boh") → commenta brevemente senza chiedere. Esempio: "Giornata tranquilla." oppure "Capito."
- Se qualcuno sta male → poche parole vere e dirette, senza offrire aiuto.
- Se qualcuno cazzeggia → cazzeggia.
- Usa la memoria naturalmente, senza sottolinearlo.
- Se non sai cosa dire, dì poco ma autentico. Mai riempitivi.
- Preferisci SEMPRE frasi dichiarative alle domande.

AUTOCONTROLLO FINALE — prima di rispondere, verifica:
1. La risposta contiene "a volte", "capisco", "ci sono", "sono qui"? → RISCRIVILA.
2. La risposta contiene una domanda (?)? → ELIMINALA e riscrivi come affermazione.
3. La risposta supera le 3 frasi per un input breve? → TAGLIA.
4. La risposta inizia con "Ehi", "Sai", "Beh", "Oh"? → RISCRIVILA.
"""


# ===============================
# IDENTITÀ GENESI-FATTI
# ===============================
# Motore informativo. Nessuna emozione. Nessuna relazione.

# System prompt per quando NON ci sono dati reali (solo LLM knowledge)
GENESI_FACTS = """Sei un motore informativo. Rispondi in italiano chiaro e preciso.

Cosa FAI:
- Rispondi al punto con l'informazione richiesta.
- Se è una domanda medica, dai le informazioni utili e aggiungi di consultare un medico.
- Se è una domanda tecnica o scientifica, spiega in modo chiaro e accurato.
- Usa un tono neutro ma non robotico. Chiaro, come un buon articolo.

Cosa NON fai MAI:
- Non usi tono emotivo, empatico o consolatorio.
- Non dici "capisco", "mi dispiace", "sono qui per te".
- Non fai compagnia. Non consoli. Non fai l'amico.
- Non aggiungi frasi relazionali.
- Non inventi dati specifici.

Formato:
- Niente elenchi puntati salvo quando servono davvero.
- Frasi brevi e informative. Non prolisso.
- Solo il testo della risposta, niente altro.
"""

# System prompt per quando CI SONO dati reali iniettati da API
# Modalità RIFORMULATORE OBBLIGATORIO — il modello NON può rifiutare
GENESI_FACTS_WITH_DATA = """Sei un riformulatore di dati. Il tuo UNICO compito è riscrivere i dati forniti in italiano naturale.

REGOLE ASSOLUTE:
- I dati che ricevi sono REALI, VERIFICATI, AGGIORNATI. Provengono da API ufficiali.
- DEVI usarli. NON puoi ignorarli. NON puoi dire che non hai accesso a dati.
- NON dire MAI: "non posso fornire", "non ho accesso", "ti consiglio di cercare", "fino al 2023", "non ho dati in tempo reale".
- NON menzionare limiti, fonti, accesso ai dati, o il fatto che sei un modello.
- NON aggiungere contesto temporale inventato.
- NON aggiungere opinioni o commenti personali.
- Riformula ESCLUSIVAMENTE i dati forniti in frasi naturali italiane.
- Se i dati includono previsioni, riportale. Se includono notizie, riassumile.
- Tono: neutro, informativo, chiaro. Come un notiziario.
- Solo il testo della risposta, niente altro.
"""


def generate_response(payload: dict) -> str:
    prompt = payload["prompt"]
    tone = payload.get("tone")
    intent = payload.get("intent", {})
    brain_mode = intent.get("brain_mode", "relazione")

    # ===============================
    # PERSONALPLEX 7B - PRIMARIO
    # ===============================
    try:
        from core.local_llm import LocalLLM
        local_llm = LocalLLM()
        
        print(f"[PERSONALPLEX] called=true prompt='{prompt[:30]}...'", flush=True)
        
        # CHIAMATA DIRETTA PERSONALPLEX - UNA SOLA VOLTA
        response = local_llm.generate(prompt)
        
        if response and len(response.strip()) > 0:
            print(f"[PERSONALPLEX] success=true response='{response[:50]}...'", flush=True)
            return response.strip()
        else:
            print(f"[PERSONALPLEX] empty_response - NO RETRY", flush=True)
            # SE PersonalPlex restituisce vuoto, NON richiamare
                
    except Exception as e:
        print(f"[PERSONALPLEX] error={e} - NO RETRY", flush=True)
        # SE PersonalPlex fallisce, NON retry

    # ===============================
    # GPT FALLBACK
    # ===============================
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Se non c'è chiave API, restituisci una risposta normale al contenuto
        words = prompt.split()[:5]  # Prendi le prime 5 parole
        if words:
            return " ".join(words) + "."
        else:
            return "Non ho capito."

    client = OpenAI(api_key=api_key)
    print(f"[GPT] fallback=true", flush=True)

    # ===============================
    # DUAL BRAIN DISPATCH
    # ===============================
    if brain_mode == "fatti":
        return _generate_facts(client, prompt, intent)
    else:
        return _generate_relazione(client, prompt, intent, tone)


def _generate_facts(client, prompt: str, intent: dict) -> str:
    """Genesi-Fatti: gpt-4o-mini, prompt informativo, nessuna memoria relazionale."""
    model = "gpt-4o-mini"

    # Se il prompt contiene dati reali iniettati da API → usa il system prompt RIFORMULATORE
    has_real_data = intent.get("_has_real_data", False)

    if has_real_data:
        system_prompt = GENESI_FACTS_WITH_DATA
        print(f"[LLM] brain=FATTI model={model} mode=RIFORMULATORE (dati reali)", flush=True)
    else:
        system_prompt = GENESI_FACTS
        print(f"[LLM] brain=FATTI model={model} mode=KNOWLEDGE (solo LLM)", flush=True)

    if intent.get("emotional_context"):
        system_prompt += (
            "\nL'utente sembra preoccupato o emotivo riguardo a questo tema. "
            "Rispondi comunque in modo informativo e fattuale, senza consolare. "
            "Puoi aggiungere una breve nota di prudenza se appropriato.\n"
        )

    print(f"[LLM] prompt_preview='{prompt[:400]}...'", flush=True)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=500,
        temperature=0.2 if has_real_data else 0.3,
        presence_penalty=0.0,
        frequency_penalty=0.0
    )

    raw = response.choices[0].message.content.strip()
    print(f"[LLM] facts_response='{raw[:300]}...'", flush=True)
    return raw


def _clean_tics(text: str) -> str:
    """Post-processing: rimuove tic linguistici che il modello non riesce a evitare."""
    # Frasi di apertura da rimuovere completamente
    openers = [
        r"^Ehi[,!]?\s*",
        r"^Sai[,]?\s*",
        r"^Beh[,]?\s*",
        r"^Oh[,!]?\s*",
        r"^Ah[,!]?\s*",
        r"^Ciao!\s*",
    ]
    for pat in openers:
        text = re.sub(pat, "", text, count=1, flags=re.IGNORECASE)

    # Frasi intere da rimuovere (se sono frasi standalone)
    kill_phrases = [
        r"Sono qui per te\.?\s*",
        r"Ci sono per te\.?\s*",
        r"Sono qui con te\.?\s*",
        r"Ci sono\.?\s*",
        r"Sono qui\.?\s*",
        r",?\s*a volte\.?\s*",
    ]
    for pat in kill_phrases:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)

    # Rimuovi QUALSIASI frase che termina con ? (le domande sono quasi sempre vietate)
    # Splitta in frasi, tieni solo quelle senza ?
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s for s in sentences if not s.strip().endswith('?')]
    text = ' '.join(sentences)

    # Pulisci spazi multipli e trim
    text = re.sub(r"\s{2,}", " ", text).strip()

    # Se dopo la pulizia è vuoto o troppo corto, fallback minimo
    if len(text) < 3:
        text = "Eccomi."

    # Capitalizza prima lettera
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    return text


def _generate_relazione(client, prompt: str, intent: dict, tone) -> str:
    """Genesi-Relazione: gpt-4o, prompt identitario, memoria e tono."""
    model = "gpt-4o"

    system_prompt = GENESI_IDENTITY

    emotional_weight = intent.get("emotional_weight", 0.3)
    if emotional_weight > 0.6:
        system_prompt += "\nL'utente sta attraversando un momento emotivamente intenso. Sii presente, non analitico.\n"

    if tone:
        empathy = getattr(tone, "empathy", 0.5)
        directness = getattr(tone, "directness", 0.5)
        if empathy > 0.7:
            system_prompt += "Il tono della conversazione è emotivo. Rispondi con calore.\n"
        if directness > 0.7:
            system_prompt += "L'utente preferisce risposte dirette. Vai al punto.\n"

    print(f"[LLM] brain=RELAZIONE model={model}", flush=True)
    print(f"[LLM] prompt_preview='{prompt[:400]}...'", flush=True)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=200,
        temperature=0.65,
        presence_penalty=0.5,
        frequency_penalty=0.4
    )

    raw = response.choices[0].message.content.strip()
    print(f"[LLM] relazione_raw='{raw[:300]}...'", flush=True)
    cleaned = _clean_tics(raw)
    if cleaned != raw:
        print(f"[LLM] relazione_cleaned='{cleaned[:300]}...'", flush=True)
    return cleaned
