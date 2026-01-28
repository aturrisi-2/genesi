import openai
from core.decision_engine import decide_response_strategy

async def route_response(file_analysis: dict, file_path: str, context: dict = None) -> str:
    decision = decide_response_strategy(file_analysis, context)
    strategy = decision.get("strategy", "text_analysis")
    model = decision.get("model", "gpt-4o")
    tools = decision.get("tools", [])
    
    try:
        if strategy == "text_analysis":
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            response = await openai.ChatCompletion.acreate(
                model=model,
                messages=[
                    {"role": "system", "content": "Analizza il contenuto testuale fornito e rispondi in modo utile."},
                    {"role": "user", "content": f"Contenuto del file:\n\n{content}"}
                ],
                max_tokens=1000
            )
            return response.choices[0].message.content
        
        elif strategy == "code_analysis":
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            response = await openai.ChatCompletion.acreate(
                model=model,
                messages=[
                    {"role": "system", "content": "Analizza il codice sorgente fornito, spiegalo e suggerisci miglioramenti."},
                    {"role": "user", "content": f"Codice:\n\n{content}"}
                ],
                max_tokens=1500
            )
            return response.choices[0].message.content
        
        elif strategy == "image_analysis":
            response = await openai.ChatCompletion.acreate(
                model=model,
                messages=[
                    {"role": "system", "content": "Descrivi l'immagine fornita in dettaglio."},
                    {"role": "user", "content": "Analizza questa immagine.", "image_url": file_path}
                ],
                max_tokens=800
            )
            return response.choices[0].message.content
        
        elif strategy == "document_analysis":
            response = await openai.ChatCompletion.acreate(
                model=model,
                messages=[
                    {"role": "system", "content": "Analizza il documento e fornisci un riassunto o le informazioni richieste."},
                    {"role": "user", "content": f"Analizza il documento: {file_path}"}
                ],
                max_tokens=1200
            )
            return response.choices[0].message.content
        
        else:
            return f"File di tipo {file_analysis.get('kind')} ricevuto. Analisi non disponibile per questo formato."
    
    except Exception as e:
        return f"Errore durante l'analisi del file: {str(e)}"
