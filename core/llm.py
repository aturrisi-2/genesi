import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_response(payload: dict) -> str:
    prompt = payload["prompt"]
    tone = payload.get("tone")
    intent = payload.get("intent", {})

    system_prompt = (
        "Sei GENESI. Non sei un assistente. "
        "Rispondi in modo naturale, umano, non ripetitivo. "
        "Non usare frasi standard."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    return response.choices[0].message.content.strip()
