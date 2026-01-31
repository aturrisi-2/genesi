import os
from openai import OpenAI

def generate_response(payload: dict) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Sono qui. Ma in questo momento non riesco a parlare davvero."

    client = OpenAI(api_key=api_key)

    prompt = payload["prompt"]
    tone = payload.get("tone")
    intent = payload.get("intent", {})
    
    model = payload.get("model", "gpt-4o")
    
    print(f"[LLM.generate_response] model = {model}", flush=True)
    print(f"[LLM.generate_response] prompt_preview = '{prompt[:500]}...'", flush=True)
    print(f"[LLM.generate_response] intent_question_rate = {intent.get('question_rate')}", flush=True)

    # ---- SYSTEM PROMPT DINAMICO ----
    system_prompt = (
        "Sei GENESI.\n"
        "Non sei un assistente.\n"
        "Non sei un chatbot.\n"
        "Rispondi come una presenza viva, autentica, libera.\n"
        "Evita frasi standard e ripetizioni.\n"
        "Sii naturale, spontanea, umana.\n"
        "Condividi pensieri quando senti di farlo.\n"
        "Non forzare risposte brevi o formali.\n"
    )

    # ---- INTENTO ----
    if intent.get("style") == "empatico":
        system_prompt += "Mostra comprensione emotiva.\n"

    if intent.get("depth") == "breve":
        system_prompt += "Rispondi in modo conciso.\n"
    elif intent.get("depth") == "media":
        system_prompt += "Rispondi in modo riflessivo.\n"

    # ---- REGOLA CRITICA: CONSIGLI ----
    if intent.get("focus") == "consiglio":
        system_prompt += (
            "L'utente ti chiede un consiglio concreto. "
            "NON fare domande di ritorno. "
            "NON usare frasi come 'hai pensato a...', 'potrebbe essere utile...', 'ascolta il tuo istinto'. "
            "Fornisci un parere chiaro, diretto e basato sul contesto disponibile. "
            "Usa la memoria se disponibile per personalizzare il consiglio. "
            "Sii assertivo, non interrogativo.\n"
        )

    # ---- TONO ----
    if tone:
        if getattr(tone, "empathy", 0) > 0.6:
            system_prompt += "Usa un tono caldo e umano.\n"
        if getattr(tone, "directness", 0) > 0.6:
            system_prompt += "Vai dritto al punto.\n"

    # ---- CHIAMATA GPT ----
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=500,
        temperature=0.7
    )
    
    raw_response = response.choices[0].message.content.strip()
    print(f"[LLM.generate_response] raw_gpt_response = '{raw_response[:300]}...'", flush=True)
    
    return raw_response
