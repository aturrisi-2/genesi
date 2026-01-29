from openai import OpenAI
from core.decision_engine import decide_response_strategy

client = OpenAI()

def safe_read_file(file_path: str) -> str:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

def prepare_content_for_model_text(text: str) -> str:
    MAX_CHARS = 12000
    HARD_LIMIT = 200000
    
    if len(text) > HARD_LIMIT:
        preview = text[:1000]
        return f"""
Il contenuto completo non è stato incluso per limiti di dimensione.
Ecco cosa posso fare con questo tipo di file e come procedere.

Anteprima del file (primi 1000 caratteri):
---
{preview}
---
"""
    
    if len(text) > MAX_CHARS:
        truncated = text[:MAX_CHARS]
        return f"""
⚠️ Il documento è più lungo del limite massimo.
⚠️ Di seguito viene fornito solo un estratto iniziale del contenuto.
⚠️ Rispondi tenendo conto che il testo è parziale.

---
{truncated}
---
"""
    
    return text

def prepare_content_for_model(file_path: str) -> str:
    MAX_CHARS = 12000
    HARD_LIMIT = 200000
    
    content = safe_read_file(file_path)
    
    if len(content) > HARD_LIMIT:
        preview = content[:1000]
        return f"""
Il contenuto completo non è stato incluso per limiti di dimensione.
Ecco cosa posso fare con questo tipo di file e come procedere.

Anteprima del file (primi 1000 caratteri):
---
{preview}
---
"""
    
    if len(content) > MAX_CHARS:
        truncated = content[:MAX_CHARS]
        return f"""
⚠️ Il documento è più lungo del limite massimo.
⚠️ Di seguito viene fornito solo un estratto iniziale del contenuto.
⚠️ Rispondi tenendo conto che il testo è parziale.

---
{truncated}
---
"""
    
    return content

def get_response_policy(decision: dict, content: str) -> str:
    response_mode = decision.get("response_mode", "direct")
    
    if response_mode == "direct" and content and len(content.strip()) > 50:
        return """
REGOLE COMPORTAMENTALI:
- Rispondi direttamente, non fare domande
- Chiudi la risposta con una conclusione chiara
- Sii presente e risolutivo
- Massimo 1 domanda solo se strettamente necessaria
- Non chiedere conferme inutili
"""
    return ""

async def route_response(file_analysis: dict, file_path: str, context: dict = None) -> str:
    decision = decide_response_strategy(file_analysis, context)
    strategy = decision.get("strategy", "text_analysis")
    model = decision.get("model", "gpt-4o")
    tools = decision.get("tools", [])
    
    try:
        if strategy == "text_analysis":
            content = prepare_content_for_model(file_path)
            policy = get_response_policy(decision, content)
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": f"Analizza il contenuto testuale fornito e rispondi in modo utile.{policy}"},
                    {
                        "role": "user",
                        "content": f"""
L'utente ha caricato il seguente documento:

---
{content}
---

Rispondi analizzando direttamente il contenuto.
"""
                    }
                ],
                max_tokens=1000
            )
            return response.choices[0].message.content
        
        elif strategy == "code_analysis":
            content = prepare_content_for_model(file_path)
            policy = get_response_policy(decision, content)
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": f"Analizza il codice sorgente fornito, spiegalo e suggerisci miglioramenti.{policy}"},
                    {
                        "role": "user",
                        "content": f"""
L'utente ha caricato il seguente codice sorgente:

---
{content}
---

Analizza il codice, spiegalo e suggerisci miglioramenti.
"""
                    }
                ],
                max_tokens=1500
            )
            return response.choices[0].message.content
        
        elif strategy == "image_analysis":
            policy = get_response_policy(decision, "")
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": f"Descrivi l'immagine fornita in dettaglio.{policy}"},
                    {"role": "user", "content": "Analizza questa immagine.", "image_url": file_path}
                ],
                max_tokens=800
            )
            return response.choices[0].message.content
        
        elif strategy == "document_analysis":
            # Check if PDF has extracted text
            if file_analysis.get("subtype") == "pdf" and "has_text" in file_analysis:
                if file_analysis.get("has_text", False):
                    # PDF with extractable text
                    pdf_text = file_analysis.get("text", "")
                    content = prepare_content_for_model_text(pdf_text)
                    policy = get_response_policy(decision, content)
                    
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": f"Analizza il documento e fornisci un riassunto o le informazioni richieste.{policy}"},
                            {
                                "role": "user",
                                "content": f"""
L'utente ha caricato un documento PDF.

Il contenuto testuale del documento è il seguente:
---
{content}
---

Rispondi analizzando direttamente il contenuto del documento.
"""
                            }
                        ],
                        max_tokens=1200
                    )
                    return response.choices[0].message.content
                else:
                    # PDF without text (scanned)
                    policy = get_response_policy(decision, "")
                    
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": f"Analizza il documento e fornisci un riassunto o le informazioni richieste.{policy}"},
                            {
                                "role": "user",
                                "content": """
Il file PDF sembra essere una scansione o non contiene testo selezionabile.
Ecco cosa posso fare:
- interpretarlo se mi descrivi il contenuto
- suggerire strumenti OCR per estrarre il testo
- spiegare come convertire scansioni in documenti testuali

Scegli l'opzione che preferisci o fornisci dettagli sul contenuto.
"""
                            }
                        ],
                        max_tokens=800
                    )
                    return response.choices[0].message.content
            else:
                # Other document types (non-PDF)
                content = prepare_content_for_model(file_path)
                policy = get_response_policy(decision, content)
                
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": f"Analizza il documento e fornisci un riassunto o le informazioni richieste.{policy}"},
                        {
                            "role": "user",
                            "content": f"""
L'utente ha caricato il seguente documento:

---
{content}
---

Rispondi analizzando direttamente il contenuto del documento.
"""
                        }
                    ],
                    max_tokens=1200
                )
                return response.choices[0].message.content
        
        else:
            return f"File di tipo {file_analysis.get('kind')} ricevuto. Analisi non disponibile per questo formato."
    
    except Exception as e:
        return f"Errore durante l'analisi del file: {str(e)}"
